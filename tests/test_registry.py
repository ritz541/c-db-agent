"""
Tests for the tool registry.
"""

import pytest
from tools.registry import ToolRegistry
from tools.base import BaseTool


@pytest.fixture
def registry():
    """Fresh registry for each test (no auto-discovery)."""
    return ToolRegistry()


class DummyTool(BaseTool):
    def get_name(self):
        return "dummy"

    def get_description(self):
        return "A dummy tool for testing."

    def get_parameters(self):
        return {"type": "object", "properties": {"msg": {"type": "string"}}}

    def execute(self, db_conn, msg="hello"):
        return {"success": True, "echo": msg}


class TestRegistryRegister:
    def test_register_and_get(self, registry):
        tool = DummyTool()
        registry.register(tool)
        assert registry.get_tool("dummy") is tool

    def test_list_tools(self, registry):
        registry.register(DummyTool())
        assert "dummy" in registry.list_tools()

    def test_duplicate_register_warns(self, registry):
        registry.register(DummyTool())
        registry.register(DummyTool())  # should not raise
        assert len(registry.list_tools()) == 1

    def test_get_unknown_tool(self, registry):
        assert registry.get_tool("nonexistent") is None


class TestRegistryExecute:
    def test_execute_success(self, registry, mock_db):
        conn, cursor = mock_db
        registry.register(DummyTool())
        result = registry.execute("dummy", {"msg": "test"}, conn)
        assert result["success"] is True
        assert result["echo"] == "test"

    def test_execute_unknown_tool(self, registry, mock_db):
        conn, cursor = mock_db
        result = registry.execute("nonexistent", {}, conn)
        assert result["success"] is False
        assert "Unknown tool" in result["error"]


class TestRegistrySchemas:
    def test_schema_generation(self, registry):
        registry.register(DummyTool())
        schemas = registry.get_schemas()
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "dummy"
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


class TestRegistryClear:
    def test_clear(self, registry):
        registry.register(DummyTool())
        assert len(registry.list_tools()) == 1
        registry.clear()
        assert len(registry.list_tools()) == 0


class TestRegistryAutoDiscover:
    def test_discover_finds_tools(self):
        registry = ToolRegistry()
        registry.auto_discover()
        tools = registry.list_tools()
        assert "calculate" in tools
        assert "get_weather" in tools
        assert "query_database" in tools
        assert "store_resume" in tools

    def test_discover_idempotent(self):
        registry = ToolRegistry()
        registry.auto_discover()
        first_count = len(registry.list_tools())
        registry.auto_discover()  # second call should be no-op
        second_count = len(registry.list_tools())
        assert first_count == second_count
