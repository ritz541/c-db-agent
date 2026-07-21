from abc import ABC, abstractmethod
from typing import Any
from core.events.base import Event


class StateStoreInterface(ABC):
    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Get current state dictionary representation."""
        pass

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """Update internal state in response to an event."""
        pass
