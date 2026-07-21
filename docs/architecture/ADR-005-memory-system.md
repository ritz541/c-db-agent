# ADR-005: Vector Memory System & Extractor Pipeline

## Status
Accepted

## Context
Long-term memory storage and semantic retrieval must operate independently of the underlying vector database implementation (e.g. Qdrant, Milvus, in-memory).

## Decision
1. **`MemoryProviderInterface`**: Defines standard async `store` and `search` methods taking strongly-typed `MemoryItem` domain models.
2. **Qdrant Implementation**: `QdrantMemoryService` implements `MemoryProviderInterface` using qdrant-client with fallback/graceful handling.
3. **Memory Extractor Pipeline**: High-importance conversation fragments are extracted into `MemoryItem`s with metadata, importance scores, and tags.

## Consequences
- Memory infrastructure can be swapped without changing agent logic.
- Rich memory metadata enables effective contextual retrieval.
