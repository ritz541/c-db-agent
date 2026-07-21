from typing import Any
from core.events.base import Event
from core.models.memory import MemoryItem
from core.models.message import AgentMessage
from core.models.planning import Plan, PlanStep
from core.models.tool import ToolCall, ToolResult


class DomainEvent(Event):
    pass


class MessageReceived(DomainEvent):
    message: AgentMessage


class MessageSent(DomainEvent):
    message: AgentMessage


class PlanCreated(DomainEvent):
    plan: Plan


class ToolStarted(DomainEvent):
    tool_call: ToolCall


class ToolFinished(DomainEvent):
    tool_call: ToolCall
    result: ToolResult


class ToolFailed(DomainEvent):
    tool_call: ToolCall
    error: str


class MemoryStored(DomainEvent):
    item: MemoryItem


class MemoryRetrieved(DomainEvent):
    query: str
    items: list[MemoryItem]

class StepScheduled(DomainEvent):
    step: PlanStep


class StepStarted(DomainEvent):
    step: PlanStep


class StepFinished(DomainEvent):
    step: PlanStep
    result: ToolResult | Any = None


class StepFailed(DomainEvent):
    step: PlanStep
    error: str


class StepCancelled(DomainEvent):
    step: PlanStep
    reason: str
