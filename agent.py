#!/usr/bin/env python3
"""
Simple AI Agent with Calculator + CockroachDB Tools

This agent uses LiteLLM to call DeepSeek (deepseek-v4-flash) with
two tools the LLM can invoke:

  1.  calculate(expression)   - evaluates math & stores in DB
  2.  query_database(sql)     - runs SQL from natural language questions

How it works:
  1. You type a message
  2. The agent sends it + tool definitions to DeepSeek
  3. DeepSeek either responds directly OR requests a tool call
  4. If a tool call is requested -> agent runs the tool -> sends result back
  5. DeepSeek gives the final answer
  6. Back to step 1

Requirements:  pip install litellm psycopg2-binary python-dotenv
Setup:         Copy .env.example to .env and fill in your API keys
Run:           python agent.py
"""

import os
import sys
import json

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Import LiteLLM - the unified LLM API library
import litellm

# Import our tools
from tools.calculator import calculate
from tools.db_tool import query_database

# DATABASE CONNECTION
# We connect once at startup and reuse the connection throughout the session.
import psycopg2

COCKROACHDB_URL = os.getenv("COCKROACHDB_URL")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# Read model from .env so you can change it without editing code
# Format: "deepseek/deepseek-v4-flash" or any LiteLLM-supported model
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")

# Connect to CockroachDB
print("Connecting to CockroachDB...")
try:
    db_conn = psycopg2.connect(COCKROACHDB_URL)
    print("Connected to CockroachDB!")
except Exception as e:
    print(f"Failed to connect to CockroachDB: {e}")
    print("   Check your COCKROACHDB_URL in .env")
    sys.exit(1)

# TOOL DEFINITIONS
# These are in OpenAI's tool-calling format (LiteLLM passes them through).
# DeepSeek supports this format natively.

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a math expression and stores the expression + result in the database. Supports: +, -, *, /, **, sqrt(), sin(), cos(), log(), etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g. '15 * 37' or 'sqrt(144) + 8'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Run a SQL query against the CockroachDB database. Use this to discover tables, inspect schemas, fetch data, or insert records. The database has a 'calculations' table with columns: id, expression, result, created_at.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to execute. Allowed: SELECT, INSERT, CREATE TABLE, CREATE INDEX, ALTER TABLE. Blocked: DROP, TRUNCATE, DELETE, UPDATE.",
                    }
                },
                "required": ["sql"],
            },
        },
    },
]

# TOOL HANDLER
# This maps the tool name DeepSeek requests -> the actual Python function.

def handle_tool_call(tool_name: str, args: dict) -> dict:
    """
    Execute the tool requested by DeepSeek.
    """
    print(f"   Tool called: {tool_name}({json.dumps(args)})")

    if tool_name == "calculate":
        return calculate(expression=args["expression"], db_conn=db_conn)

    elif tool_name == "query_database":
        return query_database(sql=args["sql"], db_conn=db_conn)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# SYSTEM PROMPT
# This tells the LLM who it is and what it can do.

SYSTEM_PROMPT = """You are a helpful AI assistant with access to two tools:

1. **calculate(expression)** — Evaluate math expressions and stores them in a database.
   Use this for any math, arithmetic, or numeric calculations.

2. **query_database(sql)** — Run SQL queries against a CockroachDB database.
   Use this to:
   - List tables (SELECT table_name FROM information_schema.tables WHERE table_schema='public')
   - Describe table schemas (SELECT column_name, data_type FROM information_schema.columns WHERE table_name='...')
   - Fetch data from tables
   - Insert new records

The database has a 'calculations' table with columns: id (SERIAL), expression (TEXT), result (TEXT), created_at (TIMESTAMP)."""

# MAIN AGENT LOOP

def chat():
    """Run the interactive chat loop with the agent."""

    # Messages history - starts with the system prompt, then user/assistant messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("\n" + "=" * 60)
    print("  Agent ready! I have a calculator + CockroachDB access.")
    print("  Type 'exit' or 'quit' to stop.")
    print("=" * 60 + "\n")

    while True:
        # 1. GET USER INPUT
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not user_input:
            continue

        # Add user message to history
        messages.append({"role": "user", "content": user_input})

        # 2. SEND TO DEEPSEEK
        # LiteLLM handles the API call. We pass:
        #   - model: "deepseek/deepseek-v4-flash"
        #   - messages: conversation history
        #   - tools: the tool definitions
        #   - tool_choice: "auto" - let the model decide if it needs tools
        print("   Thinking...")
        try:
            response = litellm.completion(
                model=MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                api_key=DEEPSEEK_API_KEY,
            )
        except Exception as e:
            print(f"API Error: {e}")
            print("   Check your DEEPSEEK_API_KEY in .env")
            messages.pop()
            continue

        # 3. PROCESS THE RESPONSE
        response_message = response.choices[0].message

        # Check if the LLM wants to call a tool
        if response_message.tool_calls:
            # The LLM wants to use a tool
            # Add the assistant's message (with tool_calls) to history
            messages.append(response_message)

            # Process each tool call
            for tool_call in response_message.tool_calls:
                # Parse the arguments (they come as a JSON string)
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # Execute the tool
                result = handle_tool_call(
                    tool_name=tool_call.function.name,
                    args=args,
                )

                # 4. SEND TOOL RESULT BACK TO LLM
                # This is how tool calling works:
                #   1. LLM says "I want to call tool X"
                #   2. We run the tool
                #   3. We send the result back as a "tool" role message
                #   4. LLM uses the result to form its final answer
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

            # Now send everything back to the LLM for the final response
            print("   Processing tool results...")
            try:
                final_response = litellm.completion(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    api_key=DEEPSEEK_API_KEY,
                )
                final_message = final_response.choices[0].message

                # Add the final assistant response to history
                messages.append(final_message)

                # Print the response
                print(f"Agent: {final_message.content}")

            except Exception as e:
                print(f"API Error: {e}")

        else:
            # No tool calls - direct text response from the LLM
            messages.append(response_message)
            print(f"Agent: {response_message.content}")


# ENTRY POINT
if __name__ == "__main__":
    try:
        chat()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        # Close the database connection when done
        if db_conn:
            db_conn.close()
            print("Database connection closed.")
