"""
Tests for the calculator tool.
"""

import pytest
from tools.calculator import CalculatorTool


@pytest.fixture
def tool():
    return CalculatorTool()


class TestCalculatorMetadata:
    def test_name(self, tool):
        assert tool.get_name() == "calculate"

    def test_description_is_nonempty(self, tool):
        assert len(tool.get_description()) > 0

    def test_parameters_schema(self, tool):
        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "expression" in params["properties"]
        assert "expression" in params["required"]


class TestCalculatorExecute:
    def test_basic_addition(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="2 + 2")
        assert result["success"] is True
        assert result["result"] == "4"
        cursor.execute.assert_called()

    def test_multiplication(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="15 * 37")
        assert result["success"] is True
        assert result["result"] == "555"

    def test_sqrt(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="sqrt(144)")
        assert result["success"] is True
        assert result["result"] == "12.0"

    def test_trig(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="sin(0)")
        assert result["success"] is True
        assert result["result"] == "0.0"

    def test_complex_expression(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="sqrt(144) + 8 * 2")
        assert result["success"] is True
        assert result["result"] == "28.0"

    def test_invalid_expression(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="not_a_math_expression")
        assert result["success"] is False
        assert "error" in result

    def test_division_by_zero(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="1 / 0")
        assert result["success"] is False

    def test_stored_in_db(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="2 + 2")
        assert result["stored_in_db"] is True
        conn.commit.assert_called()

    def test_eval_safety(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="__import__('os').system('ls')")
        assert result["success"] is False

    def test_pi_constant(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, expression="pi")
        assert result["success"] is True
        assert "3.14" in result["result"]
