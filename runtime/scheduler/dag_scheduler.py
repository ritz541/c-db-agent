import asyncio
import time
from typing import Any
import structlog

from container.services import RuntimeServices
from core.events.domain import (
    StepCancelled,
    StepFailed,
    StepFinished,
    StepScheduled,
    StepStarted,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.interfaces.scheduler import DAGSchedulerInterface
from core.models.context import ExecutionContext
from core.models.metrics import SchedulerMetrics, StepMetrics
from core.models.planning import Plan, PlanStep
from core.models.tool import ToolCall, ToolResult

logger = structlog.get_logger(__name__)


class DAGScheduler(DAGSchedulerInterface):
    """Planner-driven parallel execution engine for DAG plans."""

    def __init__(self, services: RuntimeServices, max_concurrent_tasks: int = 8) -> None:
        self.services = services
        self.max_concurrent_tasks = max_concurrent_tasks
    async def execute_plan(
        self,
        plan: Plan,
        context: ExecutionContext | None = None,
    ) -> dict[int, ToolResult | Any]:
        """Execute DAG plan concurrently based on step dependencies and concurrency limits."""
        start_wall_time = time.time()
        semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        results: dict[int, ToolResult | Any] = {}

        # Scheduler metrics tracking state
        scheduled_at: dict[int, float] = {}
        started_at: dict[int, float] = {}
        finished_at: dict[int, float] = {}
        metrics_lock = asyncio.Lock()
        concurrency_tracker = {"active": 0, "peak": 0}
        queue_depth_peak = len([s for s in plan.steps if s.status == "pending"])
        # 1. Recover completed/failed step results, and reset cancelled steps for plan resumption
        for step in plan.steps:
            if step.status == "completed":
                step.completed = True
                results[step.step_id] = ToolResult(
                    tool_call_id=f"step_{step.step_id}",
                    success=True,
                    output=step.result or "",
                )
            elif step.status == "failed":
                results[step.step_id] = ToolResult(
                    tool_call_id=f"step_{step.step_id}",
                    success=False,
                    output=step.result or "",
                    error=step.error or "Step failed in prior execution",
                )
            elif step.status == "cancelled":
                step.status = "pending"
                step.error = None

        running_tasks: set[asyncio.Task] = set()

        while not plan.is_complete():
            # 2. Check cooperative cancellation
            if context and context.cancellation_token and context.cancellation_token.check_cancelled():
                logger.info("dag_scheduler.cancelled", plan_id=plan.plan_id)
                for task in running_tasks:
                    task.cancel()
                for step in plan.steps:
                    if step.status in ("pending", "running"):
                        step.status = "cancelled"
                        if self.services and getattr(self.services, "events", None):
                            await self.services.events.publish(
                                StepCancelled(
                                    step=step,
                                    reason="Execution cancelled by cancellation token",
                                )
                            )
                break

            # 3. Handle un-runnable pending steps due to prerequisite failures
            step_map = {s.step_id: s for s in plan.steps}
            for step in plan.steps:
                if step.status != "pending" or not step.depends_on:
                    continue

                prereqs = [step_map[dep_id] for dep_id in step.depends_on if dep_id in step_map]
                if step.dependency_policy == "all":
                    if any(p.status in ("failed", "cancelled") for p in prereqs):
                        step.status = "cancelled"
                        step.error = "Prerequisite step failed or cancelled"
                        if self.services and getattr(self.services, "events", None):
                            await self.services.events.publish(
                                StepCancelled(step=step, reason=step.error)
                            )
                elif step.dependency_policy == "any":
                    if all(p.status in ("failed", "cancelled") for p in prereqs) and prereqs:
                        step.status = "cancelled"
                        step.error = "No prerequisite step succeeded"
                        if self.services and getattr(self.services, "events", None):
                            await self.services.events.publish(
                                StepCancelled(step=step, reason=step.error)
                            )

            # 4. Get ready steps and launch tasks
            ready_steps = plan.get_ready_steps()

            if ready_steps:
                now = time.time()
                for step in ready_steps:
                    if step.step_id not in scheduled_at:
                        scheduled_at[step.step_id] = now

                # Track peak queue depth
                pending_count = len([s for s in plan.steps if s.status == "pending"])
                if pending_count > queue_depth_peak:
                    queue_depth_peak = pending_count

            for step in ready_steps:
                step.status = "running"
                if self.services and getattr(self.services, "events", None):
                    await self.services.events.publish(StepScheduled(step=step))

                async def runner(s=step):
                    await self._run_step(
                        s,
                        plan,
                        context,
                        results,
                        semaphore,
                        started_at,
                        finished_at,
                        metrics_lock,
                        concurrency_tracker,
                    )

                task = asyncio.create_task(runner(step))
                running_tasks.add(task)

            # 5. Cyclic dependency & deadlock detection
            if not ready_steps and not running_tasks and not plan.is_complete():
                logger.error("dag_scheduler.deadlock_detected", plan_id=plan.plan_id)
                for step in plan.steps:
                    if step.status == "pending":
                        step.status = "failed"
                        step.error = "Cyclic dependency or deadlock detected in DAG plan"
                        if self.services and getattr(self.services, "events", None):
                            await self.services.events.publish(
                                StepFailed(step=step, error=step.error)
                            )
                break

            # 6. Wait for at least one active task to complete
            if running_tasks:
                done, running_tasks = await asyncio.wait(
                    running_tasks, return_when=asyncio.FIRST_COMPLETED
                )

        # Build telemetry metrics after plan execution finishes
        end_wall_time = time.time()
        total_wall_time = max(0.0001, end_wall_time - start_wall_time)

        step_metrics: dict[int, StepMetrics] = {}
        for step in plan.steps:
            if step.step_id in started_at:
                sched = scheduled_at.get(step.step_id, start_wall_time)
                start = started_at[step.step_id]
                fin = finished_at.get(step.step_id, start)
                w_time = max(0.0, start - sched)
                e_time = max(0.0, fin - start)
                step_metrics[step.step_id] = StepMetrics(
                    step_id=step.step_id,
                    scheduled_at=sched,
                    started_at=start,
                    finished_at=fin,
                    wait_time=w_time,
                    execution_time=e_time,
                )

        # Critical path duration computation via dynamic programming
        memo: dict[int, float] = {}
        visiting: set[int] = set()
        step_map_all = {s.step_id: s for s in plan.steps}

        def get_cp(step_id: int) -> float:
            if step_id in memo:
                return memo[step_id]
            if step_id in visiting:
                return 0.0
            visiting.add(step_id)
            step_obj = step_map_all.get(step_id)
            dur = step_metrics[step_id].execution_time if step_id in step_metrics else 0.0
            if not step_obj or not step_obj.depends_on:
                memo[step_id] = dur
                visiting.remove(step_id)
                return dur
            dep_cps = [get_cp(dep_id) for dep_id in step_obj.depends_on if dep_id in step_map_all]
            max_dep = max(dep_cps) if dep_cps else 0.0
            val = max_dep + dur
            visiting.remove(step_id)
            memo[step_id] = val
            return val

        critical_path_duration = max((get_cp(step.step_id) for step in plan.steps), default=0.0)

        avg_wait = sum(sm.wait_time for sm in step_metrics.values()) / len(step_metrics) if step_metrics else 0.0
        avg_exec = sum(sm.execution_time for sm in step_metrics.values()) / len(step_metrics) if step_metrics else 0.0
        total_exec = sum(sm.execution_time for sm in step_metrics.values())

        peak_concurrency = concurrency_tracker["peak"]
        if peak_concurrency > 0 and total_wall_time > 0:
            parallel_efficiency = min(1.0, max(0.0, total_exec / (total_wall_time * peak_concurrency)))
        else:
            parallel_efficiency = 0.0
        run_id = context.run_id if (context and getattr(context, "run_id", None)) else ""

        metrics = SchedulerMetrics(
            run_id=run_id,
            total_wall_time=total_wall_time,
            average_wait_time=avg_wait,
            average_execution_time=avg_exec,
            critical_path_duration=critical_path_duration,
            parallel_efficiency=parallel_efficiency,
            peak_concurrency=peak_concurrency,
            queue_depth_peak=queue_depth_peak,
            retry_count=0,
            step_metrics=step_metrics,
        )

        plan.metadata["metrics"] = metrics.model_dump()
        plan.metadata["metrics_object"] = metrics

        return results

    async def _run_step(
        self,
        step: PlanStep,
        plan: Plan,
        context: ExecutionContext | None,
        results: dict[int, ToolResult | Any],
        semaphore: asyncio.Semaphore,
        started_at: dict[int, float],
        finished_at: dict[int, float],
        metrics_lock: asyncio.Lock,
        concurrency_tracker: dict[str, int],
    ) -> None:
        async with semaphore:
            async with metrics_lock:
                started_at[step.step_id] = time.time()
                concurrency_tracker["active"] += 1
                if concurrency_tracker["active"] > concurrency_tracker["peak"]:
                    concurrency_tracker["peak"] = concurrency_tracker["active"]

            # Re-check cancellation token before start
            if context and context.cancellation_token and context.cancellation_token.check_cancelled():
                step.status = "cancelled"
                if self.services and getattr(self.services, "events", None):
                    await self.services.events.publish(
                        StepCancelled(step=step, reason="Execution cancelled before start")
                    )
                async with metrics_lock:
                    finished_at[step.step_id] = time.time()
                return

            if self.services and getattr(self.services, "events", None):
                await self.services.events.publish(StepStarted(step=step))

            try:
                if step.node_type == "llm" and getattr(self.services, "llm", None):
                    prompt = step.description or str(step.arguments)
                    response = await self.services.llm.generate(prompt=prompt, context=context)
                    output_text = getattr(response, "content", str(response))
                    res: ToolResult | Any = ToolResult(
                        tool_call_id=f"step_{step.step_id}",
                        success=True,
                        output=output_text,
                    )
                elif (step.tool_name or (step.node_type == "tool" and step.tool_name)) and getattr(self.services, "executor", None):
                    tool_call = ToolCall(
                        id=f"step_{step.step_id}",
                        name=step.tool_name or step.description,
                        arguments=step.arguments,
                    )
                    if self.services and getattr(self.services, "events", None):
                        await self.services.events.publish(
                            ToolStarted(tool_call=tool_call, context=context)
                        )

                    res = await self.services.executor.execute_tool(tool_call, context)

                    if self.services and getattr(self.services, "events", None):
                        if isinstance(res, ToolResult) and res.success:
                            await self.services.events.publish(
                                ToolFinished(tool_call=tool_call, result=res, context=context)
                            )
                        else:
                            err_msg = res.error if isinstance(res, ToolResult) else "Tool execution failed"
                            await self.services.events.publish(
                                ToolFailed(
                                    tool_call=tool_call,
                                    error=err_msg or "Tool execution failed",
                                    context=context,
                                )
                            )
                else:
                    res = ToolResult(
                        tool_call_id=f"step_{step.step_id}",
                        success=True,
                        output=f"Executed step {step.step_id}: {step.description}",
                    )

                if isinstance(res, ToolResult) and not res.success:
                    step.status = "failed"
                    step.error = res.error or "Tool execution failed"
                    step.result = res.output
                    results[step.step_id] = res
                    if self.services and getattr(self.services, "events", None):
                        await self.services.events.publish(StepFailed(step=step, error=step.error))
                else:
                    step.status = "completed"
                    step.completed = True
                    output_str = res.output if isinstance(res, ToolResult) else str(res)
                    step.result = output_str
                    results[step.step_id] = res
                    if self.services and getattr(self.services, "events", None):
                        await self.services.events.publish(StepFinished(step=step, result=res))

            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                res_err = ToolResult(
                    tool_call_id=f"step_{step.step_id}",
                    success=False,
                    output="",
                    error=str(e),
                )
                results[step.step_id] = res_err
                if self.services and getattr(self.services, "events", None):
                    await self.services.events.publish(StepFailed(step=step, error=str(e)))
            finally:
                async with metrics_lock:
                    finished_at[step.step_id] = time.time()
                    concurrency_tracker["active"] -= 1
