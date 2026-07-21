import inspect
from typing import Awaitable, Callable
import structlog

from core.events.base import Event, EventPriority
from core.interfaces.event_bus import EventBusInterface

logger = structlog.get_logger(__name__)


class Subscription:

    def __init__(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None] | None],
        priority: EventPriority = EventPriority.INFO,
    ) -> None:
        self.event_type = event_type
        self.handler = handler
        self.priority = priority


class EventBus(EventBusInterface):
    """Priority-filtered EventBus with subscriber exception containment."""

    def __init__(self, min_priority: EventPriority = EventPriority.DEBUG) -> None:
        self.min_priority = min_priority
        self._subscriptions: list[Subscription] = []

    def subscribe(
        self,
        event_type: type[Event],
        handler: Callable[[Event], Awaitable[None] | None],
        priority: EventPriority = EventPriority.INFO,
    ) -> None:
        sub = Subscription(event_type=event_type, handler=handler, priority=priority)
        self._subscriptions.append(sub)

    async def publish(self, event: Event) -> None:
        if event.priority < self.min_priority:
            return

        matching_subs = [
            sub
            for sub in self._subscriptions
            if isinstance(event, sub.event_type) and sub.priority >= self.min_priority
        ]

        # Sort subscriptions by priority descending (higher priority runs first)
        matching_subs.sort(key=lambda s: int(s.priority), reverse=True)

        for sub in matching_subs:
            try:
                res = sub.handler(event)
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                logger.error(
                    "Error in event handler",
                    event_type=type(event).__name__,
                    handler=getattr(sub.handler, "__name__", str(sub.handler)),
                    error=str(e),
                )
