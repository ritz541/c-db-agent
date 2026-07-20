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
import uuid
import tenacity

# ── Observability Setup ─────────────────────────────────────────
# Sentry for error tracking (must be initialized before other imports)
import sentry_sdk

sentry_sdk.init(
    dsn="https://PLACEHOLDER_DSN@oXXX.ingest.sentry.io/XXX",
    send_default_pii=True,
    traces_sample_rate=1.0,  # Set to 0.1 for production
    environment="development",
)

    # Name this agent for Sentry"s AI dashboards
    sentry_sdk.set_tag("agent.name", "c-db-agent")
    sentry_sdk.set_tag("agent.version", "1.0")

# Structlog for structured logging
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.dev.ConsoleRenderer(),  # Use JSONRenderer() for production
    ]
)

logger = structlog.get_logger()

# ── Load Environment Variables ───────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Import LiteLLM - the unified LLM API library
import litellm

# Import our tools
from tools.calculator import calculate
from tools.db_tool import query_database
from tools.email_tool import store_resume, list_resumes, load_resume_from_pdf, draft_application, list_applications, send_email

# Import configuration
from config import get_settings

# Load settings with validation
try:
    settings = get_settings()
    DEEPSEEK_API_KEY = settings.deepseek_api_key
    COCKROACHDB_URL = settings.cockroachdb_url
    MODEL_NAME = settings.llm_model
except Exception as e:
    logger.error("config.load_failed", error=str(e))
    print(f"Configuration error: {e}")
    sys.exit(1)

# DATABASE CONNECTION
# Use a connection pool for better performance and reliability.
import psycopg2
from psycopg2 import pool

logger.info("db.pool_creating")
try:
    db_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        dsn=COCKROACHDB_URL,
    )
    logger.info("db.pool_created")

    # Auto-load resume from PDF if path is set in .env
    # Get a connection from the pool for startup tasks
    db_conn = db_pool.getconn()
    try:
        pdf_path = os.getenv("RESUME_PDF_PATH", "")
        if pdf_path and os.path.isfile(pdf_path):
            result = load_resume_from_pdf(pdf_path=pdf_path, db_conn=db_conn)
            if result["success"]:
                logger.info("resume.loaded", path=pdf_path)
            else:
                logger.warning("resume.load_skipped", error=result.get("error"))
        else:
            logger.info("resume.pdf_not_found")
    finally:
        db_pool.putconn(db_conn)
except Exception as e:
    logger.error("db.pool_creation_failed", error=str(e))
    print(f"Failed to create database connection pool: {e}")
    print("   Check your COCKROACHDB_URL in .env")
    sys.exit(1)


def get_db_connection():
    """Get a connection from the pool."""
    return db_pool.getconn()


def return_db_connection(conn):
    """Return a connection to the pool."""
    db_pool.putconn(conn)

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
    {
        "type": "function",
        "function": {
            "name": "store_resume",
            "description": "Store your resume text in the database for later use in job applications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Full text of your resume"},
                    "name": {"type": "string", "description": "Optional label for this resume (e.g. 'default')"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_resumes",
            "description": "List all stored resumes and when they were saved.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_resume_from_pdf",
            "description": "Read a PDF file from disk, extract its text, and store it in the database as your resume. Use this when you have a new or updated resume PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pdf_path": {
                        "type": "string",
                        "description": "Full path to the PDF file, e.g. '/home/ritz/Downloads/resume.pdf'",
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional label for this resume (default: 'default')",
                    },
                },
                "required": ["pdf_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_application",
            "description": "Generate a tailored cover letter email for a job application. Reads your stored resume + the job description, writes a professional email, and saves it as a draft. You can then send it with send_email().",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "Company name"},
                    "role_title": {"type": "string", "description": "Job title you're applying for"},
                    "recipient_email": {"type": "string", "description": "HR/hiring manager email address"},
                    "job_description": {"type": "string", "description": "The full job description text"},
                },
                "required": ["company", "role_title", "recipient_email", "job_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_applications",
            "description": "List your job applications, optionally filtered by status ('draft' or 'sent').",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status: 'draft' or 'sent'. Omit to see all."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send a drafted application email. Provide the application ID from draft_application().",
            "parameters": {
                "type": "object",
                "properties": {
                    "application_id": {
                        "type": "number",
                        "description": "The ID of the drafted application to send (returned by draft_application)",
                    }
                },
                "required": ["application_id"],
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
    logger.info("tool.called", tool=tool_name, args=args)

    # Get a connection from the pool for this tool call
    db_conn = get_db_connection()
    try:

        with sentry_sdk.start_span(op="tool", description=tool_name) as span:
            span.set_tag("tool.name", tool_name)
            span.set_data("tool.args", args)

            if tool_name == "calculate":
                result = calculate(expression=args["expression"], db_conn=db_conn)
            elif tool_name == "query_database":
                result = query_database(sql=args["sql"], db_conn=db_conn)
            elif tool_name == "store_resume":
                result = store_resume(text=args["text"], name=args.get("name", "default"), db_conn=db_conn)
            elif tool_name == "list_resumes":
                result = list_resumes(db_conn=db_conn)
            elif tool_name == "load_resume_from_pdf":
                result = load_resume_from_pdf(
                    pdf_path=args["pdf_path"],
                    db_conn=db_conn,
                    name=args.get("name", "default"),
                )
            elif tool_name == "draft_application":
                result = draft_application(
                    company=args["company"],
                    role_title=args["role_title"],
                    recipient_email=args["recipient_email"],
                    job_description=args["job_description"],
                    db_conn=db_conn,
                )
            elif tool_name == "list_applications":
                result = list_applications(db_conn=db_conn, status=args.get("status"))
            elif tool_name == "send_email":
                result = send_email(application_id=args["application_id"], db_conn=db_conn)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            span.set_data("tool.result", result)
            return result

    finally:
        # Return the connection to the pool
        return_db_connection(db_conn)


# LLM API CALL WRAPPER
# Wraps litellm.completion with retry logic using tenacity

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
    before_sleep=lambda retry_state: logger.warning(
        "llm.retry",
        attempt=retry_state.attempt_number,
        wait=retry_state.next_action.sleep,
    ),
)
def call_llm(messages: list, tools: list) -> dict:
    """
    Call LLM API with retry logic.

    Parameters
    ----------
    messages : list
        Conversation history
    tools : list
        Tool definitions

    Returns
    -------
    dict
        LLM response
    """
    # Debug: log the last 3 messages to see what we're sending
    for i, msg in enumerate(messages[-3:]):
        role = msg.get("role", "unknown")
        has_tool_calls = bool(msg.get("tool_calls"))
        content_preview = str(msg.get("content", ""))[:50]
        logger.debug("llm.messages_preview", index=len(messages)-3+i, role=role, has_tool_calls=has_tool_calls, content=content_preview)

    logger.info("llm.calling", message_count=len(messages))

    with sentry_sdk.start_span(op="llm", description=MODEL_NAME) as span:
        span.set_tag("llm.model", MODEL_NAME)
        response = litellm.completion(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            api_key=DEEPSEEK_API_KEY,
        )

        # Extract token usage if available (DeepSeek returns usage in response)
        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            if hasattr(usage, "prompt_tokens"):
                span.set_data("llm.tokens.input", usage.prompt_tokens)
                span.set_data("llm.tokens.output", usage.completion_tokens)
                span.set_data("llm.tokens.total", usage.total_tokens)

        logger.info("llm.responded", has_tool_calls=bool(response.choices[0].message.tool_calls))

    return response


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
        # Generate request ID for tracing
        request_id = uuid.uuid4().hex[:8]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

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
        try:
            response = call_llm(messages=messages, tools=tools)
        except Exception as e:
            logger.error("llm.call_failed", error=str(e))
            sentry_sdk.capture_exception(e)
            print("   API Error: Check logs for details")
            messages.pop()  # Remove the user message that caused the failure
            continue

        # 3. PROCESS THE RESPONSE
        # Use a while loop to handle multiple rounds of tool calling.
        # The LLM may need to call tools, get results, then call more tools, etc.
        while True:
            response = call_llm(messages=messages, tools=tools)
            response_message = response.choices[0].message

            # If no tool calls, this is the final text response
            if not response_message.tool_calls:
                messages.append(response_message)
                print(f"Agent: {response_message.content}")
                break

            # LLM wants to call tools - process them
            logger.info("tool_calls.detected", count=len(response_message.tool_calls))
            messages.append(response_message)

            # Process each tool call
            for tool_call in response_message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                try:
                    result = handle_tool_call(
                        tool_name=tool_call.function.name,
                        args=args,
                    )
                except Exception as tool_e:
                    logger.error("tool.execution_failed", tool=tool_call.function.name, error=str(tool_e))
                    result = {"success": False, "error": str(tool_e)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

            # Continue the while loop - the next iteration will send tool results back to LLM


# ENTRY POINT
if __name__ == "__main__":
    try:
        chat()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        # Close the database connection pool when done
        if 'db_pool' in globals():
            db_pool.closeall()
            logger.info("db.pool_closed")
            print("Database connection pool closed.")
