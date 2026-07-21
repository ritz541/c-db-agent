import structlog
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult
from runtime.middleware.base import RuntimeMiddleware

logger = structlog.get_logger(__name__)


class LoggingMiddleware(RuntimeMiddleware):
    """Tracing and logging middleware."""

    async def before_tool_execute(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolCall | None:
        logger.info(
            "middleware.before_tool_execute",
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            trace_id=context.trace_id if context else None,
        )
        return tool_call

    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        logger.info(
            "middleware.after_tool_execute",
            tool_name=tool_call.name,
            success=result.success,
            duration_ms=result.metadata.get("duration_ms"),
            trace_id=context.trace_id if context else None,
        )
        return result
