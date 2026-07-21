from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    memory_type: str = "general"
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
