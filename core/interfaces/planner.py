from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.planning import Plan
from core.models.tool import ToolMetadata


class PlannerInterface(ABC):
    @abstractmethod
    async def create_plan(
        self,
        goal: str,
        history: list[AgentMessage],
        tools: list[ToolMetadata],
        context: ExecutionContext | None = None,
    ) -> Plan:
        """Create execution plan."""
        pass
