import time
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult
from runtime.middleware.base import RuntimeMiddleware


class TimingMiddleware(RuntimeMiddleware):
    """Middleware measuring tool execution duration."""

    def __init__(self) -> None:
        self._start_times: dict[str, float] = {}

    async def before_tool_execute(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolCall | None:
        self._start_times[tool_call.id] = time.perf_counter()
        return tool_call

    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        start_time = self._start_times.pop(tool_call.id, None)
        if start_time is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            result.metadata["duration_ms"] = round(duration_ms, 2)
        return result
