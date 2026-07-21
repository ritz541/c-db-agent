from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from core.interfaces.event_bus import EventBusInterface
from core.interfaces.executor import ExecutorInterface
from core.interfaces.llm import LLMProviderInterface
from core.interfaces.memory import MemoryProviderInterface
from core.interfaces.planner import PlannerInterface
from core.interfaces.state_store import StateStoreInterface
from core.interfaces.task_manager import TaskManagerInterface


class RuntimeServices(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    llm: LLMProviderInterface | Any
    events: EventBusInterface | Any
    state_store: StateStoreInterface | Any
    task_manager: TaskManagerInterface | Any
    memory: MemoryProviderInterface | Any = None
    planner: PlannerInterface | Any = None
    executor: ExecutorInterface | Any = None
    config: dict[str, Any] = Field(default_factory=dict)
