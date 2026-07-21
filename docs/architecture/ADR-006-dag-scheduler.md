# ADR-006: DAG Scheduler & Parallel Execution Architecture

## Status
Accepted

## Context
Executing tool calls and planner steps purely sequentially introduces latency bottlenecks during independent operations. The runtime engine requires wave-based parallel execution of DAG (Directed Acyclic Graph) plans with dependency policies, resource concurrency limits, thread-safe state store/memory updates under parallel writes, cancellation/resumption mechanics, and deterministic message ordering for LLM provider protocol compliance.

## Decision
1. **`DAGScheduler` Component**:
   - `DAGSchedulerInterface` defines the contract (`execute_plan`).
   - `DAGScheduler` consumes dependency-annotated `Plan` DAGs and executes ready `PlanStep` nodes concurrently.
   - Resource concurrency is bounded using `asyncio.Semaphore(max_concurrent_tasks)` (default: 8).
   - Single source of truth for step statuses: `pending`, `running`, `completed`, `failed`, `cancelled`.
2. **Dependency Failure Policies**:
   - `"all"`: Prerequisite steps must all complete successfully. Fails/cancels step if any prerequisite fails.
   - `"any"`: Executes if at least one prerequisite step completes successfully.
   - `"ignore_failures"`: Executes as long as all prerequisite steps finish regardless of success/failure status.
3. **Deadlock & Cyclic Dependency Protection**:
   - Automatic cycle/deadlock detection marks unresolved pending steps as `failed` if no ready steps exist while no tasks are active.
4. **Thread-Safe State & Memory Mutations**:
   - Explicit `asyncio.Lock()` in `StateStore` and `QdrantMemoryService` serializes updates during parallel execution.
5. **Deterministic History & Provider Compliance**:
   - `RuntimeEngine` uses `asyncio.gather` for parallel LLM tool call execution and appends results to `ConversationHistory` in exact original index order.
6. **Cancellation & Resumption**:
   - Cooperative cancellation via `CancellationToken` cancels active tasks and updates step states.
   - Plan checkpointing enables resumption of partially completed DAG plans.

## Consequences
- Significant performance speedup for multi-tool parallel workflows.
- Thread safety and data integrity guaranteed across concurrent event handlers.
- Full compatibility with strict LLM provider message ordering protocols.
