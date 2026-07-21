import asyncio
from typing import Any
from core.events.base import Event
from core.events.domain import (
    MessageReceived,
    MessageSent,
    PlanCreated,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from core.interfaces.event_bus import EventBusInterface
from core.interfaces.state_store import StateStoreInterface
from runtime.state.models import AgentSessionState, RunState, ToolExecutionState


class StateStore(StateStoreInterface):
    """Reactive StateStore keeping single source of truth updated from domain events."""

    def __init__(self, session_id: str = "default_session", user_id: str = "default_user") -> None:
        self._lock = asyncio.Lock()
        self.session_state = AgentSessionState(session_id=session_id, user_id=user_id)
        self.tool_state = ToolExecutionState()
        self.run_state = RunState()
    def register(self, event_bus: EventBusInterface) -> None:
        """Register state store handler with event bus for all events."""
        event_bus.subscribe(Event, self.handle_event)

    async def handle_event(self, event: Event) -> None:
        async with self._lock:
            if event.context and event.context.session_id:
                self.session_state.session_id = event.context.session_id
            if event.context and event.context.user_id:
                self.session_state.user_id = event.context.user_id
            if event.context and event.context.run_id:
                self.run_state.run_id = event.context.run_id

            if isinstance(event, (MessageReceived, MessageSent)):
                self.session_state.messages.append(event.message)
            elif isinstance(event, PlanCreated):
                self.session_state.active_plan = event.plan
            elif isinstance(event, ToolStarted):
                self.tool_state.tool_calls_count += 1
                self.run_state.current_step = f"Executing tool: {event.tool_call.name}"
            elif isinstance(event, ToolFinished):
                self.tool_state.tool_success_count += 1
                self.tool_state.history.append(
                    {
                        "tool_call_id": event.tool_call.id,
                        "name": event.tool_call.name,
                        "success": True,
                        "output": event.result.output,
                    }
                )
                self.run_state.current_step = None
            elif isinstance(event, ToolFailed):
                self.tool_state.tool_failure_count += 1
                self.tool_state.history.append(
                    {
                        "tool_call_id": event.tool_call.id,
                        "name": event.tool_call.name,
                        "success": False,
                        "error": event.error,
                    }
                )
                self.run_state.current_step = None
            elif isinstance(event, RuntimeStarted):
                self.run_state.status = "running"
                self.run_state.run_id = event.runtime_id
                self.run_state.turn_count = 0
                self.run_state.last_error = None
            elif isinstance(event, RuntimeStopped):
                if event.reason == "error":
                    self.run_state.status = "failed"
                else:
                    self.run_state.status = "completed"
    def get_state(self) -> dict[str, Any]:
        return {
            "session": self.session_state.model_dump(),
            "tools": self.tool_state.model_dump(),
            "run": self.run_state.model_dump(),
        }
