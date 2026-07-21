import asyncio
from datetime import datetime, timezone
from typing import Any, Coroutine
from uuid import uuid4

from core.events.base import EventPriority
from core.events.system import TaskCancelled, TaskCompleted, TaskCreated, TaskFailed
from core.interfaces.event_bus import EventBusInterface
from core.interfaces.task_manager import TaskManagerInterface
from core.models.context import ExecutionContext


class TaskManager(TaskManagerInterface):
    """Centralized Async Task Manager tracking background tasks and emitting events."""

    def __init__(self, event_bus: EventBusInterface | None = None) -> None:
        self.event_bus = event_bus
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    async def spawn_task(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
        context: ExecutionContext | None = None,
    ) -> str:
        task_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self._metadata[task_id] = {
            "task_id": task_id,
            "name": name,
            "status": "running",
            "created_at": now,
            "context": context,
        }

        if self.event_bus:
            await self.event_bus.publish(
                TaskCreated(
                    task_id=task_id,
                    task_name=name,
                    context=context,
                    priority=EventPriority.INFO,
                )
            )

        async def _wrapper() -> Any:
            try:
                res = await coro
                self._metadata[task_id]["status"] = "completed"
                self._metadata[task_id]["result"] = res
                if self.event_bus:
                    await self.event_bus.publish(
                        TaskCompleted(
                            task_id=task_id,
                            result=str(res),
                            context=context,
                            priority=EventPriority.INFO,
                        )
                    )
                return res
            except asyncio.CancelledError:
                self._metadata[task_id]["status"] = "cancelled"
                if self.event_bus:
                    await self.event_bus.publish(
                        TaskCancelled(
                            task_id=task_id,
                            context=context,
                            priority=EventPriority.WARNING,
                        )
                    )
                raise
            except Exception as exc:
                self._metadata[task_id]["status"] = "failed"
                self._metadata[task_id]["error"] = str(exc)
                if self.event_bus:
                    await self.event_bus.publish(
                        TaskFailed(
                            task_id=task_id,
                            error=str(exc),
                            context=context,
                            priority=EventPriority.ERROR,
                        )
                    )
                raise

        task = asyncio.create_task(_wrapper(), name=f"{name}-{task_id}")
        self._tasks[task_id] = task

        # Add done callback to clean up task reference when finished
        def _on_done(t: asyncio.Task[Any]) -> None:
            pass

        task.add_done_callback(_on_done)
        return task_id

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.done():
            return False

        self._metadata[task_id]["status"] = "cancelled"
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    def list_tasks(self) -> list[dict[str, Any]]:
        result = []
        for task_id, meta in self._metadata.items():
            task = self._tasks.get(task_id)
            is_done = task.done() if task else True
            result.append(
                {
                    "task_id": task_id,
                    "name": meta.get("name"),
                    "status": meta.get("status"),
                    "done": is_done,
                    "created_at": meta.get("created_at"),
                }
            )
        return result
