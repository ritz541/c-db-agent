from abc import ABC, abstractmethod
from typing import Any
from core.models.context import ExecutionContext
from core.models.tool import ToolMetadata, ToolResult


class ToolInterface(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return metadata describing tool."""
        pass

    @abstractmethod
    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> ToolResult | str | dict[str, Any]:
        """Execute tool logic."""
        pass
