from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.tool import ToolCall, ToolResult


class ExecutorInterface(ABC):
    @abstractmethod
    async def execute_tool(
        self,
        tool_call: ToolCall,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        """Execute a tool call."""
        pass
