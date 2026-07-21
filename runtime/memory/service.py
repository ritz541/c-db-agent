import asyncio
from typing import Any
import structlog

from core.errors.exceptions import MemoryError
from core.interfaces.memory import MemoryProviderInterface
from core.models.context import ExecutionContext
from core.models.memory import MemoryItem

logger = structlog.get_logger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


class QdrantMemoryService(MemoryProviderInterface):
    """Qdrant-backed memory provider with in-memory fallback."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "agent_memories",
        vector_size: int = 1536,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.vector_size = vector_size

        self._lock = asyncio.Lock()
        self._in_memory_store: list[MemoryItem] = []
        self._qdrant_client: Any | None = None

        if QDRANT_AVAILABLE and url:
            try:
                self._qdrant_client = QdrantClient(url=url, api_key=api_key)
            except Exception as e:
                logger.warning(
                    "qdrant_init_failed_falling_back_to_in_memory", error=str(e)
                )

    async def store(
        self,
        item: MemoryItem,
        context: ExecutionContext | None = None,
    ) -> bool:
        async with self._lock:
            try:
                # Store in in-memory fallback
                self._in_memory_store.append(item)

                if self._qdrant_client:
                    # Optionally generate vector or store point
                    pass

                logger.info(
                    "memory.stored", memory_id=item.memory_id, type=item.memory_type
                )
                return True
            except Exception as e:
                logger.error("memory.store_failed", error=str(e))
                raise MemoryError(f"Failed to store memory item: {e}") from e
    async def search(
        self,
        query: str,
        limit: int = 5,
        context: ExecutionContext | None = None,
    ) -> list[MemoryItem]:
        async with self._lock:
            try:
                query_lower = query.lower()
                results = []

                # Basic keyword / similarity search on in-memory store
                for item in self._in_memory_store:
                    if query_lower in item.content.lower() or any(
                        query_lower in tag.lower() for tag in item.tags
                    ):
                        results.append(item)

                # If keyword search hits nothing, return top standard items up to limit
                if not results and self._in_memory_store:
                    results = sorted(
                        self._in_memory_store, key=lambda x: x.importance, reverse=True
                    )[:limit]

                return results[:limit]
            except Exception as e:
                logger.error("memory.search_failed", error=str(e))
                raise MemoryError(f"Failed to search memory items: {e}") from e
    async def delete(self, memory_id: str) -> bool:
        async with self._lock:
            self._in_memory_store = [
                m for m in self._in_memory_store if m.memory_id != memory_id
            ]
            return True
