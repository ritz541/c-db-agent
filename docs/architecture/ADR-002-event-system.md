# ADR-002: Event-Driven Pub/Sub & Middleware Hooks

## Status
Accepted

## Context
As complex agent execution flows occur, UI rendering, logging, state tracking, and metrics monitoring need real-time updates without coupling execution logic directly to output handlers. Furthermore, pre-execution interception (timing, permissions, caching, retries) is required.

## Decision
1. **Event Taxonomy**: Define `DomainEvent` (MessageReceived, PlanCreated, ToolStarted, ToolFinished, ToolFailed, MemoryStored) and `SystemEvent` (RuntimeStarted, RuntimeStopped, TaskCreated, TaskCompleted).
2. **Priority Event Bus**: Implement `EventBusInterface` with subscriber priority levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`) and subscriber exception isolation so single subscriber failures do not crash the engine.
3. **Pre-Execution Middleware**: Use runtime middleware hooks (`before_tool_execute`, `after_tool_execute`) for intercepting execution before actions occur.

## Consequences
- Complete decoupling of UI and telemetry from engine execution.
- Robust execution where subscriber errors are contained.
- Pluggable middleware capability for authorization, auditing, timing, and rate limiting.
