from typing import Any
from pydantic import BaseModel, Field

from core.models.message import AgentMessage
from core.models.tool import ToolCall


class ConversationHistory(BaseModel):
    """Encapsulates chat history and enforces LLM provider protocol invariants."""

    messages: list[AgentMessage] = Field(default_factory=list)

    def add_system(
        self,
        content: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            role="system", content=content, name=name, metadata=metadata or {}
        )
        self.messages.append(msg)
        return msg

    def add_user(
        self,
        content: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            role="user", content=content, name=name, metadata=metadata or {}
        )
        self.messages.append(msg)
        return msg

    def add_assistant(
        self,
        content: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            role="assistant",
            content=content or "",
            tool_calls=tool_calls if tool_calls else None,
            name=name,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        return msg

    def add_tool(
        self,
        tool_call_id: str,
        content: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        return msg

    def get_messages(self) -> list[AgentMessage]:
        return list(self.messages)

    def __len__(self) -> int:
        return len(self.messages)

    def __getitem__(self, item: int) -> AgentMessage:
        return self.messages[item]
