"""
Tests for memory_service.py — QdrantMemoryService and MemoryService ABC.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from datetime import datetime, timezone
from typing import Optional

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    MatchAny,
    PointStruct,
    ScoredPoint,
)

from core.memory_service import MemoryService, QdrantMemoryService


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_qdrant_client():
    """Mock QdrantClient."""
    client = MagicMock()
    # Mock get_collections to return empty (so collection will be created)
    collections_response = MagicMock()
    collections_response.collections = []
    client.get_collections.return_value = collections_response
    return client


@pytest.fixture
def service(mock_qdrant_client):
    """Create a QdrantMemoryService with a mocked client and embedding."""
    with patch("core.memory_service.QdrantClient", return_value=mock_qdrant_client):
        svc = QdrantMemoryService(
            url="http://mock:6333",
            api_key="test-key",
            collection_name="test_memories",
            vector_size=3,
            embedding_provider="openrouter",
            embedding_model="test/model",
        )
        svc._initialized = True
        svc._embed_async = AsyncMock(return_value=[0.1, 0.2, 0.3])
        yield svc


def make_scored_point(
    point_id: str,
    score: float = 0.95,
    payload: Optional[dict] = None,
    vector: Optional[list[float]] = None,
) -> ScoredPoint:
    """Helper to create a mock ScoredPoint."""
    point = MagicMock(spec=ScoredPoint)
    point.id = point_id
    point.score = score
    point.payload = payload or {}
    point.vector = vector or [0.1, 0.2, 0.3]
    return point


# ── MemoryService ABC ────────────────────────────────────────────

class TestMemoryServiceABC:
    def test_abstract_class_cannot_instantiate(self):
        """Must subclass and implement all abstract methods."""
        with pytest.raises(TypeError):
            MemoryService()

    def test_incomplete_subclass_raises(self):
        """Missing abstract methods should raise TypeError."""
        class Incomplete(MemoryService):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass_works(self):
        """All abstract methods implemented = works."""
        class Full(MemoryService):
            async def store(self, content, memory_type, importance, tags, user_id, session_id, source="extraction"):
                return "id-1"
            async def retrieve(self, query, user_id, top_k=5, memory_types=None):
                return []
            async def update(self, target_memory_id, new_content, new_tags=None):
                return True
            async def delete(self, memory_id):
                return True
            async def consolidate(self):
                return 0

        inst = Full()
        assert inst is not None


# ── _make_filter ─────────────────────────────────────────────────

class TestMakeFilter:
    def test_user_id_only(self, service):
        """Filter with only user_id should return a Filter with one condition."""
        result = service._make_filter(user_id="user-1")
        assert isinstance(result, Filter)
        assert len(result.must) == 1
        assert result.must[0].key == "user_id"
        assert result.must[0].match.value == "user-1"

    def test_user_id_and_single_memory_type(self, service):
        """Filter with user_id and a single memory_type."""
        result = service._make_filter(user_id="user-1", memory_types=["semantic"])
        assert len(result.must) == 2
        assert result.must[1].key == "memory_type"
        assert result.must[1].match.any == ["semantic"]

    def test_user_id_and_multiple_memory_types(self, service):
        """Filter with user_id and multiple memory_types should use MatchAny."""
        result = service._make_filter(user_id="user-1", memory_types=["semantic", "episodic"])
        assert len(result.must) == 2
        assert isinstance(result.must[1].match, MatchAny)
        assert result.must[1].match.any == ["semantic", "episodic"]

    def test_empty_user_id_and_no_memory_types(self, service):
        """Empty user_id with no memory_types should return filter with one condition."""
        result = service._make_filter(user_id="", memory_types=None)
        assert result is not None
        assert len(result.must) == 1
        assert result.must[0].key == "user_id"
        assert result.must[0].match.value == ""

    def test_none_memory_types_omitted(self, service):
        """None memory_types should not add a condition."""
        result = service._make_filter(user_id="user-1", memory_types=None)
        assert len(result.must) == 1
        assert result.must[0].key == "user_id"


# ── _point_to_dict ───────────────────────────────────────────────

class TestPointToDict:
    def test_full_payload(self, service):
        """Convert a ScoredPoint with full payload to dict."""
        point = make_scored_point(
            point_id="mem-1",
            score=0.95,
            payload={
                "content": "User likes Rust",
                "memory_type": "semantic",
                "importance": 8,
                "tags": ["rust", "programming"],
                "user_id": "user-1",
                "session_id": "sess-1",
                "created_at": "2026-01-01T00:00:00",
                "last_accessed": "2026-01-01T00:00:00",
                "times_retrieved": 3,
                "source": "extraction",
            },
        )
        result = service._point_to_dict(point)
        assert result["memory_id"] == "mem-1"
        assert result["content"] == "User likes Rust"
        assert result["memory_type"] == "semantic"
        assert result["importance"] == 8
        assert result["score"] == 0.95
        assert result["times_retrieved"] == 3

    def test_empty_payload(self, service):
        """Convert a ScoredPoint with no payload to dict with defaults."""
        point = make_scored_point(point_id="mem-2", payload={})
        result = service._point_to_dict(point)
        assert result["content"] == ""
        assert result["memory_type"] == "semantic"  # default
        assert result["importance"] == 0
        assert result["tags"] == []

    def test_missing_score_field(self, service):
        """Handle ScoredPoint without score attribute gracefully."""
        point = make_scored_point(point_id="mem-3", score=0.0)
        # Remove score attribute to test fallback
        del point.score
        result = service._point_to_dict(point)
        assert result["score"] == 0.0


# ── store ────────────────────────────────────────────────────────

class TestStore:
    @pytest.mark.asyncio
    async def test_store_returns_memory_id(self, service, mock_qdrant_client):
        """Store should create a PointStruct and call upsert, returning the memory_id."""
        memory_id = await service.store(
            content="User likes Python",
            memory_type="semantic",
            importance=7,
            tags=["python"],
            user_id="user-1",
            session_id="sess-1",
        )
        assert isinstance(memory_id, str)
        assert len(memory_id) > 0

        # Verify upsert was called with the right collection
        mock_qdrant_client.upsert.assert_called_once()
        call_kwargs = mock_qdrant_client.upsert.call_args[1]
        assert call_kwargs["collection_name"] == "test_memories"
        points = call_kwargs["points"]
        assert len(points) == 1
        assert isinstance(points[0], PointStruct)
        assert points[0].id == memory_id
        assert points[0].payload["content"] == "User likes Python"

    @pytest.mark.asyncio
    async def test_store_initializes_collection_if_needed(self, mock_qdrant_client):
        """Store should call _ensure_collection if not initialized."""
        with patch("core.memory_service.QdrantClient", return_value=mock_qdrant_client), \
             patch.object(QdrantMemoryService, "_embed_async", new_callable=AsyncMock, return_value=[0.1, 0.2, 0.3]):
            svc = QdrantMemoryService(
                url="http://mock:6333",
                api_key="test-key",
                collection_name="test_memories",
            )
            svc._initialized = False  # Force re-init

            # Mock _ensure_collection to avoid real Qdrant calls
            svc._ensure_collection = MagicMock()

            await svc.store(
                content="Test",
                memory_type="semantic",
                importance=5,
                tags=[],
                user_id="u1",
                session_id="s1",
            )

            svc._ensure_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_with_source(self, service, mock_qdrant_client):
        """Store should pass the source field to payload."""
        await service.store(
            content="Manual entry",
            memory_type="episodic",
            importance=3,
            tags=[],
            user_id="u1",
            session_id="s1",
            source="manual",
        )
        payload = mock_qdrant_client.upsert.call_args[1]["points"][0].payload
        assert payload["source"] == "manual"
        assert payload["times_retrieved"] == 0


# ── retrieve ─────────────────────────────────────────────────────

class TestRetrieve:
    @pytest.mark.asyncio
    async def test_retrieve_returns_memories(self, service, mock_qdrant_client):
        """Retrieve should query points and return formatted memories."""
        # Mock query_points to return results
        mock_point = make_scored_point(
            point_id="mem-1",
            score=0.92,
            payload={
                "content": "User likes Go",
                "memory_type": "semantic",
                "importance": 6,
                "tags": ["go"],
                "user_id": "user-1",
            },
        )
        query_response = MagicMock()
        query_response.points = [mock_point]
        mock_qdrant_client.query_points.return_value = query_response

        results = await service.retrieve(query="What language?", user_id="user-1", top_k=5)

        assert len(results) == 1
        assert results[0]["content"] == "User likes Go"
        assert results[0]["memory_id"] == "mem-1"
        assert results[0]["times_retrieved"] == 1  # Incremented from 0 in payload

    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, service, mock_qdrant_client):
        """Retrieve with no matches should return empty list."""
        query_response = MagicMock()
        query_response.points = []
        mock_qdrant_client.query_points.return_value = query_response

        results = await service.retrieve(query="nothing", user_id="user-1")
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_passes_filter(self, service, mock_qdrant_client):
        """Retrieve should pass the correct filter to query_points."""
        query_response = MagicMock()
        query_response.points = []
        mock_qdrant_client.query_points.return_value = query_response

        await service.retrieve(query="test", user_id="user-1", memory_types=["semantic"])

        call_kwargs = mock_qdrant_client.query_points.call_args[1]
        assert call_kwargs["collection_name"] == "test_memories"
        assert call_kwargs["limit"] == 5
        # Should have a query_filter with user_id and memory_type conditions
        qfilter = call_kwargs["query_filter"]
        assert isinstance(qfilter, Filter)
        assert len(qfilter.must) == 2

    @pytest.mark.asyncio
    async def test_retrieve_increments_access_count(self, service, mock_qdrant_client):
        """Retrieve should increment the times_retrieved count on returned memories."""
        mock_point = make_scored_point(
            point_id="mem-1",
            score=0.8,
            payload={
                "content": "test",
                "memory_type": "semantic",
                "importance": 5,
                "tags": [],
                "times_retrieved": 3,
            },
        )
        query_response = MagicMock()
        query_response.points = [mock_point]
        mock_qdrant_client.query_points.return_value = query_response

        results = await service.retrieve(query="test", user_id="u1")
        
        assert len(results) == 1
        assert results[0]["times_retrieved"] == 4  # Incremented from 3 to 4


# ── update ───────────────────────────────────────────────────────

class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_existing_memory_direct_retrieve(self, service, mock_qdrant_client):
        """Update should regenerate embedding and upsert via direct retrieve."""
        mock_point = make_scored_point(
            point_id="mem-1",
            payload={
                "content": "Old content",
                "memory_type": "semantic",
                "importance": 5,
                "tags": ["old"],
                "user_id": "u1",
                "session_id": "s1",
            },
            vector=[0.1, 0.2, 0.3],
        )
        mock_qdrant_client.retrieve.return_value = [mock_point]

        result = await service.update(
            target_memory_id="mem-1",
            new_content="Updated content",
            new_tags=["updated"],
        )

        assert result is True
        mock_qdrant_client.retrieve.assert_called_once()
        mock_qdrant_client.upsert.assert_called_once()
        upserted = mock_qdrant_client.upsert.call_args[1]["points"][0]
        assert upserted.id == "mem-1"
        assert upserted.payload["content"] == "Updated content"
        assert upserted.payload["tags"] == ["updated"]
        assert "updated_at" in upserted.payload

    @pytest.mark.asyncio
    async def test_update_existing_memory_scroll_fallback(self, service, mock_qdrant_client):
        """Update should fall back to scroll if direct retrieve returns empty."""
        mock_point = make_scored_point(
            point_id="mem-1",
            payload={
                "content": "Old content",
                "memory_type": "semantic",
                "importance": 5,
                "tags": ["old"],
            },
            vector=[0.1, 0.2, 0.3],
        )
        mock_qdrant_client.retrieve.return_value = []
        mock_qdrant_client.scroll.return_value = ([mock_point], None)

        result = await service.update(
            target_memory_id="mem-1",
            new_content="Updated content",
        )

        assert result is True
        mock_qdrant_client.retrieve.assert_called_once()
        mock_qdrant_client.scroll.assert_called_once()
        mock_qdrant_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent_memory(self, service, mock_qdrant_client):
        """Update on non-existent memory should return False."""
        mock_qdrant_client.retrieve.return_value = []
        mock_qdrant_client.scroll.return_value = ([], None)
        result = await service.update(target_memory_id="nonexistent", new_content="nope")
        assert result is False
        mock_qdrant_client.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_preserves_tags_when_not_provided(self, service, mock_qdrant_client):
        """Update without new_tags should keep existing tags."""
        mock_point = make_scored_point(
            point_id="mem-1",
            payload={"content": "Old", "tags": ["keep"], "memory_type": "semantic", "importance": 5, "user_id": "u1", "session_id": "s1"},
            vector=[0.1, 0.2, 0.3],
        )
        mock_qdrant_client.retrieve.return_value = [mock_point]

        await service.update(target_memory_id="mem-1", new_content="Updated")
        upserted = mock_qdrant_client.upsert.call_args[1]["points"][0]
        assert upserted.payload["tags"] == ["keep"]  # Unchanged

# ── delete ───────────────────────────────────────────────────────

class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing_memory_direct_retrieve(self, service, mock_qdrant_client):
        """Delete should retrieve point by ID directly and delete it."""
        mock_point = make_scored_point(point_id="mem-1")
        mock_qdrant_client.retrieve.return_value = [mock_point]

        result = await service.delete(memory_id="mem-1")
        assert result is True
        mock_qdrant_client.retrieve.assert_called_once()
        mock_qdrant_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_existing_memory_scroll_fallback(self, service, mock_qdrant_client):
        """Delete should fall back to scroll if retrieve returns empty."""
        mock_point = make_scored_point(point_id="mem-1")
        mock_qdrant_client.retrieve.return_value = []
        mock_qdrant_client.scroll.return_value = ([mock_point], None)

        result = await service.delete(memory_id="mem-1")
        assert result is True
        mock_qdrant_client.retrieve.assert_called_once()
        mock_qdrant_client.scroll.assert_called_once()
        mock_qdrant_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_memory(self, service, mock_qdrant_client):
        """Delete on non-existent memory should return False."""
        mock_qdrant_client.retrieve.return_value = []
        mock_qdrant_client.scroll.return_value = ([], None)
        result = await service.delete(memory_id="nonexistent")
        assert result is False
        mock_qdrant_client.delete.assert_not_called()

# ── consolidate ──────────────────────────────────────────────────

class TestConsolidate:
    @pytest.mark.asyncio
    async def test_consolidate_returns_zero(self, service):
        """Consolidate is a placeholder, should return 0."""
        result = await service.consolidate()
        assert result == 0


# ── _embed_sync ──────────────────────────────────────────────────

class TestEmbedSync:
    def test_model_string_constructed_correctly(self, service):
        """_embed_sync should construct provider/model string."""
        with patch("core.memory_service.litellm.embedding") as mock_embed:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
            mock_embed.return_value = mock_response

            service._embed_sync("test text")

            mock_embed.assert_called_once()
            assert mock_embed.call_args[1]["model"] == "openrouter/test/model"
            assert mock_embed.call_args[1]["input"] == ["test text"]

    def test_model_string_without_provider(self):
        """When provider is empty, model should be used as-is."""
        svc = QdrantMemoryService.__new__(QdrantMemoryService)
        svc.embedding_provider = ""
        svc.embedding_model = "bare-model"
        svc.embedding_api_key = None

        with patch("core.memory_service.litellm.embedding") as mock_embed:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_embed.return_value = mock_response

            svc._embed_sync("test")
            assert mock_embed.call_args[1]["model"] == "bare-model"

    def test_model_string_without_model(self):
        """When model is empty, should pass empty string."""
        svc = QdrantMemoryService.__new__(QdrantMemoryService)
        svc.embedding_provider = "openrouter"
        svc.embedding_model = ""
        svc.embedding_api_key = None

        with patch("core.memory_service.litellm.embedding") as mock_embed:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_embed.return_value = mock_response

            svc._embed_sync("test")
            assert mock_embed.call_args[1]["model"] == ""

    def test_api_key_passed_when_set(self):
        """API key should be passed to litellm when configured."""
        svc = QdrantMemoryService.__new__(QdrantMemoryService)
        svc.embedding_provider = "openrouter"
        svc.embedding_model = "test/model"
        svc.embedding_api_key = "sk-test-key"

        with patch("core.memory_service.litellm.embedding") as mock_embed:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_embed.return_value = mock_response

            svc._embed_sync("test")
            assert mock_embed.call_args[1]["api_key"] == "sk-test-key"

    def test_api_key_omitted_when_not_set(self, service):
        """API key should NOT be passed to litellm when not configured."""
        service.embedding_api_key = None
        with patch("core.memory_service.litellm.embedding") as mock_embed:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_embed.return_value = mock_response

            service._embed_sync("test")
            assert "api_key" not in mock_embed.call_args[1]


# ── _ensure_collection ───────────────────────────────────────────

class TestEnsureCollection:
    def test_creates_collection_when_missing(self, mock_qdrant_client):
        """Should create collection and payload indexes when it doesn't exist."""
        with patch("core.memory_service.QdrantClient", return_value=mock_qdrant_client):
            svc = QdrantMemoryService(
                url="http://mock:6333",
                api_key="test-key",
                collection_name="new_collection",
                vector_size=3,
            )
            svc._ensure_collection()

            mock_qdrant_client.create_collection.assert_called_once()
            mock_qdrant_client.create_payload_index.assert_called()
            assert svc._initialized is True

    def test_skips_creation_when_exists(self, mock_qdrant_client):
        """Should skip collection creation if it already exists."""
        # Mock existing collections
        collections_response = MagicMock()
        existing_collection = MagicMock()
        existing_collection.name = "existing_collection"
        collections_response.collections = [existing_collection]
        mock_qdrant_client.get_collections.return_value = collections_response

        with patch("core.memory_service.QdrantClient", return_value=mock_qdrant_client):
            svc = QdrantMemoryService(
                url="http://mock:6333",
                api_key="test-key",
                collection_name="existing_collection",
            )
            svc._ensure_collection()

            mock_qdrant_client.create_collection.assert_not_called()
            assert svc._initialized is True

    def test_handles_get_collections_error(self, mock_qdrant_client):
        """If get_collections fails, should attempt to create."""
        mock_qdrant_client.get_collections.side_effect = Exception("Connection error")

        with patch("core.memory_service.QdrantClient", return_value=mock_qdrant_client):
            svc = QdrantMemoryService(
                url="http://mock:6333",
                api_key="test-key",
                collection_name="error_collection",
            )
            svc._ensure_collection()

            # Should still try to create
            mock_qdrant_client.create_collection.assert_called_once()
