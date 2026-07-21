import asyncio
import random
import time
import pytest

from agent.builder import AgentBuilder
from container.services import RuntimeServices
from core.events.domain import (
    StepCancelled,
    StepFailed,
    StepFinished,
    StepScheduled,
    StepStarted,
)
from core.models.context import CancellationToken, ExecutionContext
from core.models.planning import Plan, PlanStep
from core.models.tool import ToolCall, ToolResult
from runtime.events.bus import EventBus
from runtime.execution.tool_executor import ToolExecutor
from runtime.scheduler.dag_scheduler import DAGScheduler
from runtime.state.store import StateStore


class MockSlowExecutor(ToolExecutor):
    """Executor that simulates tool delay for testing concurrency and ordering."""

    def __init__(self, delay_map: dict[str, float] | None = None, default_delay: float = 0.05) -> None:
        super().__init__()
        self.delay_map = delay_map or {}
        self.default_delay = default_delay
        self.execution_log: list[str] = []
        self.active_count = 0
        self.max_observed_concurrency = 0

    async def execute_tool(self, tool_call: ToolCall, context: ExecutionContext | None = None) -> ToolResult:
        self.active_count += 1
        if self.active_count > self.max_observed_concurrency:
            self.max_observed_concurrency = self.active_count

        delay = self.delay_map.get(tool_call.name, self.default_delay)
        await asyncio.sleep(delay)

        self.execution_log.append(tool_call.name)
        self.active_count -= 1

        if tool_call.arguments.get("fail", False):
            return ToolResult(
                tool_call_id=tool_call.id,
                success=False,
                output="",
                error=f"Error executing {tool_call.name}",
            )

        return ToolResult(
            tool_call_id=tool_call.id,
            success=True,
            output=f"Result of {tool_call.name}",
        )


@pytest.mark.asyncio
async def test_parallel_execution_speedup():
    """Verify independent steps execute concurrently within bounded time."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor(default_delay=0.1)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=8)

    # 5 independent steps, each taking 0.1s. Sequential = 0.5s. Parallel <= 0.25s.
    steps = [
        PlanStep(step_id=i, description=f"step_{i}", tool_name=f"tool_{i}")
        for i in range(1, 6)
    ]
    plan = Plan(plan_id="plan_parallel", goal="test speedup", steps=steps)

    start_time = time.monotonic()
    results = await scheduler.execute_plan(plan)
    elapsed = time.monotonic() - start_time

    assert plan.is_complete()
    assert len(results) == 5
    assert elapsed < 0.3, f"Expected parallel speedup < 0.3s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_dag_dependency_resolution():
    """Verify dependent steps wait for prerequisite completion."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor(default_delay=0.02)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=4)

    # DAG structure: Step 1 -> Step 2 -> Step 3
    steps = [
        PlanStep(step_id=1, description="Step 1", tool_name="tool_1"),
        PlanStep(step_id=2, description="Step 2", tool_name="tool_2", depends_on=[1]),
        PlanStep(step_id=3, description="Step 3", tool_name="tool_3", depends_on=[2]),
    ]
    plan = Plan(plan_id="plan_deps", goal="test deps", steps=steps)

    results = await scheduler.execute_plan(plan)

    assert plan.is_complete()
    assert [s.status for s in plan.steps] == ["completed", "completed", "completed"]
    assert executor.execution_log == ["tool_1", "tool_2", "tool_3"]


@pytest.mark.asyncio
async def test_branch_failure_policy_propagation():
    """Verify 'all', 'any', and 'ignore_failures' policies."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor(default_delay=0.01)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services)

    # Step 1 fails, Step 2 succeeds
    steps = [
        PlanStep(step_id=1, description="Step 1", tool_name="tool_1", arguments={"fail": True}),
        PlanStep(step_id=2, description="Step 2", tool_name="tool_2"),
        # Step 3 depends on [1, 2] with policy "all" -> should cancel
        PlanStep(step_id=3, description="Step 3", tool_name="tool_3", depends_on=[1, 2], dependency_policy="all"),
        # Step 4 depends on [1, 2] with policy "any" -> should execute
        PlanStep(step_id=4, description="Step 4", tool_name="tool_4", depends_on=[1, 2], dependency_policy="any"),
        # Step 5 depends on [1] with policy "ignore_failures" -> should execute
        PlanStep(step_id=5, description="Step 5", tool_name="tool_5", depends_on=[1], dependency_policy="ignore_failures"),
    ]
    plan = Plan(plan_id="plan_policy", goal="test policy", steps=steps)

    results = await scheduler.execute_plan(plan)

    step_status_map = {s.step_id: s.status for s in plan.steps}
    assert step_status_map[1] == "failed"
    assert step_status_map[2] == "completed"
    assert step_status_map[3] == "cancelled"
    assert step_status_map[4] == "completed"
    assert step_status_map[5] == "completed"


@pytest.mark.asyncio
async def test_resource_concurrency_limits():
    """Verify 100 independent nodes never exceed max_concurrent_tasks = 8."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor(default_delay=0.01)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    max_limit = 8
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=max_limit)

    steps = [
        PlanStep(step_id=i, description=f"step_{i}", tool_name=f"tool_{i}")
        for i in range(1, 101)
    ]
    plan = Plan(plan_id="plan_100_nodes", goal="test max limit", steps=steps)

    results = await scheduler.execute_plan(plan)

    assert plan.is_complete()
    assert len(results) == 100
    assert executor.max_observed_concurrency <= max_limit


@pytest.mark.asyncio
async def test_atomic_state_consistency():
    """Verify concurrent state writes with asyncio.Lock maintain deterministic state."""
    event_bus = EventBus()
    state_store = StateStore()
    state_store.register(event_bus)

    executor = MockSlowExecutor(default_delay=0.01)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=16)

    steps = [
        PlanStep(step_id=i, description=f"step_{i}", tool_name=f"tool_{i}")
        for i in range(1, 51)
    ]
    plan = Plan(plan_id="plan_atomic", goal="test atomicity", steps=steps)

    await scheduler.execute_plan(plan)

    final_state = state_store.get_state()
    tools_history = final_state["tools"]["history"]
    assert len(tools_history) == 50
    assert final_state["tools"]["tool_success_count"] == 50


@pytest.mark.asyncio
async def test_deterministic_message_ordering():
    """Verify parallel tool calls with random finish delays preserve exact LLM tool_calls order in ConversationHistory."""
    class VariableDelayExecutor(ToolExecutor):
        async def execute_tool(self, tool_call: ToolCall, context: ExecutionContext | None = None) -> ToolResult:
            # Random finish delay between 0.01s and 0.05s
            await asyncio.sleep(random.uniform(0.01, 0.05))
            return ToolResult(tool_call_id=tool_call.id, success=True, output=f"Result for {tool_call.name}")

    class MockLLMProvider:
        async def generate_response(self, messages, tools=None, context=None):
            class Response:
                content = "Running parallel tools"
                tool_calls = [
                    ToolCall(id="tc_1", name="first_tool", arguments={}),
                    ToolCall(id="tc_2", name="second_tool", arguments={}),
                    ToolCall(id="tc_3", name="third_tool", arguments={}),
                    ToolCall(id="tc_4", name="fourth_tool", arguments={}),
                ]
            return Response()

    builder = AgentBuilder()
    agent = (
        builder.with_llm(MockLLMProvider())
        .with_executor(VariableDelayExecutor())
        .with_max_turns(1)
        .build()
    )

    # Run for 1 turn
    res = await agent.run("Execute tools")

    # Retrieve conversation messages from state_store
    messages = agent.services.state_store.session_state.messages
    tool_messages = [m for m in messages if m.role == "tool"]

    assert len(tool_messages) == 4
    assert [m.tool_call_id for m in tool_messages] == ["tc_1", "tc_2", "tc_3", "tc_4"]
    assert [m.name for m in tool_messages] == ["first_tool", "second_tool", "third_tool", "fourth_tool"]


@pytest.mark.asyncio
async def test_scheduler_event_invariant_trace():
    """Verify event trace sequence: StepScheduled -> StepStarted -> StepFinished."""
    event_bus = EventBus()
    state_store = StateStore()

    events_captured = []

    async def log_event(evt):
        events_captured.append(evt)

    event_bus.subscribe(StepScheduled, log_event)
    event_bus.subscribe(StepStarted, log_event)
    event_bus.subscribe(StepFinished, log_event)

    executor = MockSlowExecutor(default_delay=0.01)
    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services)

    steps = [PlanStep(step_id=1, description="Step 1", tool_name="tool_1")]
    plan = Plan(plan_id="plan_events", goal="test events", steps=steps)

    await scheduler.execute_plan(plan)

    event_types = [type(e) for e in events_captured]
    assert event_types == [StepScheduled, StepStarted, StepFinished]


@pytest.mark.asyncio
async def test_cancellation_and_resumption_recovery():
    """Verify cancellation halts pending steps, and re-submitting resumes from pending steps."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor(default_delay=0.1)

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=1)

    steps = [
        PlanStep(step_id=1, description="Step 1", tool_name="tool_1"),
        PlanStep(step_id=2, description="Step 2", tool_name="tool_2", depends_on=[1]),
    ]
    plan = Plan(plan_id="plan_resume", goal="test resume", steps=steps)

    ctx = ExecutionContext()
    ctx.cancellation_token.request_cancellation()

    # Executing with cancelled token should mark steps as cancelled
    results_cancelled = await scheduler.execute_plan(plan, context=ctx)
    assert plan.steps[0].status == "cancelled"

    # Reset token and status to test resumption from step 1
    ctx.cancellation_token = CancellationToken()
    plan.steps[0].status = "pending"

    # Now execute step 1 to completion
    results_step1 = await scheduler.execute_plan(plan, context=ctx)
    assert plan.steps[0].status == "completed"
    assert plan.steps[1].status == "completed"


@pytest.mark.asyncio
async def test_unmatched_tool_name_defaults_to_custom_step():
    """Verify steps without tool_name execute safely as custom steps without failing on missing tool."""
    event_bus = EventBus()
    state_store = StateStore()
    executor = MockSlowExecutor()

    services = RuntimeServices(
        llm=None,
        events=event_bus,
        state_store=state_store,
        task_manager=None,
        executor=executor,
    )
    scheduler = DAGScheduler(services=services, max_concurrent_tasks=2)

    steps = [
        PlanStep(step_id=1, description="Process goal: greeting", tool_name=None, node_type="custom"),
    ]
    plan = Plan(plan_id="plan_no_tool", goal="greeting", steps=steps)

    results = await scheduler.execute_plan(plan)
    assert plan.steps[0].status == "completed"
    assert plan.steps[0].completed is True
