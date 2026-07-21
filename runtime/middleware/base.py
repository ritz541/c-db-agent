from core.interfaces.middleware import MiddlewareInterface
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult


class RuntimeMiddleware(MiddlewareInterface):
    """Base class for runtime pre/post execution middleware."""

    async def before_tool_execute(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolCall | None:
        return tool_call

    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        return result
