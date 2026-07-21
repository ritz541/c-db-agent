import json
import time
from typing import Any
from pydantic import BaseModel
from core.events.base import Event
from core.events.domain import PlanCreated, ToolFailed, ToolFinished, ToolStarted
from core.events.system import RuntimeStarted
from core.interfaces.event_bus import EventBusInterface
from core.models.recording import RunRecord
from runtime.state.store import StateStore


class ExecutionRecorder:
    """Records event stream, state snapshots, plan, and tool calls during a run bound by run_id."""

    def __init__(
        self,
        run_id: str,
        event_bus: EventBusInterface | None = None,
        state_store: StateStore | None = None,
    ) -> None:
        self.run_id = run_id
        self.event_bus = event_bus
        self.state_store = state_store
        self.recorded_events: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.plan: dict[str, Any] | None = None
        self.metrics: dict[str, Any] | None = None
        self.tool_calls: list[dict[str, Any]] = []
        self._subscribed = False

        if self.event_bus and not self._subscribed:
            self.start()

    def start(self) -> None:
        """Subscribe recorder to event bus for all events."""
        if self.event_bus and not self._subscribed:
            self.event_bus.subscribe(Event, self.handle_event)
            self._subscribed = True

    def stop(self) -> None:
        """Stop recording events."""
        self._subscribed = False

    async def handle_event(self, event: Event) -> None:
        """Record incoming event if it matches run_id or if recorder is unbound (run_id='')."""
        if not self._subscribed:
            return

        # Check run_id scoping
        event_run_id = None
        if hasattr(event, "context") and event.context and getattr(event.context, "run_id", None):
            event_run_id = event.context.run_id
        elif isinstance(event, RuntimeStarted):
            event_run_id = event.runtime_id

        if self.run_id and event_run_id and event_run_id != self.run_id:
            return

        event_data = event.model_dump() if isinstance(event, BaseModel) else getattr(event, "__dict__", {})
        record_entry = {
            "event_type": event.__class__.__name__,
            "data": event_data,
            "timestamp": time.time(),
        }
        self.recorded_events.append(record_entry)

        if isinstance(event, PlanCreated):
            self.plan = event.plan.model_dump() if hasattr(event.plan, "model_dump") else event.plan
            if hasattr(event.plan, "metadata") and isinstance(event.plan.metadata, dict):
                if "metrics" in event.plan.metadata:
                    self.metrics = event.plan.metadata["metrics"]

        if isinstance(event, (ToolStarted, ToolFinished, ToolFailed)):
            self.tool_calls.append(record_entry)

    def record_snapshot(self, snapshot: Any) -> None:
        """Record a StateSnapshot object or dictionary."""
        snapshot_dict = snapshot.model_dump() if isinstance(snapshot, BaseModel) else dict(snapshot)
        self.snapshots.append(snapshot_dict)

    def get_record(self) -> RunRecord:
        """Compile and return final RunRecord."""
        snapshots_list = list(self.snapshots)
        if not snapshots_list and self.state_store:
            snapshots_list = [snap.model_dump() for snap in self.state_store.get_history()]

        plan_dict = self.plan
        metrics_dict = self.metrics

        if self.state_store and self.state_store.session_state.active_plan:
            active_plan = self.state_store.session_state.active_plan
            if not plan_dict:
                plan_dict = active_plan.model_dump()
            if not metrics_dict and "metrics" in active_plan.metadata:
                metrics_dict = active_plan.metadata["metrics"]

        return RunRecord(
            run_id=self.run_id,
            timestamp=time.time(),
            events=self.recorded_events,
            snapshots=snapshots_list,
            plan=plan_dict,
            metrics=metrics_dict,
            tool_calls=self.tool_calls,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation of RunRecord."""
        return self.get_record().model_dump()

    def save_to_file(self, path: str) -> None:
        """Save RunRecord JSON payload to specified file path."""
        record = self.get_record()
        with open(path, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))

    @classmethod
    def load_from_file(cls, path: str) -> RunRecord:
        """Load RunRecord from JSON file path."""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return RunRecord.model_validate_json(content)
