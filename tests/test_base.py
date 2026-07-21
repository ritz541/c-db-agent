"""
Tests for BaseTool abstract class and schema generation.
"""

import pytest
from tools.base import BaseTool


class TestBaseToolAbstract:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseTool()

    def test_must_implement_all_methods(self):
        class IncompleteTool(BaseTool):
            def get_name(self):
                return "incomplete"

            # Missing: get_description, get_parameters, execute

        with pytest.raises(TypeError):
            IncompleteTool()


class ConcreteTool(BaseTool):
    def get_name(self):
        return "concrete"

    def get_description(self):
        return "A concrete test tool."

    def get_parameters(self):
        return {
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        }

    def execute(self, db_conn, input=""):
        return {"success": True, "output": input}


class TestBaseToolSchema:
    def test_get_schema_format(self):
        tool = ConcreteTool()
        schema = tool.get_schema()
        assert schema == {
            "type": "function",
            "function": {
                "name": "concrete",
                "description": "A concrete test tool.",
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                },
            },
        }

    def test_schema_has_required_keys(self):
        tool = ConcreteTool()
        schema = tool.get_schema()
        assert "type" in schema
        assert "function" in schema
        func = schema["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
