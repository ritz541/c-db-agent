# ADR-003: Reactive StateStore as Single Source of Truth

## Status
Accepted

## Context
Agent applications require tracking active turns, session messages, tool execution metrics, and run status. Distributing state management across multiple components leads to state inconsistency and sync bugs.

## Decision
1. **Single Source of Truth**: `StateStore` implements `StateStoreInterface` and acts as the central reactive state store for session and run states.
2. **Event-Driven State Updates**: `StateStore` subscribes to domain events on the `EventBus` (`MessageReceived`, `ToolStarted`, `ToolFinished`, `ToolFailed`, `PlanCreated`) and updates state models (`AgentSessionState`, `RunState`, `ToolExecutionState`) reactively.

## Consequences
- State updates are deterministic and audit-ready via the event log.
- Frontends can query state snapshot at any time without imperatively modifying agent state.
