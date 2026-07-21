import structlog

from core.events.base import Event
from core.interfaces.event_bus import EventBusInterface
from runtime.events.subscriber import BaseSubscriber

logger = structlog.get_logger(__name__)


class StructlogSubscriber(BaseSubscriber):
    """Structlog telemetry subscriber."""

    def register(self, event_bus: EventBusInterface) -> None:
        event_bus.subscribe(Event, self.on_event)

    def on_event(self, event: Event) -> None:
        event_name = type(event).__name__
        logger.info(
            f"event.{event_name}",
            priority=event.priority.name,
            event_id=event.event_id,
            trace_id=event.context.trace_id if event.context else None,
        )
