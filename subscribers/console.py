from rich.console import Console
from rich.panel import Panel

from core.events.base import Event
from core.events.domain import (
    MessageReceived,
    MessageSent,
    PlanCreated,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from core.interfaces.event_bus import EventBusInterface
from runtime.events.subscriber import BaseSubscriber


class ConsoleSubscriber(BaseSubscriber):
    """CLI Rich Console subscriber rendering events to stdout."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def register(self, event_bus: EventBusInterface) -> None:
        event_bus.subscribe(RuntimeStarted, self.on_runtime_started)
        event_bus.subscribe(RuntimeStopped, self.on_runtime_stopped)
        event_bus.subscribe(MessageReceived, self.on_message_received)
        event_bus.subscribe(MessageSent, self.on_message_sent)
        event_bus.subscribe(PlanCreated, self.on_plan_created)
        event_bus.subscribe(ToolStarted, self.on_tool_started)
        event_bus.subscribe(ToolFinished, self.on_tool_finished)
        event_bus.subscribe(ToolFailed, self.on_tool_failed)

    def on_runtime_started(self, event: RuntimeStarted) -> None:
        self.console.print(f"[dim]🚀 Engine Started (run_id: {event.runtime_id})[/dim]")

    def on_runtime_stopped(self, event: RuntimeStopped) -> None:
        self.console.print(f"[dim]🏁 Engine Stopped (reason: {event.reason})[/dim]")

    def on_message_received(self, event: MessageReceived) -> None:
        pass

    def on_message_sent(self, event: MessageSent) -> None:
        content = event.message.content
        if content and event.message.role == "assistant":
            self.console.print(Panel(content, title="Assistant", border_style="green"))

    def on_plan_created(self, event: PlanCreated) -> None:
        plan = event.plan
        steps_str = "\n".join(f"{s.step_id}. {s.description}" for s in plan.steps)
        self.console.print(Panel(f"Goal: {plan.goal}\nSteps:\n{steps_str}", title="📋 Plan", border_style="cyan"))

    def on_tool_started(self, event: ToolStarted) -> None:
        self.console.print(f"[yellow]⚙ Executing Tool:[/yellow] [bold]{event.tool_call.name}[/bold] (args: {event.tool_call.arguments})")

    def on_tool_finished(self, event: ToolFinished) -> None:
        dur = event.result.metadata.get("duration_ms", "")
        dur_str = f" in {dur}ms" if dur else ""
        self.console.print(f"[green]✔ Tool {event.tool_call.name} Succeeded{dur_str}[/green]")

    def on_tool_failed(self, event: ToolFailed) -> None:
        self.console.print(f"[red]❌ Tool {event.tool_call.name} Failed:[/red] {event.error}")
