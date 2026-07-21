"""
Tests for the database query tool.
"""

import pytest
from datetime import datetime, date, time
from decimal import Decimal
from unittest.mock import MagicMock

from tools.db_tool import DatabaseQueryTool, is_safe_query, _serialize_value


# ── Tests for is_safe_query() ────────────────────────────────────────


class TestIsSafeQuery:
    def test_select_is_safe(self):
        assert is_safe_query("SELECT * FROM calculations") is True

    def test_insert_is_safe(self):
        assert is_safe_query("INSERT INTO calculations (expr) VALUES ('1+1')") is True

    def test_create_table_is_safe(self):
        assert is_safe_query("CREATE TABLE IF NOT EXISTS items (id SERIAL)") is True

    def test_drop_table_blocked(self):
        assert is_safe_query("DROP TABLE calculations") is False

    def test_drop_database_blocked(self):
        assert is_safe_query("DROP DATABASE mydb") is False

    def test_truncate_blocked(self):
        assert is_safe_query("TRUNCATE TABLE calculations") is False

    def test_delete_blocked(self):
        assert is_safe_query("DELETE FROM calculations WHERE id = 1") is False

    def test_update_blocked(self):
        assert is_safe_query("UPDATE calculations SET result = '0'") is False

    def test_comment_bypass_blocked(self):
        sql = "-- harmless\nDROP TABLE calculations"
        assert is_safe_query(sql) is False

    def test_case_insensitive(self):
        assert is_safe_query("drop table calculations") is False
        assert is_safe_query("select * from calculations") is True


# ── Tests for _serialize_value() ─────────────────────────────────────


class TestSerializeValue:
    def test_datetime(self):
        dt = datetime(2026, 7, 21, 12, 0, 0)
        assert _serialize_value(dt) == "2026-07-21T12:00:00"

    def test_date(self):
        d = date(2026, 7, 21)
        assert _serialize_value(d) == "2026-07-21"

    def test_time(self):
        t = time(12, 0, 0)
        assert _serialize_value(t) == "12:00:00"

    def test_decimal(self):
        assert _serialize_value(Decimal("3.14")) == 3.14

    def test_bytes(self):
        assert _serialize_value(b"hello") == "hello"

    def test_set(self):
        assert _serialize_value({1, 2, 3}) == [1, 2, 3]

    def test_passthrough(self):
        assert _serialize_value(42) == 42
        assert _serialize_value("text") == "text"
        assert _serialize_value(None) is None
        assert _serialize_value(True) is True


# ── Tests for DatabaseQueryTool ──────────────────────────────────────


@pytest.fixture
def tool():
    return DatabaseQueryTool()


class TestDatabaseQueryMetadata:
    def test_name(self, tool):
        assert tool.get_name() == "query_database"

    def test_description_is_nonempty(self, tool):
        assert len(tool.get_description()) > 0

    def test_parameters_schema(self, tool):
        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "sql" in params["properties"]
        assert "sql" in params["required"]


class TestDatabaseQueryExecute:
    def test_select_returns_rows(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.description = [("id",), ("expression",)]
        cursor.fetchall.return_value = [(1, "2+2")]
        result = tool.execute(db_conn=conn, sql="SELECT id, expression FROM calculations")
        assert result["success"] is True
        assert result["columns"] == ["id", "expression"]
        assert result["rows"] == [[1, "2+2"]]
        assert result["row_count"] == 1

    def test_select_empty(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.description = [("id",)]
        cursor.fetchall.return_value = []
        result = tool.execute(db_conn=conn, sql="SELECT * FROM calculations")
        assert result["success"] is True
        assert result["row_count"] == 0

    def test_insert_no_rows(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.description = None
        cursor.rowcount = 1
        result = tool.execute(db_conn=conn, sql="INSERT INTO calculations (expr) VALUES ('1+1')")
        assert result["success"] is True
        conn.commit.assert_called()

    def test_blocked_query(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, sql="DROP TABLE calculations")
        assert result["success"] is False
        assert "BLOCKED" in result["error"]
        cursor.execute.assert_not_called()

    def test_sql_error(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.execute.side_effect = Exception("relation \"fake_table\" does not exist")
        result = tool.execute(db_conn=conn, sql="SELECT * FROM fake_table")
        assert result["success"] is False
        assert "does not exist" in result["error"]
