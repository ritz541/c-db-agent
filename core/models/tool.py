from typing import Any
from pydantic import BaseModel, Field


class ToolMetadata(BaseModel):
    name: str
    description: str
    category: str = "general"
    capabilities: set[str] = Field(default_factory=set)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
