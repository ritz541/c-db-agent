import asyncio
import os
import tempfile
import pytest
from pydantic import ValidationError

from container.services import RuntimeServices
from core.events.domain import (
    MessageReceived,
    MessageSent,
    PlanCreated,
    StepFinished,
    StepScheduled,
    StepStarted,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from core.export.plan_exporter import MermaidExporter, PlanExporter
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.metrics import SchedulerMetrics, StepMetrics
from core.models.planning import Plan, PlanStep
from core.models.recording import RunRecord
from core.models.tool import ToolCall, ToolResult
from runtime.events.bus import EventBus
from runtime.execution.tool_executor import ToolExecutor
from runtime.recording.recorder import ExecutionRecorder
from runtime.recording.replay import ReplayPlayer
from runtime.scheduler.dag_scheduler import DAGScheduler
from runtime.state.models import StateSnapshot
from runtime.state.reducer import reduce_state
from runtime.state.store import StateStore


# Mock executor with known delays for metric verification
class MockDelayExecutor(ToolExecutor):
    def __init__(self, delay_map: dict[str, float] | None = None, default_delay: float = 0.05) -> None:
        super().__init__()
        self.delay_map = delay_map or {}
        self.default_delay = default_delay

    async def execute_tool(self, tool_call: ToolCall, context: ExecutionContext | None = None) -> ToolResult:
        delay = self.delay_map.get(tool_call.name, self.default_delay)
        await asyncio.sleep(delay)
        return ToolResult(
            tool_call_id=tool_call.id,
            success=True,
            output=f"Executed {tool_call.name} in {delay}s",
        )


@pytest.mark.asyncio
async def test_immutable_state_store_and_snapshot_history():
    """Verification Check 1: Immutable State Reducer and snapshot history sequence."""
    store = StateStore(session_id="test_session", user_id="test_user")
    bus = EventBus()
    store.register(bus)

    # Initial history has sequence 0
    history = store.get_history()
    assert len(history) == 1
    assert history[0].sequence_number == 0

    # Publish events
    ctx = ExecutionContext(session_id="test_session", user_id="test_user", run_id="run_100")
    msg1 = AgentMessage(role="user", content="Hello agent")
    await bus.publish(MessageReceived(message=msg1, context=ctx))

    msg2 = AgentMessage(role="assistant", content="Hello user")
    await bus.publish(MessageSent(message=msg2, context=ctx))

    history_after = store.get_history()
    assert len(history_after) == 3
    assert history_after[0].sequence_number == 0
    assert history_after[1].sequence_number == 1
    assert history_after[2].sequence_number == 2
    assert len(store.get_snapshot().session.messages) == 2

    # Verify immutability error when modifying snapshot directly
    latest_snapshot = store.get_snapshot()
    with pytest.raises((ValidationError, TypeError)):
        latest_snapshot.sequence_number = 999  # Frozen model error


@pytest.mark.asyncio
async def test_state_reducer_determinism_property():
    """Verification Check 2: Determinism Property Test by replaying events."""
    events = [
        RuntimeStarted(runtime_id="run_det_1"),
        MessageReceived(message=AgentMessage(role="user", content="Test query")),
        ToolStarted(tool_call=ToolCall(id="t1", name="calc", arguments={"expr": "2+2"})),
        ToolFinished(
            tool_call=ToolCall(id="t1", name="calc", arguments={"expr": "2+2"}),
            result=ToolResult(tool_call_id="t1", success=True, output="4"),
        ),
        RuntimeStopped(runtime_id="run_det_1", reason="completed"),
    ]

    dummy_store = StateStore()
    initial_snapshot = dummy_store.get_snapshot()

    # Run pass 1
    snap_pass_1 = initial_snapshot
    for evt in events:
        snap_pass_1 = reduce_state(snap_pass_1, evt)

    # Run pass 2
    snap_pass_2 = initial_snapshot
    for evt in events:
        snap_pass_2 = reduce_state(snap_pass_2, evt)

    assert snap_pass_1.sequence_number == snap_pass_2.sequence_number == 5
    assert snap_pass_1.run.status == snap_pass_2.run.status == "completed"
    assert snap_pass_1.tools.tool_success_count == snap_pass_2.tools.tool_success_count == 1
    assert snap_pass_1.model_dump(exclude={"timestamp"}) == snap_pass_2.model_dump(exclude={"timestamp"})


@pytest.mark.asyncio
async def test_scheduler_metrics_telemetry():
    """Verification Check 3: Execute a 4-step DAG with known delays, verify metrics."""
    # Step 1 -> Step 2 & Step 3 (parallel) -> Step 4
    # Delays: Step 1 (0.05s), Step 2 (0.10s), Step 3 (0.05s), Step 4 (0.05s)
    # Critical path: Step 1 + Step 2 + Step 4 = 0.05 + 0.10 + 0.05 = 0.20s
    plan = Plan(
        plan_id="plan_metrics",
        goal="Test DAG metrics calculation",
        steps=[
            PlanStep(step_id=1, description="Step 1", tool_name="tool_1"),
            PlanStep(step_id=2, description="Step 2", tool_name="tool_2", depends_on=[1]),
            PlanStep(step_id=3, description="Step 3", tool_name="tool_3", depends_on=[1]),
            PlanStep(step_id=4, description="Step 4", tool_name="tool_4", depends_on=[2, 3]),
        ],
    )

    delay_map = {
        "tool_1": 0.05,
        "tool_2": 0.10,
        "tool_3": 0.05,
        "tool_4": 0.05,
    }
    executor = MockDelayExecutor(delay_map=delay_map)
    bus = EventBus()
    state_store = StateStore()
    services = RuntimeServices(
        llm=None,
        events=bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=4)
    ctx = ExecutionContext(run_id="run_dag_metrics")
    results = await scheduler.execute_plan(plan, context=ctx)

    assert len(results) == 4
    assert "metrics" in plan.metadata

    metrics = plan.metadata["metrics_object"]
    assert isinstance(metrics, SchedulerMetrics)
    assert metrics.run_id == "run_dag_metrics"
    assert len(metrics.step_metrics) == 4

    # Verify critical path duration is ~0.20s (Step 1 + Step 2 + Step 4)
    assert 0.18 <= metrics.critical_path_duration <= 0.35
    assert metrics.peak_concurrency >= 1
    assert 0.0 <= metrics.parallel_efficiency <= 1.0
    assert metrics.average_wait_time >= 0.0
    assert metrics.average_execution_time > 0.0


def test_mermaid_plan_exporter():
    """Verification Check 4: Plan Mermaid Exporter generates valid graph TD string."""
    plan = Plan(
        plan_id="plan_mermaid",
        goal="Test export",
        steps=[
            PlanStep(step_id=1, description="Fetch data", status="completed"),
            PlanStep(step_id=2, description="Process data", depends_on=[1], status="running"),
            PlanStep(step_id=3, description="Save report", depends_on=[2], status="pending"),
        ],
    )

    mermaid_str = MermaidExporter.export(plan)
    assert mermaid_str.startswith("graph TD")
    assert 'step_1["Step 1: Fetch data"]' in mermaid_str
    assert 'step_2["Step 2: Process data"]' in mermaid_str
    assert 'step_3["Step 3: Save report"]' in mermaid_str
    assert "step_1 --> step_2" in mermaid_str
    assert "step_2 --> step_3" in mermaid_str
    assert "style step_1 fill:#d4edda,stroke:#28a745" in mermaid_str  # completed
    assert "style step_2 fill:#fff3cd,stroke:#ffc107" in mermaid_str  # running
    assert "style step_3 fill:#ffffff,stroke:#6c757d" in mermaid_str  # pending

    # Facade checks
    facade_str = PlanExporter.export(plan, format="mermaid")
    assert facade_str == mermaid_str

    instance_str = PlanExporter(plan).to_mermaid()
    assert instance_str == mermaid_str


@pytest.mark.asyncio
async def test_execution_recorder_and_replay_player():
    """Verification Check 5: Record execution, export to RunRecord, replay to reconstructed StateStore."""
    bus = EventBus()
    state_store = StateStore(session_id="rec_session")
    state_store.register(bus)

    run_id = "run_rec_test"
    recorder = ExecutionRecorder(run_id=run_id, event_bus=bus, state_store=state_store)

    ctx = ExecutionContext(run_id=run_id, session_id="rec_session")
    await bus.publish(RuntimeStarted(runtime_id=run_id))
    await bus.publish(MessageReceived(message=AgentMessage(role="user", content="Calculate 10+20"), context=ctx))
    await bus.publish(
        ToolStarted(
            tool_call=ToolCall(id="tc_1", name="add", arguments={"a": 10, "b": 20}),
            context=ctx,
        )
    )
    await bus.publish(
        ToolFinished(
            tool_call=ToolCall(id="tc_1", name="add", arguments={"a": 10, "b": 20}),
            result=ToolResult(tool_call_id="tc_1", success=True, output="30"),
            context=ctx,
        )
    )
    await bus.publish(MessageSent(message=AgentMessage(role="assistant", content="Result is 30"), context=ctx))
    await bus.publish(RuntimeStopped(runtime_id=run_id, reason="completed"))

    # Obtain recorded RunRecord
    record = recorder.get_record()
    assert record.run_id == run_id
    assert len(record.events) == 6
    assert len(record.tool_calls) == 2

    # Save to temp file and load back
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        file_path = f.name
    try:
        recorder.save_to_file(file_path)

        # Feed to ReplayPlayer
        player = ReplayPlayer(file_path)
        replayed_store = player.replay()

        # Verify replayed state matches original state_store exactly
        orig_state = state_store.get_state()
        replayed_state = replayed_store.get_state()

        assert replayed_state["run"]["status"] == orig_state["run"]["status"] == "completed"
        assert replayed_state["tools"]["tool_success_count"] == orig_state["tools"]["tool_success_count"] == 1
        assert len(replayed_state["session"]["messages"]) == len(orig_state["session"]["messages"]) == 2

        # Verify step-by-step history length matches
        assert len(replayed_store.get_history()) == len(state_store.get_history())
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
