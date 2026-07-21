from typing import Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field


class CancellationToken(BaseModel):
    """Token allowing cooperative cancellation across long-running tasks."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_cancelled: bool = False

    def request_cancellation(self) -> None:
        self.is_cancelled = True

    def check_cancelled(self) -> bool:
        return self.is_cancelled


class ExecutionContext(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = "default_user"
    cancellation_token: CancellationToken = Field(default_factory=CancellationToken)
    config: dict[str, Any] = Field(default_factory=dict)
