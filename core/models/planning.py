from typing import Any
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step_id: int
    description: str
    tool_name: str | None = None
    completed: bool = False
    result: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    plan_id: str
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    completed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
