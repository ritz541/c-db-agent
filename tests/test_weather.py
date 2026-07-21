"""
Tests for the weather tool.
"""

import pytest
from tools.weather import WeatherTool


@pytest.fixture
def tool():
    return WeatherTool()


class TestWeatherMetadata:
    def test_name(self, tool):
        assert tool.get_name() == "get_weather"

    def test_description_is_nonempty(self, tool):
        assert len(tool.get_description()) > 0

    def test_parameters_schema(self, tool):
        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "city" in params["properties"]
        assert "city" in params["required"]


class TestWeatherExecute:
    def test_known_city(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, city="San Francisco")
        assert result["success"] is True
        assert result["temperature"] == 65
        assert result["condition"] == "foggy"

    def test_another_city(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, city="Tokyo")
        assert result["success"] is True
        assert result["temperature"] == 80

    def test_unknown_city(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, city="Mars")
        assert result["success"] is False
        assert "not available" in result["error"].lower()
