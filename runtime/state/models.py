from typing import Any
from pydantic import BaseModel, Field
from core.models.message import AgentMessage
from core.models.planning import Plan


class AgentSessionState(BaseModel):
    session_id: str = ""
    user_id: str = "default_user"
    messages: list[AgentMessage] = Field(default_factory=list)
    active_plan: Plan | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionState(BaseModel):
    tool_calls_count: int = 0
    tool_success_count: int = 0
    tool_failure_count: int = 0
    history: list[dict[str, Any]] = Field(default_factory=list)


class RunState(BaseModel):
    run_id: str | None = None
    status: str = "idle"  # idle, running, completed, failed
    turn_count: int = 0
    current_step: str | None = None
    last_error: str | None = None
