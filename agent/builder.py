from typing import Any

from container.services import RuntimeServices
from core.interfaces.event_bus import EventBusInterface
from core.interfaces.executor import ExecutorInterface
from core.interfaces.llm import LLMProviderInterface
from core.interfaces.memory import MemoryProviderInterface
from core.interfaces.planner import PlannerInterface
from core.interfaces.state_store import StateStoreInterface
from core.interfaces.task_manager import TaskManagerInterface
from core.interfaces.tool import ToolInterface
from core.models.context import ExecutionContext
from core.models.result import RunResult
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.bus import EventBus
from runtime.events.subscriber import BaseSubscriber
from runtime.execution.tool_executor import ToolExecutor
from runtime.llm.litellm_provider import LiteLLMProvider
from runtime.middleware.base import RuntimeMiddleware
from runtime.planning.direct_planner import DirectPlanner
from runtime.state.store import StateStore
from runtime.tasks.task_manager import TaskManager


class AgentBuilder:
    """Fluent Builder for configuring and building an Agent Runtime Instance."""

    def __init__(self) -> None:
        self._llm: LLMProviderInterface | None = None
        self._memory: MemoryProviderInterface | None = None
        self._planner: PlannerInterface | None = None
        self._executor: ToolExecutor | None = None
        self._event_bus: EventBusInterface | None = None
        self._state_store: StateStoreInterface | None = None
        self._task_manager: TaskManagerInterface | None = None
        self._middleware: list[RuntimeMiddleware] = []
        self._subscribers: list[BaseSubscriber] = []
        self._tools: list[ToolInterface] = []
        self._config: dict[str, Any] = {}
        self._system_prompt: str = "You are a helpful AI assistant."
        self._max_turns: int = 10

    def with_llm(self, llm: LLMProviderInterface | str) -> "AgentBuilder":
        if isinstance(llm, str):
            self._llm = LiteLLMProvider(model=llm)
        else:
            self._llm = llm
        return self

    def with_memory(self, memory: MemoryProviderInterface) -> "AgentBuilder":
        self._memory = memory
        return self

    def with_planner(self, planner: PlannerInterface) -> "AgentBuilder":
        self._planner = planner
        return self

    def with_executor(self, executor: ToolExecutor) -> "AgentBuilder":
        self._executor = executor
        return self

    def with_event_bus(self, event_bus: EventBusInterface) -> "AgentBuilder":
        self._event_bus = event_bus
        return self

    def with_state_store(self, state_store: StateStoreInterface) -> "AgentBuilder":
        self._state_store = state_store
        return self

    def with_task_manager(self, task_manager: TaskManagerInterface) -> "AgentBuilder":
        self._task_manager = task_manager
        return self

    def with_middleware(self, middleware: RuntimeMiddleware) -> "AgentBuilder":
        self._middleware.append(middleware)
        return self

    def with_subscriber(self, subscriber: BaseSubscriber) -> "AgentBuilder":
        self._subscribers.append(subscriber)
        return self

    def with_tool(self, tool: ToolInterface) -> "AgentBuilder":
        self._tools.append(tool)
        return self

    def with_system_prompt(self, system_prompt: str) -> "AgentBuilder":
        self._system_prompt = system_prompt
        return self

    def with_max_turns(self, max_turns: int) -> "AgentBuilder":
        self._max_turns = max_turns
        return self

    def with_config(self, key: str, value: Any) -> "AgentBuilder":
        self._config[key] = value
        return self

    def build(self) -> "Agent":
        event_bus = self._event_bus or EventBus()
        state_store = self._state_store or StateStore()

        if isinstance(state_store, StateStore):
            state_store.register(event_bus)

        task_manager = self._task_manager or TaskManager(event_bus=event_bus)
        llm = self._llm or LiteLLMProvider()
        planner = self._planner or DirectPlanner(llm_provider=llm)

        executor = self._executor or ToolExecutor()
        for t in self._tools:
            executor.register_tool(t)

        for sub in self._subscribers:
            sub.register(event_bus)

        services = RuntimeServices(
            llm=llm,
            events=event_bus,
            state_store=state_store,
            task_manager=task_manager,
            memory=self._memory,
            planner=planner,
            executor=executor,
            config=self._config,
        )

        engine = RuntimeEngine(
            services=services,
            middleware=self._middleware,
            max_turns=self._max_turns,
            system_prompt=self._system_prompt,
        )

        return Agent(engine=engine, services=services)


class Agent:
    """Agent API Facade wrapping RuntimeEngine and RuntimeServices container."""

    def __init__(self, engine: RuntimeEngine, services: RuntimeServices) -> None:
        self.engine = engine
        self.services = services

    @classmethod
    def builder(cls) -> AgentBuilder:
        return AgentBuilder()

    async def run(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> RunResult:
        return await self.engine.run(prompt=prompt, context=context)
