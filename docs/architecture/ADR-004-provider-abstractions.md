# ADR-004: Service Container & Capability-Based Tool Metadata

## Status
Accepted

## Context
Passing 10+ dependencies across constructor arguments creates brittle code. Tools need to declare their operational semantics (e.g. database access, filesystem, unsafe execution) so planners and security middleware can inspect them dynamically.

## Decision
1. **Service Container (`RuntimeServices`)**: A unified container object encapsulates `llm`, `memory`, `planner`, `events`, `config`, `state_store`, and `task_manager`. Components receive `RuntimeServices` instead of separate constructor parameters.
2. **Capability-Based Tools**: `ToolMetadata` includes a `capabilities: set[str]` field (e.g., `{"database"}`, `{"filesystem"}`, `{"unsafe"}`).

## Consequences
- Clean dependency resolution across the entire framework.
- Planners can dynamically reason over tool capabilities rather than hardcoded tool names.
