import inspect
from typing import Any
import structlog

from core.errors.exceptions import ToolExecutionError
from core.interfaces.executor import ExecutorInterface
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult

logger = structlog.get_logger(__name__)


class ToolExecutor(ExecutorInterface):
    """Tool Executor implementation of ExecutorInterface."""

    def __init__(self, tools: list[ToolInterface] | None = None) -> None:
        self._tools: dict[str, ToolInterface] = {}
        if tools:
            for tool in tools:
                self.register_tool(tool)

    def register_tool(self, tool: ToolInterface) -> None:
        name = tool.metadata.name
        self._tools[name] = tool
        logger.info("tool_executor.registered", tool_name=name)

    def get_tool(self, name: str) -> ToolInterface | None:
        return self._tools.get(name)

    def list_tool_metadata(self) -> list[Any]:
        return [tool.metadata for tool in self._tools.values()]

    async def execute_tool(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if not tool:
            err_msg = f"Tool '{tool_call.name}' is not registered."
            logger.error("tool_executor.not_found", tool_name=tool_call.name)
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=err_msg,
            )

        try:
            logger.info("tool_executor.executing", tool_name=tool_call.name)
            args = tool_call.arguments or {}
            res = tool.execute(context=context, **args)
            if inspect.isawaitable(res):
                res = await res

            if isinstance(res, ToolResult):
                return res
            elif isinstance(res, dict):
                return ToolResult(
                    tool_call_id=tool_call.id,
                    success=res.get("success", True),
                    output=str(res.get("output", res)),
                    error=res.get("error"),
                    metadata=res.get("metadata", {}),
                )
            else:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    success=True,
                    output=str(res),
                )
        except Exception as e:
            err_str = f"Error executing tool '{tool_call.name}': {e}"
            logger.error("tool_executor.failed", tool_name=tool_call.name, error=str(e))
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=err_str,
            )
