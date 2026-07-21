from typing import Any
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step_id: int
    description: str
    node_type: str = "tool"  # "tool", "llm", "subagent", "custom"
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    dependency_policy: str = "all"  # "all", "any", "ignore_failures"
    status: str = "pending"  # "pending", "running", "completed", "failed", "cancelled"
    completed: bool = False
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    plan_id: str
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    completed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_ready_steps(self) -> list[PlanStep]:
        """Return steps that are 'pending' and satisfy dependency policy."""
        step_map = {step.step_id: step for step in self.steps}
        ready: list[PlanStep] = []

        for step in self.steps:
            if step.status != "pending":
                continue

            if not step.depends_on:
                ready.append(step)
                continue

            prereqs = [step_map[dep_id] for dep_id in step.depends_on if dep_id in step_map]
            if len(prereqs) < len(step.depends_on):
                # Unresolved dependency reference
                continue

            if step.dependency_policy == "all":
                if all(p.status == "completed" for p in prereqs):
                    ready.append(step)
            elif step.dependency_policy == "any":
                if any(p.status == "completed" for p in prereqs):
                    ready.append(step)
            elif step.dependency_policy == "ignore_failures":
                if all(p.status in ("completed", "failed", "cancelled") for p in prereqs):
                    ready.append(step)

        return ready

    def is_complete(self) -> bool:
        """Return True when all steps are resolved (completed, failed, or cancelled)."""
        if not self.steps:
            return True
        return all(step.status in ("completed", "failed", "cancelled") for step in self.steps)

    def get_checkpoint(self) -> dict[str, Any]:
        """Get plan checkpoint state dictionary."""
        return self.model_dump()
