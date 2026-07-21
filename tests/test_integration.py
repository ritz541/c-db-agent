import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from agent.builder import Agent
from core.models.llm import LLMResponse
from core.models.tool import ToolCall
from tools.calculator import CalculatorTool
from tools.db_tool import DatabaseQueryTool
from tools.registry import ToolRegistry

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault(
    "COCKROACHDB_URL", "postgresql://test:test@localhost:26257/test"
)
os.environ.setdefault("LLM_MODEL", "deepseek/deepseek-v4-flash")


@pytest.fixture
def test_registry():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DatabaseQueryTool())
    return registry


@pytest.mark.asyncio
class TestAgentIntegration:
    """Integration tests for Agent Runtime Framework."""

    async def test_process_user_input_with_tool_call(self, test_registry, mock_db):
        conn, cursor = mock_db

        mock_llm_provider = MagicMock()
        mock_llm_provider.generate_response = AsyncMock(
            side_effect=[
                LLMResponse(
                    content="Calculating...",
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="calculate",
                            arguments={"expression": "2 + 2"},
                        )
                    ],
                ),
                LLMResponse(content="The result is 4", tool_calls=[]),
            ]
        )

        agent = (
            Agent.builder()
            .with_llm(mock_llm_provider)
            .with_tool(test_registry.get_tool("calculate"))
            .build()
        )

        with patch(
            "infrastructure.db_pool.get_connection", return_value=conn
        ), patch("infrastructure.db_pool.return_connection"):
            result = await agent.run("What is 2 + 2?")
            assert result.final_output == "The result is 4"

    async def test_process_user_input_direct_response(self):
        mock_llm_provider = MagicMock()
        mock_llm_provider.generate_response = AsyncMock(
            return_value=LLMResponse(content="Hello there!", tool_calls=[])
        )

        agent = Agent.builder().with_llm(mock_llm_provider).build()

        result = await agent.run("Hello!")
        assert result.final_output == "Hello there!"

    def test_tool_execution_with_real_calculator(self, test_registry, mock_db):
        conn, cursor = mock_db

        result = test_registry.execute(
            tool_name="calculate", args={"expression": "15 * 37"}, db_conn=conn
        )

        assert result["success"] is True
        assert result["result"] == "555"
        assert result["stored_in_db"] is True
        assert cursor.execute.called

    def test_tool_execution_error_handling(self, test_registry, mock_db):
        conn, cursor = mock_db
        cursor.execute.side_effect = Exception("Database connection lost")

        result = test_registry.execute(
            tool_name="calculate", args={"expression": "2 + 2"}, db_conn=conn
        )

        assert result["success"] is False
        assert "error" in result


class TestDatabaseIntegration:
    """Test database-related tool execution."""

    def test_calculator_inserts_data(self, test_registry, mock_db):
        conn, cursor = mock_db

        test_registry.execute(
            tool_name="calculate", args={"expression": "2 + 2"}, db_conn=conn
        )

        insert_calls = [
            call for call in cursor.execute.call_args_list if "INSERT" in str(call)
        ]
        assert len(insert_calls) > 0

    def test_database_query_with_select(self, test_registry, mock_db):
        conn, cursor = mock_db
        cursor.description = [("id",), ("expression",), ("result",)]
        cursor.fetchall.return_value = [(1, "2+2", "4")]

        result = test_registry.execute(
            tool_name="query_database",
            args={"sql": "SELECT * FROM calculations"},
            db_conn=conn,
        )

        assert result["success"] is True
        assert result["row_count"] == 1
        assert result["columns"] == ["id", "expression", "result"]
        assert result["rows"] == [[1, "2+2", "4"]]

    def test_database_query_blocked_destructive(self, test_registry, mock_db):
        conn, cursor = mock_db

        result = test_registry.execute(
            tool_name="query_database",
            args={"sql": "DROP TABLE calculations"},
            db_conn=conn,
        )

        assert result["success"] is False
        assert "BLOCKED" in result["error"]
        cursor.execute.assert_not_called()
