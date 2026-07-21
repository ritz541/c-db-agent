from abc import ABC, abstractmethod
from typing import Any
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.tool import ToolMetadata, ToolResult


class BaseTool(ToolInterface, ABC):
    """Base class for tools implementing core ToolInterface and supporting rich planner metadata."""

    def get_capabilities(self) -> set[str]:
        """Return capability tags (e.g. {'database', 'network', 'filesystem'})."""
        return set()

    def get_category(self) -> str:
        """Return tool category."""
        return "general"

    def get_estimated_cost(self) -> str:
        """Return estimated cost ('low', 'medium', 'high')."""
        return "low"

    def get_estimated_latency(self) -> str:
        """Return estimated latency ('fast', 'medium', 'slow')."""
        return "fast"

    def is_destructive(self) -> bool:
        """Return True if tool performs destructive operations."""
        return False

    def requires_confirmation(self) -> bool:
        """Return True if execution requires human confirmation."""
        return False

    def supports_streaming(self) -> bool:
        """Return True if tool supports output streaming."""
        return False

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.get_name(),
            description=self.get_description(),
            category=self.get_category(),
            capabilities=self.get_capabilities(),
            estimated_cost=self.get_estimated_cost(),
            estimated_latency=self.get_estimated_latency(),
            destructive=self.is_destructive(),
            requires_confirmation=self.requires_confirmation(),
            supports_streaming=self.supports_streaming(),
            parameters=self.get_parameters(),
        )

    @abstractmethod
    def get_name(self) -> str:
        """Return the tool name."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Return the tool description for the LLM."""
        pass

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return the parameter schema in OpenAI format."""
        pass

    @abstractmethod
    def execute(
        self,
        db_conn: Any = None,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> ToolResult | dict[str, Any] | str:
        """Execute tool logic."""
        pass

    def get_schema(self) -> dict[str, Any]:
        """Generate OpenAI tool schema for backward compatibility."""
        return {
            "type": "function",
            "function": {
                "name": self.get_name(),
                "description": self.get_description(),
                "parameters": self.get_parameters(),
            },
        }
