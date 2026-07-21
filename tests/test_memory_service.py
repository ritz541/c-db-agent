from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.models.memory import MemoryItem
from runtime.memory.service import QdrantMemoryService


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()
    collections_response = MagicMock()
    collections_response.collections = []
    client.get_collections.return_value = collections_response
    return client


@pytest.fixture
def service(mock_qdrant_client):
    with patch(
        "runtime.memory.service.QdrantClient", return_value=mock_qdrant_client
    ):
        svc = QdrantMemoryService(
            url="http://mock:6333",
            api_key="test-key",
            collection_name="test_memories",
            vector_size=3,
        )
        yield svc


class TestMemoryService:

    @pytest.mark.asyncio
    async def test_store_memory(self, service):
        item = MemoryItem(
            content="User prefers Python over Rust",
            memory_type="preference",
            importance=0.8,
            tags=["python", "preference"],
        )
        success = await service.store(item)
        assert success is True

    @pytest.mark.asyncio
    async def test_search_memory(self, service):
        item = MemoryItem(
            content="User prefers Python over Rust",
            memory_type="preference",
            importance=0.8,
            tags=["python", "preference"],
        )
        await service.store(item)

        results = await service.search("Python", limit=5)
        assert len(results) >= 1
        assert results[0].content == item.content

    @pytest.mark.asyncio
    async def test_delete_memory(self, service):
        item = MemoryItem(
            content="Temporary note",
            memory_type="note",
        )
        await service.store(item)
        assert len(await service.search("Temporary", limit=5)) == 1

        await service.delete(item.memory_id)
        assert len(await service.search("Temporary", limit=5)) == 0
