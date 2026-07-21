from typing import Any, Generator
from core.events.base import Event
from core.events.domain import (
    MessageReceived,
    MessageSent,
    PlanCreated,
    StepCancelled,
    StepFailed,
    StepFinished,
    StepScheduled,
    StepStarted,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from core.models.recording import RunRecord
from runtime.state.models import StateSnapshot
from runtime.state.reducer import reduce_state
from runtime.state.store import StateStore

EVENT_CLASS_MAP: dict[str, type[Event]] = {
    "MessageReceived": MessageReceived,
    "MessageSent": MessageSent,
    "PlanCreated": PlanCreated,
    "ToolStarted": ToolStarted,
    "ToolFinished": ToolFinished,
    "ToolFailed": ToolFailed,
    "RuntimeStarted": RuntimeStarted,
    "RuntimeStopped": RuntimeStopped,
    "StepScheduled": StepScheduled,
    "StepStarted": StepStarted,
    "StepFinished": StepFinished,
    "StepFailed": StepFailed,
    "StepCancelled": StepCancelled,
}


class ReplayPlayer:
    """Replays recorded event streams through the pure reduce_state reducer without LLM or tool side effects."""

    def __init__(self, record: RunRecord | dict[str, Any] | str) -> None:
        if isinstance(record, str):
            with open(record, "r", encoding="utf-8") as f:
                content = f.read()
            self.record = RunRecord.model_validate_json(content)
        elif isinstance(record, dict):
            self.record = RunRecord.model_validate(record)
        elif isinstance(record, RunRecord):
            self.record = record
        else:
            raise TypeError(f"Invalid record type: {type(record)}")

    def _reconstruct_event(self, entry: dict[str, Any] | Event) -> Event | None:
        if isinstance(entry, Event):
            return entry

        if isinstance(entry, dict):
            event_type = entry.get("event_type", "")
            data = entry.get("data", {})
            event_cls = EVENT_CLASS_MAP.get(event_type)
            if event_cls and isinstance(data, dict):
                try:
                    return event_cls.model_validate(data)
                except Exception:
                    return None
        return None

    def replay_step_by_step(self) -> Generator[tuple[Event, StateSnapshot], None, None]:
        """Generator that yields (event, snapshot) step-by-step during replay."""
        store = StateStore(session_id="replay_session")
        snapshot = store.get_snapshot()

        for entry in self.record.events:
            event = self._reconstruct_event(entry)
            if event is None:
                continue
            snapshot = reduce_state(snapshot, event)
            yield event, snapshot

    def replay(self) -> StateStore:
        """Replay recorded run and return reconstructed StateStore containing complete snapshot history."""
        store = StateStore(session_id="replay_session")

        for entry in self.record.events:
            event = self._reconstruct_event(entry)
            if event is None:
                continue
            # Synchronously update store state snapshot
            store._current_snapshot = reduce_state(store._current_snapshot, event)
            store._history.append(store._current_snapshot)

        return store
