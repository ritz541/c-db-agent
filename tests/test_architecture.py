import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from container.services import RuntimeServices
from core.events.base import Event, EventPriority
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
from core.interfaces.executor import ExecutorInterface
from core.interfaces.llm import LLMProviderInterface
from core.interfaces.memory import MemoryProviderInterface
from core.interfaces.planner import PlannerInterface
from core.interfaces.runtime import RuntimeEngineInterface
from core.interfaces.state_store import StateStoreInterface
from core.interfaces.task_manager import TaskManagerInterface
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.llm import LLMResponse
from core.models.message import AgentMessage
from core.models.planning import Plan
from core.models.result import RunResult
from core.models.tool import ToolCall, ToolMetadata, ToolResult
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.bus import EventBus
from runtime.execution.tool_executor import ToolExecutor
from runtime.llm.litellm_provider import LiteLLMProvider
from runtime.memory.service import QdrantMemoryService
from runtime.planning.direct_planner import DirectPlanner
from runtime.state.store import StateStore
from runtime.tasks.task_manager import TaskManager


class TestEventBusArchitecture:

    @pytest.mark.asyncio
    async def test_priority_filtering_and_order(self):
        bus = EventBus(min_priority=EventPriority.INFO)
        execution_order = []

        def low_priority_handler(event: Event):
            execution_order.append("low")

        def high_priority_handler(event: Event):
            execution_order.append("high")

        bus.subscribe(Event, low_priority_handler, priority=EventPriority.INFO)
        bus.subscribe(Event, high_priority_handler, priority=EventPriority.ERROR)

        evt = Event(priority=EventPriority.INFO)
        await bus.publish(evt)

        assert execution_order == ["high", "low"]

    @pytest.mark.asyncio
    async def test_subscriber_exception_containment(self):
        bus = EventBus()
        called_second = False

        def failing_handler(event: Event):
            raise RuntimeError("Subscriber crash!")

        def succeeding_handler(event: Event):
            nonlocal called_second
            called_second = True

        bus.subscribe(Event, failing_handler)
        bus.subscribe(Event, succeeding_handler)

        # Should not raise exception
        await bus.publish(Event())
        assert called_second is True


class TestDomainModelArchitecture:

    def test_tool_metadata_capabilities(self):
        meta = ToolMetadata(
            name="db_query",
            description="Query database",
            capabilities={"database", "sql", "unsafe"},
        )
        assert "database" in meta.capabilities
        assert "sql" in meta.capabilities
    def test_tool_metadata_rich_planner_hints(self):
        meta = ToolMetadata(
            name="browser",
            description="Automate browser",
            capabilities={"browser", "network"},
            estimated_cost="medium",
            estimated_latency="slow",
            destructive=False,
            requires_confirmation=True,
            supports_streaming=True,
        )
        assert meta.estimated_cost == "medium"
        assert meta.estimated_latency == "slow"
        assert meta.requires_confirmation is True
        assert meta.supports_streaming is True


    def test_metadata_carrying(self):
        result = ToolResult(
            tool_call_id="call_1",
            success=True,
            output="ok",
            metadata={"duration_ms": 12.5, "provider": "local"},
        )
        assert result.metadata["duration_ms"] == 12.5
        assert result.metadata["provider"] == "local"


class TestExecutionContextArchitecture:

    def test_trace_id_propagation(self):
        ctx = ExecutionContext()
        assert ctx.trace_id is not None
        assert ctx.session_id is not None
        assert ctx.run_id is not None
    def test_cancellation_token(self):
        ctx = ExecutionContext()
        assert ctx.cancellation_token.is_cancelled is False
        ctx.cancellation_token.request_cancellation()
        assert ctx.cancellation_token.is_cancelled is True


class TestStateStoreArchitecture:

    @pytest.mark.asyncio
    async def test_reactive_state_updates(self):
        bus = EventBus()
        store = StateStore(session_id="test_session")
        store.register(bus)

        ctx = ExecutionContext(session_id="test_session")

        # Emit MessageReceived
        msg = AgentMessage(role="user", content="Hello state store!")
        await bus.publish(MessageReceived(message=msg, context=ctx))

        state = store.get_state()
        assert len(state["session"]["messages"]) == 1
        assert state["session"]["messages"][0]["content"] == "Hello state store!"

        # Emit ToolStarted & ToolFinished
        tc = ToolCall(id="c1", name="calculate", arguments={"expression": "1+1"})
        await bus.publish(ToolStarted(tool_call=tc, context=ctx))
        tr = ToolResult(tool_call_id="c1", success=True, output="2")
        await bus.publish(ToolFinished(tool_call=tc, result=tr, context=ctx))

        state = store.get_state()
        assert state["tools"]["tool_calls_count"] == 1
        assert state["tools"]["tool_success_count"] == 1


class TestTaskManagerArchitecture:

    @pytest.mark.asyncio
    async def test_task_lifecycle_and_cancellation(self):
        bus = EventBus()
        tm = TaskManager(event_bus=bus)

        async def slow_work():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        ctx = ExecutionContext()
        task_id = await tm.spawn_task("slow_work", slow_work(), context=ctx)

        tasks = tm.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["status"] == "running"

        cancelled = await tm.cancel_task(task_id)
        assert cancelled is True

        tasks_after = tm.list_tasks()
        assert tasks_after[0]["status"] == "cancelled"


class TestContractCompliance:

    def test_interfaces_subclass_check(self):
        assert issubclass(LiteLLMProvider, LLMProviderInterface)
        assert issubclass(QdrantMemoryService, MemoryProviderInterface)
        assert issubclass(DirectPlanner, PlannerInterface)
        assert issubclass(ToolExecutor, ExecutorInterface)
        assert issubclass(RuntimeEngine, RuntimeEngineInterface)
        assert issubclass(EventBus, EventBusInterface)
        assert issubclass(StateStore, StateStoreInterface)
        assert issubclass(TaskManager, TaskManagerInterface)
