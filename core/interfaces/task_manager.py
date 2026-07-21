from abc import ABC, abstractmethod
from typing import Any, Coroutine
from core.models.context import ExecutionContext


class TaskManagerInterface(ABC):
    @abstractmethod
    async def spawn_task(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
        context: ExecutionContext | None = None,
    ) -> str:
        """Spawn background task and return task_id."""
        pass

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running background task."""
        pass

    @abstractmethod
    def list_tasks(self) -> list[dict[str, Any]]:
        """List active background tasks."""
        pass
