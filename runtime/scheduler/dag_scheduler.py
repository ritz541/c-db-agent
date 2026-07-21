import asyncio
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
        semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        results: dict[int, ToolResult | Any] = {}

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

            for step in ready_steps:
                step.status = "running"
                if self.services and getattr(self.services, "events", None):
                    await self.services.events.publish(StepScheduled(step=step))

                task = asyncio.create_task(
                    self._run_step(step, plan, context, results, semaphore)
                )
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

        return results

    async def _run_step(
        self,
        step: PlanStep,
        plan: Plan,
        context: ExecutionContext | None,
        results: dict[int, ToolResult | Any],
        semaphore: asyncio.Semaphore,
    ) -> None:
        async with semaphore:
            # Re-check cancellation token before start
            if context and context.cancellation_token and context.cancellation_token.check_cancelled():
                step.status = "cancelled"
                if self.services and getattr(self.services, "events", None):
                    await self.services.events.publish(
                        StepCancelled(step=step, reason="Execution cancelled before start")
                    )
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
                elif (step.node_type == "tool" or step.tool_name) and getattr(self.services, "executor", None):
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
