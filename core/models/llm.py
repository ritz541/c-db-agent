from typing import Any
from pydantic import BaseModel, Field
from core.models.tool import ToolCall


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
