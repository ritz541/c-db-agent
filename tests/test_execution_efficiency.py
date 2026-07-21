import pytest

from agent.builder import AgentBuilder
from core.models.context import ExecutionContext
from core.models.message import AgentMessage
from core.models.tool import ToolCall, ToolResult
from runtime.middleware.deduplication import ToolDeduplicationMiddleware
from tools.db_tool import DatabaseQueryTool


@pytest.mark.asyncio
async def test_tool_deduplication_middleware():
    """Verify ToolDeduplicationMiddleware intercepts duplicate tool calls and returns cached results."""
    mw = ToolDeduplicationMiddleware()
    ctx = ExecutionContext(run_id="run_dedup_test")

    tool_call = ToolCall(id="tc_1", name="list_resumes", arguments={})
    res1 = ToolResult(tool_call_id="tc_1", success=True, output="Found 1 resume")

    # 1. First execution should pass through before_tool_execute
    intercepted1 = await mw.before_tool_execute(tool_call, context=ctx)
    assert intercepted1 is not None
    assert intercepted1.name == "list_resumes"

    # Store result in after_tool_execute
    await mw.after_tool_execute(tool_call, res1, context=ctx)

    # 2. Second execution with identical args should be intercepted (return None)
    intercepted2 = await mw.before_tool_execute(tool_call, context=ctx)
    assert intercepted2 is None

    # Cached result should match res1
    cached = mw.get_cached_result(tool_call, context=ctx)
    assert cached is not None
    assert cached.output == "Found 1 resume"


def test_agent_builder_registers_deduplication_middleware():
    """Verify AgentBuilder includes ToolDeduplicationMiddleware by default."""
    agent = AgentBuilder().build()
    middleware_types = [type(m) for m in agent.engine.middleware]
    assert ToolDeduplicationMiddleware in middleware_types


def test_database_query_tool_schema_description():
    """Verify DatabaseQueryTool description documents resumes and applications tables."""
    desc = DatabaseQueryTool().get_description()
    assert "resumes" in desc
    assert "applications" in desc
    assert "calculations" in desc
