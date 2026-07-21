from typing import Any
from pydantic import BaseModel, Field


class RunResult(BaseModel):
    final_output: str
    turn_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
