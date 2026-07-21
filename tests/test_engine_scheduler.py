import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.builder import Agent
from core.models.llm import LLMResponse
from core.models.planning import Plan, PlanCategory, PlanStep
from core.models.tool import ToolCall
from runtime.execution.tool_executor import ToolExecutor
from tools.calculator import CalculatorTool


class _PreResolvedPlanner:
    """Planner that emits a single_pass plan with a step that already has
    resolved arguments, so the engine should hand execution to the DAG
    scheduler and short-circuit the LLM loop.
    """

    def __init__(self, tool_name: str, arguments: dict):
        self._tool_name = tool_name
        self._arguments = arguments

    async def create_plan(self, goal, history, tools, context=None):
        step = PlanStep(
            step_id=1,
            description=f"Process goal: {goal}",
            tool_name=self._tool_name,
            node_type="tool",
            arguments=self._arguments,
            status="pending",
            completed=False,
        )
        return Plan(
            plan_id="pre_resolved",
            goal=goal,
            category=PlanCategory.SIMPLE_RETRIEVAL,
            steps=[step],
            completed=False,
            metadata={"single_pass": True},
        )


@pytest.mark.asyncio
async def test_engine_consumes_scheduler_results_for_preresolved_plan():
    """Verify the engine runs the DAG scheduler for a plan with resolved args
    and returns its result WITHOUT invoking the LLM turn-loop.

    Before the fix, execute_plan() was called and its results discarded; the
    engine then re-ran the full LLM loop. Here we assert the LLM is never
    called and the scheduler's tool output becomes the final result.
    """
    planner = _PreResolvedPlanner("calculate", {"expression": "6 * 7"})
    executor = ToolExecutor([CalculatorTool()])

    agent = (
        Agent.builder()
        .with_planner(planner)  # type: ignore[arg-type]
        .with_executor(executor)
        .with_tool(CalculatorTool())
        .build()
    )

    # Field the network/LLM check: the planner is set but no LLM should be
    # contacted. We patch generate_response to fail the test if called.
    llm_calls = []

    async def _fail_if_called(*args, **kwargs):
        llm_calls.append(1)
        raise AssertionError("LLM should not be called on the scheduler fast-path")

    agent.engine.services.llm.generate_response = _fail_if_called

    result = await agent.run("what is 6 * 7")
    assert llm_calls == [], "LLM turn-loop must be skipped for a resolved plan"
    assert result.metadata.get("single_pass") is True
    assert "42" in result.final_output, result.final_output
