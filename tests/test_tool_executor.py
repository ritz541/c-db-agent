import pytest
from unittest.mock import MagicMock, patch

from core.models.tool import ToolCall
from runtime.execution.tool_executor import ToolExecutor
from tools.calculator import CalculatorTool
from tools.db_tool import DatabaseQueryTool


@pytest.mark.asyncio
async def test_tool_executor_preserves_full_structured_payload():
    """Verify ToolExecutor serializes full dict payloads (including rows/columns) instead of discarding them."""
    db_tool = DatabaseQueryTool()
    executor = ToolExecutor([db_tool])

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.description = [("id",), ("company",), ("status",)]
    mock_cursor.fetchall.return_value = [(1, "Acme Corp", "sent"), (2, "Google", "sent")]

    tc = ToolCall(id="tc_db", name="query_database", arguments={"sql": "SELECT * FROM applications WHERE status = 'sent';"})

    with patch("infrastructure.db_pool.get_connection", return_value=mock_conn):
        res = await executor.execute_tool(tc)

    assert res.success is True
    assert "Acme Corp" in res.output, "Tool output must preserve row data"
    assert "Google" in res.output, "Tool output must preserve row data"
    assert "Query returned 2 row(s)" in res.output


@pytest.mark.asyncio
async def test_tool_executor_runs_calculator():
    """Sanity that the executor dispatches to a registered tool."""
    executor = ToolExecutor([CalculatorTool()])
    tc = ToolCall(id="tc_calc", name="calculate", arguments={"expression": "3 + 4"})
    res = await executor.execute_tool(tc)
    assert res.success is True
    assert "7" in res.output
