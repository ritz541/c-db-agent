"""
Chat Session Module

Handles the interactive chat loop and message management.
Encapsulates chat state and tool call processing.
"""

import json
import structlog

from core.llm_client import LLMClient
from tools.registry import ToolRegistry


logger = structlog.get_logger()


class ChatSession:
    """
    Chat session manager.
    
    Handles:
    - Message history
    - Multi-turn tool call processing
    - User interaction loop
    """
    
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry, system_prompt: str):
        """
        Initialize the chat session.
        
        Args:
            llm_client: LLM API client
            tool_registry: Tool registry for executing tools
            system_prompt: System prompt for the LLM
        """
        self.llm = llm_client
        self.tool_registry = tool_registry
        self.messages = [{"role": "system", "content": system_prompt}]
        
        logger.info("chat_session.initialized")
    
    def process_user_input(self, user_input: str) -> str:
        """
        Process one user message (handles multi-turn tool calls).

        Args:
            user_input: User's message

        Returns:
            str: Agent's final response
        """
        import uuid
        import sentry_sdk
        from rich.markdown import Markdown
        from rich.console import Console
        console = Console()

        # Generate request ID for tracing
        request_id = uuid.uuid4().hex[:8]

        # Wrap each user interaction in a Sentry transaction
        with sentry_sdk.start_transaction(op="agent_run", name="user_message") as transaction:
            transaction.set_tag("request_id", request_id)

            # Add user message to history
            self.messages.append({"role": "user", "content": user_input})

            # Send to LLM
            try:
                response = self.llm.complete(
                    messages=self.messages,
                    tools=self.tool_registry.get_schemas()
                )
            except Exception as e:
                logger.error("llm.call_failed", error=str(e))
                sentry_sdk.capture_exception(e)
                print("   API Error: Check logs for details")
                self.messages.pop()  # Remove the user message that caused the failure
                return None

            # Process the response (handle multiple rounds of tool calls)
            while True:
                response_message = response.choices[0].message
                logger.info("tool_calls.detected", count=len(response_message.tool_calls) if response_message.tool_calls else 0)

                # If no tool calls, this is the final text response
                if not response_message.tool_calls:
                    self.messages.append(response_message)
                    return response_message.content

                # LLM wants to call tools - print any intermediate content first
                if response_message.content:
                    print()  # blank line before intermediate response
                    console.print(Markdown(response_message.content))
                    print()
                self.messages.append(response_message)
                
                # Process each tool call
                for tool_call in response_message.tool_calls:
                    # Parse the arguments (they come as a JSON string)
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    # Execute the tool
                    from infrastructure.db_pool import get_connection, return_connection
                    
                    conn = get_connection()
                    try:
                        result = self.tool_registry.execute(
                            tool_name=tool_call.function.name,
                            args=args,
                            db_conn=conn
                        )
                    except Exception as tool_e:
                        logger.error(
                            "tool.execution_failed",
                            tool=tool_call.function.name,
                            error=str(tool_e)
                        )
                        result = {"success": False, "error": str(tool_e)}
                    finally:
                        return_connection(conn)
                    
                    # Send tool result back to LLM
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })
                
                # Send tool results back to LLM for final response
                try:
                    response = self.llm.complete(
                        messages=self.messages,
                        tools=self.tool_registry.get_schemas()
                    )
                except Exception as e:
                    logger.error("llm.tool_response_failed", error=str(e))
                    sentry_sdk.capture_exception(e)
                    # Remove the assistant message with tool_calls and tool responses
                    # to keep message history clean
                    self.messages.pop()  # Remove last tool response
                    return f"Sorry, there was an error processing the tool results. Please try again."
    
    def run(self):
        """Run the interactive chat loop."""
        
        from rich.markdown import Markdown
        from rich.console import Console
        console = Console()
        
        print("\n" + "=" * 60)
        print("  Agent ready! I have access to tools:")
        tools = self.tool_registry.list_tools()
        for tool in tools:
            print(f"    - {tool}")
        print("  Type 'exit' or 'quit' to stop.")
        print("  Press Enter twice (blank line) or Ctrl+D to send multi-line messages.")
        print("=" * 60 + "\n")
        
        while True:
            # ── Multi-line input ───────────────────────────────────
            # Reads until an empty line (just Enter) or Ctrl+D
            lines = []
            try:
                while True:
                    prompt = "→ " if lines else "You: "
                    line = input(prompt)
                    if line.strip().lower() in ("exit", "quit"):
                        print("Goodbye!")
                        return
                    if not line.strip() and not lines:
                        # First empty line (user just pressed Enter) - skip
                        continue
                    if not line.strip() and lines:
                        # Empty line after some input - end multi-line
                        break
                    lines.append(line.strip())
            except (EOFError, KeyboardInterrupt):
                pass  # Ctrl+D or Ctrl+C - send whatever was collected
            
            user_input = "\n".join(lines).strip()
            if not user_input:
                continue
            
            # Process the input
            response = self.process_user_input(user_input)
            
            if response:
                print()  # blank line before response
                console.print(Markdown(response))
                print()  # blank line after
