from abc import ABC, abstractmethod
from typing import Awaitable, Callable
from core.events.base import Event, EventPriority


class EventBusInterface(ABC):
    @abstractmethod
    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None] | None],
        priority: EventPriority = EventPriority.INFO,
    ) -> None:
        """Subscribe handler to event type."""
        pass

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish event to subscribers."""
        pass
