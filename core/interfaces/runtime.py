from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.result import RunResult


class RuntimeEngineInterface(ABC):
    @abstractmethod
    async def run(
        self,
        prompt: str,
        context: ExecutionContext | None = None,
    ) -> RunResult:
        """Run prompt through agent runtime."""
        pass
