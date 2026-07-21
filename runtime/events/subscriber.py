from abc import ABC, abstractmethod
from core.events.base import Event
from core.interfaces.event_bus import EventBusInterface


class BaseSubscriber(ABC):
    """Abstract base class for event subscribers."""

    @abstractmethod
    def register(self, event_bus: EventBusInterface) -> None:
        """Register subscriber event handlers with the event bus."""
        pass
