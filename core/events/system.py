from typing import Any
from core.events.base import Event


class SystemEvent(Event):
    pass


class RuntimeStarted(SystemEvent):
    runtime_id: str


class RuntimeStopped(SystemEvent):
    runtime_id: str
    reason: str = "normal"


class PluginLoaded(SystemEvent):
    plugin_name: str


class SubscriberRegistered(SystemEvent):
    event_type_name: str
    handler_name: str


class TaskCreated(SystemEvent):
    task_id: str
    task_name: str


class TaskCompleted(SystemEvent):
    task_id: str
    result: Any = None


class TaskFailed(SystemEvent):
    task_id: str
    error: str


class TaskCancelled(SystemEvent):
    task_id: str
