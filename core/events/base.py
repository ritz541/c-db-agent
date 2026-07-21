from datetime import datetime, timezone
from enum import IntEnum
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field
from core.models.context import ExecutionContext


class EventPriority(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: EventPriority = EventPriority.INFO
    context: ExecutionContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
