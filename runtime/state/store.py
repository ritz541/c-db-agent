import asyncio
from typing import Any
from core.events.base import Event
from core.interfaces.event_bus import EventBusInterface
from core.interfaces.state_store import StateStoreInterface
from runtime.state.models import AgentSessionState, RunState, StateSnapshot, ToolExecutionState
from runtime.state.reducer import reduce_state


class StateStore(StateStoreInterface):
    """Reactive StateStore keeping single source of truth updated from domain events using immutable StateSnapshots."""

    def __init__(self, session_id: str = "default_session", user_id: str = "default_user") -> None:
        initial_session = AgentSessionState(session_id=session_id, user_id=user_id)
        initial_tools = ToolExecutionState()
        initial_run = RunState()
        self._current_snapshot = StateSnapshot(
            run_id="",
            sequence_number=0,
            session=initial_session,
            tools=initial_tools,
            run=initial_run,
        )
        self._history: list[StateSnapshot] = [self._current_snapshot]

    @property
    def session_state(self) -> AgentSessionState:
        return self._current_snapshot.session

    @property
    def tool_state(self) -> ToolExecutionState:
        return self._current_snapshot.tools

    @property
    def run_state(self) -> RunState:
        return self._current_snapshot.run

    def register(self, event_bus: EventBusInterface) -> None:
        """Register state store handler with event bus for all events."""
        event_bus.subscribe(Event, self.handle_event)

    async def handle_event(self, event: Event) -> None:
        """Update internal state snapshot in response to an event using pure reducer."""
        self._current_snapshot = reduce_state(self._current_snapshot, event)
        self._history.append(self._current_snapshot)

    def get_snapshot(self) -> StateSnapshot:
        """Return the current immutable StateSnapshot."""
        return self._current_snapshot

    def get_history(self) -> list[StateSnapshot]:
        """Return the list of all historical StateSnapshots."""
        return list(self._history)

    def get_snapshot_at(self, sequence_number: int) -> StateSnapshot | None:
        """Return historical snapshot with matching sequence_number if found."""
        for snapshot in self._history:
            if snapshot.sequence_number == sequence_number:
                return snapshot
        return None

    def get_state(self) -> dict[str, Any]:
        """Return state dictionary representation of current snapshot."""
        return {
            "session": self._current_snapshot.session.model_dump(),
            "tools": self._current_snapshot.tools.model_dump(),
            "run": self._current_snapshot.run.model_dump(),
        }
