import time
from core.events.base import Event
from core.events.domain import (
    MessageReceived,
    MessageSent,
    PlanCreated,
    StepCancelled,
    StepFailed,
    StepFinished,
    StepScheduled,
    StepStarted,
    ToolFailed,
    ToolFinished,
    ToolStarted,
)
from core.events.system import RuntimeStarted, RuntimeStopped
from runtime.state.models import StateSnapshot


def reduce_state(snapshot: StateSnapshot, event: Event) -> StateSnapshot:
    """Pure state reducer: (StateSnapshot, Event) -> StateSnapshot.
    
    Returns a new immutable StateSnapshot with sequence_number = snapshot.sequence_number + 1.
    No side effects or mutation of existing snapshot objects.
    """
    # Create deep copies of inner states to avoid mutating previous snapshot's state
    session = snapshot.session.model_copy(deep=True)
    tools = snapshot.tools.model_copy(deep=True)
    run = snapshot.run.model_copy(deep=True)
    run_id = snapshot.run_id

    # Extract metadata/context if present on the event
    if hasattr(event, "context") and event.context:
        if getattr(event.context, "session_id", None):
            session.session_id = event.context.session_id
        if getattr(event.context, "user_id", None):
            session.user_id = event.context.user_id
        if getattr(event.context, "run_id", None):
            run.run_id = event.context.run_id
            run_id = event.context.run_id

    # Handle domain and system event transformations
    if isinstance(event, (MessageReceived, MessageSent)):
        session.messages.append(event.message)
    elif isinstance(event, PlanCreated):
        session.active_plan = event.plan
    elif isinstance(event, ToolStarted):
        tools.tool_calls_count += 1
        run.current_step = f"Executing tool: {event.tool_call.name}"
    elif isinstance(event, ToolFinished):
        tools.tool_success_count += 1
        tools.history.append(
            {
                "tool_call_id": event.tool_call.id,
                "name": event.tool_call.name,
                "success": True,
                "output": event.result.output if hasattr(event.result, "output") else str(event.result),
            }
        )
        run.current_step = None
    elif isinstance(event, ToolFailed):
        tools.tool_failure_count += 1
        tools.history.append(
            {
                "tool_call_id": event.tool_call.id,
                "name": event.tool_call.name,
                "success": False,
                "error": event.error,
            }
        )
        run.current_step = None
    elif isinstance(event, RuntimeStarted):
        run.status = "running"
        run.run_id = event.runtime_id
        run_id = event.runtime_id
        run.turn_count = 0
        run.last_error = None
    elif isinstance(event, RuntimeStopped):
        if getattr(event, "reason", "normal") == "error":
            run.status = "failed"
        else:
            run.status = "completed"
    elif isinstance(event, StepStarted):
        run.current_step = f"Executing step {event.step.step_id}: {event.step.description}"
        if session.active_plan:
            for step in session.active_plan.steps:
                if step.step_id == event.step.step_id:
                    step.status = "running"
    elif isinstance(event, StepFinished):
        run.current_step = None
        if session.active_plan:
            for step in session.active_plan.steps:
                if step.step_id == event.step.step_id:
                    step.status = "completed"
                    step.completed = True
                    if getattr(event, "result", None) is not None:
                        step.result = str(event.result)
    elif isinstance(event, StepFailed):
        run.current_step = None
        run.last_error = event.error
        if session.active_plan:
            for step in session.active_plan.steps:
                if step.step_id == event.step.step_id:
                    step.status = "failed"
                    step.error = event.error
    elif isinstance(event, StepCancelled):
        run.current_step = None
        if session.active_plan:
            for step in session.active_plan.steps:
                if step.step_id == event.step.step_id:
                    step.status = "cancelled"

    return StateSnapshot(
        run_id=run_id,
        sequence_number=snapshot.sequence_number + 1,
        session=session,
        tools=tools,
        run=run,
        timestamp=time.time(),
    )
