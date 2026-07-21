import structlog
from typing import Any

from container.services import RuntimeServices
from core.events.base import EventPriority
from core.events.domain import (
    MemoryRetrieved,
    MessageReceived,
    MessageSent,
    PlanCreated,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from core.interfaces.runtime import RuntimeEngineInterface
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.result import RunResult
from core.models.tool import ToolCall, ToolResult
from runtime.middleware.base import RuntimeMiddleware

logger = structlog.get_logger(__name__)


class RuntimeEngine(RuntimeEngineInterface):
    """UI-less Agent Runtime Engine consuming RuntimeServices container."""

    def __init__(
        self,
        services: RuntimeServices,
        middleware: list[RuntimeMiddleware] | None = None,
        max_turns: int = 10,
        system_prompt: str = "You are a helpful AI assistant.",
    ) -> None:
        self.services = services
        self.middleware = middleware or []
        self.max_turns = max_turns
        self.system_prompt = system_prompt

    async def run(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> RunResult:
        ctx = context or ExecutionContext()
        logger.info("runtime_engine.run_started", run_id=ctx.run_id, trace_id=ctx.trace_id)

        # Emit RuntimeStarted
        await self.services.events.publish(
            RuntimeStarted(runtime_id=ctx.run_id, context=ctx, priority=EventPriority.INFO)
        )

        user_message = AgentMessage(role="user", content=prompt)
        await self.services.events.publish(
            MessageReceived(message=user_message, context=ctx, priority=EventPriority.INFO)
        )

        # Check existing messages from state store or initialize with system prompt
        state_dict = self.services.state_store.get_state()
        history: list[AgentMessage] = []

        # Add system prompt if not present
        history.append(AgentMessage(role="system", content=self.system_prompt))

        # Add stored session messages if any
        stored_msgs = state_dict.get("session", {}).get("messages", [])
        for m in stored_msgs:
            if isinstance(m, AgentMessage):
                history.append(m)
            elif isinstance(m, dict):
                history.append(AgentMessage(**m))

        # Include prompt user message if not already added
        if not history or history[-1].content != prompt or history[-1].role != "user":
            history.append(user_message)

        # Memory search
        if self.services.memory:
            try:
                memories = await self.services.memory.search(prompt, limit=5, context=ctx)
                if memories:
                    await self.services.events.publish(
                        MemoryRetrieved(query=prompt, items=memories, context=ctx)
                    )
                    mem_context = "\n".join(f"- {m.content}" for m in memories)
                    history.insert(
                        1,
                        AgentMessage(
                            role="system",
                            content=f"Relevant Memory Context:\n{mem_context}",
                        ),
                    )
            except Exception as e:
                logger.warning("runtime_engine.memory_search_failed", error=str(e))

        # Tools discovery
        tool_metadatas = []
        if self.services.executor and hasattr(self.services.executor, "list_tool_metadata"):
            tool_metadatas = self.services.executor.list_tool_metadata()

        # Planner invocation
        if self.services.planner:
            try:
                plan = await self.services.planner.create_plan(
                    goal=prompt,
                    history=history,
                    tools=tool_metadatas,
                    context=ctx,
                )
                await self.services.events.publish(
                    PlanCreated(plan=plan, context=ctx, priority=EventPriority.INFO)
                )
            except Exception as e:
                logger.warning("runtime_engine.planner_failed", error=str(e))

        turn_count = 0
        final_output = ""

        try:
            while turn_count < self.max_turns:
                turn_count += 1
                logger.info("runtime_engine.turn", turn=turn_count, max_turns=self.max_turns)

                response = await self.services.llm.generate_response(
                    messages=history,
                    tools=tool_metadatas if tool_metadatas else None,
                    context=ctx,
                )

                if response.content:
                    assistant_msg = AgentMessage(role="assistant", content=response.content)
                    history.append(assistant_msg)
                    await self.services.events.publish(
                        MessageSent(message=assistant_msg, context=ctx, priority=EventPriority.INFO)
                    )
                    final_output = response.content

                if not response.tool_calls:
                    # Engine finished execution
                    await self.services.events.publish(
                        RuntimeStopped(runtime_id=ctx.run_id, reason="normal", context=ctx)
                    )
                    return RunResult(
                        final_output=final_output,
                        turn_count=turn_count,
                        metadata={"run_id": ctx.run_id, "trace_id": ctx.trace_id},
                    )

                # Tool Calls Execution Loop
                for tool_call in response.tool_calls:
                    curr_call: ToolCall | None = tool_call

                    # Pre-execution Middleware pipeline
                    for mw in self.middleware:
                        if curr_call is not None:
                            curr_call = await mw.before_tool_execute(curr_call, context=ctx)

                    if curr_call is None:
                        logger.warning("runtime_engine.tool_call_cancelled_by_middleware", tool=tool_call.name)
                        continue

                    await self.services.events.publish(
                        ToolStarted(tool_call=curr_call, context=ctx, priority=EventPriority.INFO)
                    )

                    # Execute tool call
                    if self.services.executor:
                        tool_result = await self.services.executor.execute_tool(curr_call, context=ctx)
                    else:
                        tool_result = ToolResult(
                            tool_call_id=curr_call.id,
                            success=False,
                            output="",
                            error="No executor configured in services",
                        )

                    # Post-execution Middleware pipeline
                    for mw in self.middleware:
                        tool_result = await mw.after_tool_execute(curr_call, tool_result, context=ctx)

                    if tool_result.success:
                        await self.services.events.publish(
                            ToolFinished(tool_call=curr_call, result=tool_result, context=ctx)
                        )
                    else:
                        await self.services.events.publish(
                            ToolFailed(
                                tool_call=curr_call,
                                error=tool_result.error or "Execution failed",
                                context=ctx,
                            )
                        )

                    # Append tool result to history
                    tool_output_msg = AgentMessage(
                        role="tool",
                        content=tool_result.output or tool_result.error or "",
                        tool_call_id=curr_call.id,
                        name=curr_call.name,
                    )
                    history.append(tool_output_msg)

            # Reached max turns limit
            await self.services.events.publish(
                RuntimeStopped(runtime_id=ctx.run_id, reason="max_turns_exceeded", context=ctx)
            )
            return RunResult(
                final_output=final_output,
                turn_count=turn_count,
                metadata={"warning": "max_turns_exceeded", "run_id": ctx.run_id},
            )

        except Exception as e:
            logger.error("runtime_engine.error", error=str(e), run_id=ctx.run_id)
            await self.services.events.publish(
                RuntimeStopped(runtime_id=ctx.run_id, reason="error", context=ctx)
            )
            raise
