from abc import ABC, abstractmethod
from typing import Any
from core.models.context import ExecutionContext
from core.models.planning import Plan
from core.models.tool import ToolResult


class DAGSchedulerInterface(ABC):
    @abstractmethod
    async def execute_plan(
        self,
        plan: Plan,
        context: ExecutionContext | None = None,
    ) -> dict[int, ToolResult | Any]:
        """Execute DAG plan concurrently based on step dependencies and concurrency limits."""
        pass
