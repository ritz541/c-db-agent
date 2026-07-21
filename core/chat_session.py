"""
Chat Session Module

Handles the interactive chat loop and message management.
Encapsulates chat state and tool call processing.
"""

import asyncio
import json
import structlog
import uuid

from core.llm_client import LLMClient
from core.memory_service import MemoryService
from core.memory_extractor import extract_memory
from tools.registry import ToolRegistry


logger = structlog.get_logger()


class ChatSession:
    """
    Chat session manager.
    
    Handles:
    - Message history
    - Multi-turn tool call processing
    - User interaction loop
    - Memory retrieval and storage
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        system_prompt: str,
        max_tool_retries: int = 2,
        memory_service: MemoryService = None,
        user_id: str = "",
        top_k_memories: int = 5,
        importance_threshold: int = 6,
    ):
        """
        Initialize the chat session.

        Args:
            llm_client: LLM API client
            tool_registry: Tool registry for executing tools
            system_prompt: System prompt for the LLM
            max_tool_retries: Maximum number of retries for failed tool executions
            memory_service: Optional memory service for context retrieval and storage
            user_id: User identifier for memory scoping
            top_k_memories: Number of memories to retrieve per query
            importance_threshold: Minimum importance score to persist a memory
        """
        self.llm = llm_client
        self.tool_registry = tool_registry
        self.messages = [{"role": "system", "content": system_prompt}]
        self.max_tool_retries = max_tool_retries
        self.memory_service = memory_service
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())
        self.top_k_memories = top_k_memories
        self.importance_threshold = importance_threshold
        
        logger.info(
            "chat_session.initialized",
            max_tool_retries=max_tool_retries,
            memory_enabled=memory_service is not None,
            user_id=user_id,
            session_id=self.session_id,
            top_k_memories=top_k_memories,
            importance_threshold=importance_threshold,
        )
    
    def _format_memories(self, memories: list[dict]) -> str:
        """Format retrieved memories for injection into the prompt."""
        lines = []
        for m in memories:
            lines.append(f"[{m['memory_type']}] (importance={m['importance']}): {m['content']}")
        return "\n".join(lines)

    async def _background_extract_and_store(self, user_input: str, llm_response: str):
        """Async background task: extract memories from the conversation turn."""
        try:
            memories_to_store = await extract_memory(
                llm_client=self.llm,
                conversation_history=self.messages[-10:],  # last ~10 messages
                existing_memories=[],  # optional: fetch for update detection
                user_id=self.user_id,
                importance_threshold=self.importance_threshold,
            )
            for mem in memories_to_store:
                if mem["action"] == "create":
                    await self.memory_service.store(
                        content=mem["content"],
                        memory_type=mem["memory_type"],
                        importance=mem["importance"],
                        tags=mem["tags"],
                        user_id=self.user_id,
                        session_id=self.session_id,
                    )
                elif mem["action"] == "update" and mem.get("target_memory"):
                    await self.memory_service.update(
                        target_memory_id=mem["target_memory"],
                        new_content=mem["content"],
                        new_tags=mem.get("tags"),
                    )
        except Exception as e:
            logger.error("memory.extract_and_store_failed", error=str(e))
            # Silently fail — memory loss is not critical
    
    async def process_user_input(self, user_input: str) -> str:
        """
        Process one user message (handles multi-turn tool calls).

        Args:
            user_input: User's message

        Returns:
            str: Agent's final response
        """
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

            # STEP 1: Retrieve relevant memories
            if self.memory_service:
                try:
                    retrieved = await self.memory_service.retrieve(
                        query=user_input,
                        user_id=self.user_id,
                        top_k=self.top_k_memories,
                    )
                    if retrieved:
                        memory_context = self._format_memories(retrieved)
                        self.messages.insert(
                            1,
                            {"role": "system", "content": f"RETRIEVED CONTEXT:\n{memory_context}\n---"}
                        )
                except Exception as e:
                    logger.error("memory.retrieval_failed", error=str(e))
                    # Continue without memories

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
                    final_content = response_message.content

                    # STEP 2: Async memory extraction and storage
                    if self.memory_service:
                        asyncio.create_task(
                            self._background_extract_and_store(user_input, final_content or "")
                        )

                    return final_content

                # LLM wants to call tools - print any intermediate content first
                if response_message.content:
                    print()  # blank line before intermediate response
                    console.print(Markdown(response_message.content))
                    print()
                
                # Process each tool call
                for tool_call in response_message.tool_calls:
                    # Parse the arguments (they come as a JSON string)
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    # Execute the tool with retry logic
                    from infrastructure.db_pool import get_connection, return_connection
                    
                    result = None
                    
                    for attempt in range(self.max_tool_retries):
                        try:
                            conn = get_connection()
                            try:
                                result = self.tool_registry.execute(
                                    tool_name=tool_call.function.name,
                                    args=args,
                                    db_conn=conn
                                )
                                # If successful, break out of retry loop
                                if result.get("success", False):
                                    break
                                # If tool failed but didn't raise exception, still retry
                                elif attempt < self.max_tool_retries - 1:
                                    logger.warning(
                                        "tool.failed_retrying",
                                        tool=tool_call.function.name,
                                        attempt=attempt + 1,
                                        error=result.get("error", "Unknown error")
                                    )
                                    continue
                            finally:
                                return_connection(conn)
                        except Exception as tool_e:
                            logger.error(
                                "tool.execution_failed",
                                tool=tool_call.function.name,
                                attempt=attempt + 1,
                                error=str(tool_e)
                            )
                            if attempt < self.max_tool_retries - 1:
                                # Retry on connection errors or transient failures
                                continue
                            else:
                                result = {"success": False, "error": str(tool_e)}
                    
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
                    return "Sorry, there was an error processing the tool results. Please try again."
    
    async def run(self):
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
                    line = await asyncio.to_thread(input, prompt)
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
            response = await self.process_user_input(user_input)
            
            if response:
                print()  # blank line before response
                console.print(Markdown(response))
                print()  # blank line after
