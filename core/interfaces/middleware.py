from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult


class MiddlewareInterface(ABC):
    @abstractmethod
    async def before_tool_execute(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolCall | None:
        """Pre-hook before tool execution. Return modified tool_call or None to cancel."""
        pass

    @abstractmethod
    async def after_tool_execute(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        """Post-hook after tool execution. Return modified result."""
        pass
