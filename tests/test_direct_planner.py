import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.builder import Agent
from core.models.llm import LLMResponse
from core.models.planning import PlanCategory
from core.models.tool import ToolCall, ToolMetadata
from runtime.planning.direct_planner import DirectPlanner
from tools.calculator import CalculatorTool
from tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_direct_planner_single_pass_classification():
    """Verify DirectPlanner classifies 1-step tool matching plans as SIMPLE_RETRIEVAL."""
    planner = DirectPlanner()
    tool_meta = [ToolMetadata(name="calculate", description="Calculate mathematical expressions")]

    plan = await planner.create_plan(goal="calculate 2 + 2", history=[], tools=tool_meta)
    assert plan.category == PlanCategory.SIMPLE_RETRIEVAL
    assert plan.metadata.get("single_pass") is True

    plan_gen = await planner.create_plan(goal="Write a creative story", history=[], tools=[])
    assert plan_gen.category == PlanCategory.GENERAL
    assert plan_gen.metadata.get("single_pass") is not True


@pytest.mark.asyncio
async def test_direct_planner_no_overbroad_keyword_matching():
    """Verify DirectPlanner does not match tools based on overbroad description keywords like 'job'."""
    planner = DirectPlanner()
    tool_meta = [ToolMetadata(name="web_search", description="Search the web for jobs and fetch job descriptions")]

    plan = await planner.create_plan(
        goal="so tell me how many job applications sent and to which companies.",
        history=[],
        tools=tool_meta,
    )
    assert plan.steps[0].tool_name is None
    assert plan.category == PlanCategory.GENERAL


@pytest.mark.asyncio
async def test_single_pass_reactive_execution_turn_limit():
    """Verify single-tool query completes naturally in 2 turns without stripping tools schema."""
    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        side_effect=[
            LLMResponse(
                content="Checking status...",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="calculate",
                        arguments={"expression": "2 + 3"},
                    )
                ],
            ),
            LLMResponse(content="You have 5 items so far.", tool_calls=[]),
        ]
    )

    registry = ToolRegistry()
    calc_tool = CalculatorTool()
    registry.register(calc_tool)

    agent = Agent.builder().with_llm(mock_llm).with_tool(calc_tool).build()

    result = await agent.run("calculate 2 + 3")

    assert result.turn_count == 2
    assert result.final_output == "You have 5 items so far."
    assert mock_llm.generate_response.call_count == 2


@pytest.mark.asyncio
async def test_intermediate_assistant_chatter_suppression():
    """Verify intermediate filler text alongside tool calls does NOT publish non-empty content in MessageSent."""
    from agent.builder import Agent
    from core.events.domain import MessageSent

    published_events = []

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        side_effect=[
            LLMResponse(
                content="Let me check the database...",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="calculate",
                        arguments={"expression": "10 * 2"},
                    )
                ],
            ),
            LLMResponse(content="The result is 20.", tool_calls=[]),
        ]
    )

    calc_tool = CalculatorTool()
    agent = Agent.builder().with_llm(mock_llm).with_tool(calc_tool).build()

    async def handler(event):
        if isinstance(event, MessageSent):
            published_events.append(event.message)

    agent.engine.services.events.subscribe(MessageSent, handler)

    result = await agent.run("calculate 10 * 2")

    assert result.final_output == "The result is 20."

    assistant_sent_contents = [
        msg.content for msg in published_events if msg.role == "assistant"
    ]

    # Intermediate text "Let me check the database..." should NOT be in published content
    assert "Let me check the database..." not in assistant_sent_contents
    # Final answer "The result is 20." MUST be published
    assert "The result is 20." in assistant_sent_contents


@pytest.mark.asyncio
async def test_state_store_preserves_tool_call_assistant_messages_for_multi_turn():
    """Verify StateStore preserves assistant messages with tool_calls so follow-up turns receive valid chat history."""
    from agent.builder import Agent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        side_effect=[
            LLMResponse(
                content="Let me calculate...",
                tool_calls=[
                    ToolCall(
                        id="call_99",
                        name="calculate",
                        arguments={"expression": "5 + 5"},
                    )
                ],
            ),
            LLMResponse(content="The result is 10.", tool_calls=[]),
            LLMResponse(content="The previous result was 10.", tool_calls=[]),
        ]
    )

    calc_tool = CalculatorTool()
    agent = Agent.builder().with_llm(mock_llm).with_tool(calc_tool).build()

    res1 = await agent.run("calculate 5 + 5")
    assert res1.final_output == "The result is 10."

    state = agent.engine.services.state_store.get_state()
    msgs = state["session"]["messages"]

    tool_msg_indices = [i for i, m in enumerate(msgs) if m.get("role") == "tool"]
    assert len(tool_msg_indices) > 0, "Tool message should be recorded in state store"
    for idx in tool_msg_indices:
        prev_msg = msgs[idx - 1]
        assert prev_msg.get("role") == "assistant", "Tool message must be preceded by assistant message"
        assert prev_msg.get("tool_calls") is not None, "Preceding assistant message must have tool_calls"

    res2 = await agent.run("what was the result of that?")
    assert res2.final_output == "The previous result was 10."
