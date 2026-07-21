from typing import Any


class AgentError(Exception):
    """Base exception for all agent runtime errors."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.metadata = metadata or {}


class ToolExecutionError(AgentError):
    """Raised when a tool execution fails."""

    pass


class LLMProviderError(AgentError):
    """Raised when an LLM provider request fails."""

    pass


class MemoryError(AgentError):
    """Raised when memory storage or retrieval fails."""

    pass


class PlanningError(AgentError):
    """Raised when planning fails."""

    pass


class TaskError(AgentError):
    """Raised when background task execution fails or is cancelled."""

    pass


class StateError(AgentError):
    """Raised when state mutation or lookup fails."""

    pass


class MiddlewareError(AgentError):
    """Raised when a middleware execution fails."""

    pass
