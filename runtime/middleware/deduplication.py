import json
from typing import Any
import structlog

from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult
from runtime.middleware.base import RuntimeMiddleware

logger = structlog.get_logger(__name__)


class ToolDeduplicationMiddleware(RuntimeMiddleware):
    """Intercepts and suppresses duplicate tool executions with identical arguments within a run session."""

    def __init__(self) -> None:
        self._executed_cache: dict[str, ToolResult] = {}

    def _get_cache_key(self, tool_call: ToolCall, context: ExecutionContext | None) -> str:
        run_id = context.run_id if (context and getattr(context, "run_id", None)) else "default"
        try:
            args_str = json.dumps(tool_call.arguments or {}, sort_keys=True)
        except Exception:
            args_str = str(tool_call.arguments)
        return f"{run_id}:{tool_call.name}:{args_str}"

    async def before_tool_execute(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolCall | None:
        cache_key = self._get_cache_key(tool_call, context)
        if cache_key in self._executed_cache:
            logger.info(
                "middleware.deduplication.duplicate_tool_call_intercepted",
                tool_name=tool_call.name,
                run_id=getattr(context, "run_id", None),
            )
            return None
        return tool_call

    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        cache_key = self._get_cache_key(tool_call, context)
        if cache_key not in self._executed_cache:
            self._executed_cache[cache_key] = result
        return result

    def get_cached_result(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolResult | None:
        cache_key = self._get_cache_key(tool_call, context)
        return self._executed_cache.get(cache_key)
