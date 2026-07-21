"""
Memory Service Layer

Abstract interface for memory storage and retrieval.
Default implementation uses Qdrant Cloud with Qwen3 embeddings.

Usage:
    service = QdrantMemoryService(url=..., api_key=...)
    await service.store(content="User prefers Rust", memory_type="semantic", ...)
    memories = await service.retrieve(query="What language does user prefer", top_k=5)
"""

from __future__ import annotations

import uuid
import asyncio
import structlog
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import litellm
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
    MatchValue,
    PointIdsList,
)


logger = structlog.get_logger()


class MemoryService(ABC):
    """Interface for memory storage and retrieval."""

    @abstractmethod
    async def store(
        self,
        content: str,
        memory_type: str,
        importance: int,
        tags: list[str],
        user_id: str,
        session_id: str,
        source: str = "extraction",
    ) -> str:
        """Store a new memory. Returns the memory_id."""
        ...

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """Retrieve relevant memories for a query. Returns list of {content, score, payload}."""
        ...

    @abstractmethod
    async def update(
        self,
        target_memory_id: str,
        new_content: str,
        new_tags: Optional[list[str]] = None,
    ) -> bool:
        """Update an existing memory by ID."""
        ...

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        ...

    @abstractmethod
    async def consolidate(self) -> int:
        """Consolidate duplicate/stale memories. Returns count of merged memories. Future use."""
        ...


class QdrantMemoryService(MemoryService):
    """Qdrant-backed memory service using Qwen3 embeddings via LiteLLM."""

    def __init__(
        self,
        url: str,
        api_key: str,
        collection_name: str = "agent_memory",
        vector_size: int = 4096,
        embedding_model: str = "qwen/qwen3-embedding-8b",
        distance: Distance = Distance.COSINE,
    ):
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.embedding_model = embedding_model
        self.distance = distance
        self._initialized = False

    def _ensure_collection(self):
        """Create the collection if it doesn't exist."""
        try:
            collections = self.client.get_collections()
            existing = [c.name for c in collections.collections]
        except Exception as e:
            logger.error("memory.collection_check_failed", error=str(e))
            existing = []

        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=self.distance,
                ),
            )
            # Create payload indexes for efficient filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="user_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="memory_type",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(
                "memory.collection_created",
                collection=self.collection_name,
                vector_size=self.vector_size,
            )
        self._initialized = True

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding using LiteLLM + OpenRouter-compatible endpoint."""
        try:
            response = litellm.embedding(
                model=self.embedding_model,
                input=[text],
            )
            embedding = response.data[0]["embedding"]
            return embedding
        except Exception as e:
            logger.error("memory.embedding_failed", error=str(e), text_preview=text[:100])
            raise

    def _make_filter(self, user_id: str, memory_types: Optional[list[str]] = None) -> Optional[Filter]:
        """Build a filter for user_id and optional memory types."""
        conditions = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        ]
        if memory_types:
            conditions.append(
                FieldCondition(key="memory_type", match=MatchValue(value=memory_types))
            )
        return Filter(must=conditions) if conditions else None

    def _point_to_dict(self, point: PointStruct) -> dict:
        """Convert a Qdrant point to a memory dict."""
        payload = point.payload or {}
        return {
            "memory_id": point.id,
            "content": payload.get("content", ""),
            "memory_type": payload.get("memory_type", "semantic"),
            "importance": payload.get("importance", 0),
            "tags": payload.get("tags", []),
            "score": point.score if hasattr(point, "score") else 0.0,
            "user_id": payload.get("user_id", ""),
            "session_id": payload.get("session_id", ""),
            "created_at": payload.get("created_at", ""),
            "last_accessed": payload.get("last_accessed", ""),
            "times_retrieved": payload.get("times_retrieved", 0),
            "source": payload.get("source", ""),
        }

    def _format_external_ids_query(self, memory_ids: list[str]) -> Filter:
        """Create a filter matching any of the given external memory_ids."""
        return Filter(should=[
            FieldCondition(key="memory_id", match=MatchValue(value=m))
            for m in memory_ids
        ])

    async def store(
        self,
        content: str,
        memory_type: str,
        importance: int,
        tags: list[str],
        user_id: str,
        session_id: str,
        source: str = "extraction",
    ) -> str:
        """Store a new memory in Qdrant."""
        if not self._initialized:
            self._ensure_collection()

        memory_id = str(uuid.uuid4())
        embedding = await self._embed_async(content)

        now = datetime.now(timezone.utc).isoformat()
        point = PointStruct(
            id=memory_id,
            vector=embedding,
            payload={
                "content": content,
                "memory_type": memory_type,
                "importance": importance,
                "tags": tags,
                "user_id": user_id,
                "session_id": session_id,
                "source": source,
                "created_at": now,
                "last_accessed": now,
                "times_retrieved": 0,
            },
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
        )
        logger.info("memory.stored", memory_id=memory_id, type=memory_type, importance=importance)
        return memory_id

    async def _embed_async(self, text: str) -> list[float]:
        """Wrapper around _embed to run sync litellm call in thread pool."""
        return await asyncio.to_thread(self._embed_sync, text)

    def _embed_sync(self, text: str) -> list[float]:
        """Sync embedding generation (runs in thread pool)."""
        try:
            response = litellm.embedding(
                model=self.embedding_model,
                input=[text],
            )
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error("memory.embedding_failed", error=str(e), text_preview=text[:100])
            raise

    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        memory_types: Optional[list[str]] = None,
    ) -> list[dict]:
        """Retrieve relevant memories using vector similarity search."""
        if not self._initialized:
            self._ensure_collection()

        embedding = await self._embed_async(query)
        query_filter = self._make_filter(user_id, memory_types)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            query_filter=query_filter,
            limit=top_k,
        )

        memories = []
        for hit in (results.points if hasattr(results, 'points') else results):
            memo = self._point_to_dict(hit)
            # Update access stats asynchronously (non-blocking)
            memo["times_retrieved"] = memo.get("times_retrieved", 0) + 1
            memo["last_accessed"] = datetime.now(timezone.utc).isoformat()
            memories.append(memo)

        # Background: update access counts
        if memories:
            asyncio.create_task(self._update_access_counts(memories))

        logger.info(
            "memory.retrieved",
            query_length=len(query),
            user_id=user_id,
            returned_count=len(memories),
            top_k=top_k,
        )
        return memories

    async def _update_access_counts(self, memories: list[dict]):
        """Update last_accessed and times_retrieved for retrieved memories via get_points."""
        try:
            if not memories:
                return
            for m in memories:
                ids_to_get = [m["memory_id"]]
                points_response = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[m["memory_id"]],
                    with_payload=["memory_id"],
                    with_vectors=False,
                )
                if points_response:
                    for pt in points_response:
                        ext_id = pt.payload.get("memory_id")
                        if ext_id == m["memory_id"]:
                            self.client.set_payload(
                                collection_name=self.collection_name,
                                payload={
                                    "last_accessed": m["last_accessed"],
                                    "times_retrieved": m["times_retrieved"],
                                },
                                points=[pt.id],
                            )
        except Exception as e:
            logger.warning("memory.access_update_failed", error=str(e))

    async def update(
        self,
        target_memory_id: str,
        new_content: str,
        new_tags: Optional[list[str]] = None,
    ) -> bool:
        """Update an existing memory's content and optionally its tags."""
        try:
            # Get existing point to preserve embedding
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[
                    FieldCondition(key="memory_id", match=MatchValue(value=target_memory_id)),
                ]),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )
            points, _ = scroll_result
            if not points:
                logger.warning("memory.update_target_not_found", target_memory_id=target_memory_id)
                return False

            point = points[0]
            old_embedding = point.vector or []
            old_payload = dict(point.payload or {})
            old_payload["content"] = new_content
            if new_tags is not None:
                old_payload["tags"] = new_tags
            old_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

            updated_point = PointStruct(
                id=target_memory_id,
                vector=old_embedding,
                payload=old_payload,
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=[updated_point],
            )
            logger.info("memory.updated", memory_id=target_memory_id)
            return True

        except Exception as e:
            logger.error("memory.update_failed", error=str(e))
            return False

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        try:
            # Re-fetch the internal point IDs
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[
                    FieldCondition(key="memory_id", match=MatchValue(value=memory_id)),
                ]),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            points, _ = scroll_result
            if not points:
                return False

            internal_ids = [p.id for p in points]
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=internal_ids),
            )
            logger.info("memory.deleted", memory_id=memory_id)
            return True

        except Exception as e:
            logger.error("memory.delete_failed", error=str(e))
            return False

    async def consolidate(self) -> int:
        """Consolidate duplicate or stale memories. Placeholder for future use."""
        logger.info("memory.consolidate_called", message="Not yet implemented — placeholder")
        return 0
