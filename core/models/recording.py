import time
from typing import Any
from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    run_id: str
    timestamp: float = Field(default_factory=time.time)
    events: list[dict[str, Any]] = Field(default_factory=list)
    snapshots: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
