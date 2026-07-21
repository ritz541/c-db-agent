from abc import ABC, abstractmethod
from typing import Any
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.tool import ToolMetadata, ToolResult


class BaseTool(ToolInterface, ABC):
    """Base class for tools implementing core ToolInterface and supporting capabilities."""

    def get_capabilities(self) -> set[str]:
        """Return capability tags (e.g. {'database', 'network', 'filesystem'})."""
        return set()

    def get_category(self) -> str:
        """Return tool category."""
        return "general"

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.get_name(),
            description=self.get_description(),
            category=self.get_category(),
            capabilities=self.get_capabilities(),
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
