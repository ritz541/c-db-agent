from typing import Any
from pydantic import BaseModel, Field
from core.models.tool import ToolCall


class AgentMessage(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
