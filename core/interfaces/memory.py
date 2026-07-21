from abc import ABC, abstractmethod
from core.models.context import ExecutionContext
from core.models.memory import MemoryItem


class MemoryProviderInterface(ABC):
    @abstractmethod
    async def store(
        self,
        item: MemoryItem,
        context: ExecutionContext | None = None,
    ) -> bool:
        """Store memory item."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 5,
        context: ExecutionContext | None = None,
    ) -> list[MemoryItem]:
        """Search memory items by query."""
        pass
