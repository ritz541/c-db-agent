import time
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
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


class StateSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    run_id: str = ""
    sequence_number: int = 0
    session: AgentSessionState
    tools: ToolExecutionState
    run: RunState
    timestamp: float = Field(default_factory=time.time)
