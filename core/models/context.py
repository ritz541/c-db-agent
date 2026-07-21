from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = "default_user"
    config: dict[str, Any] = Field(default_factory=dict)
