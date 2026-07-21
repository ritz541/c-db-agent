"""
Tests for web search tool.
"""

import pytest
from unittest.mock import patch
from tools.web_search import WebSearchTool


class TestWebSearchMetadata:
    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    def test_name(self, tool):
        assert tool.get_name() == "web_search"

    def test_description_is_nonempty(self, tool):
        assert len(tool.get_description()) > 0

    def test_parameters_schema(self, tool):
        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "action" in params["properties"]


class TestWebSearchExecute:
    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    def test_no_api_key(self, tool, mock_db):
        conn, cursor = mock_db
        with patch("tools.web_search.os.getenv", return_value=""):
            result = tool.execute(db_conn=conn, query="test")
        assert result["success"] is False
        assert "TINYFISH_API_KEY" in result["error"]

    def test_auto_detect_url(self, tool, mock_db):
        conn, cursor = mock_db
        with (
            patch("tools.web_search.os.getenv", return_value="test-key"),
            patch("tools.web_search.requests.post") as mock_post,
        ):
            mock_post.return_value.json.return_value = {
                "text": "Job description here",
                "title": "Software Engineer - Acme"
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = tool.execute(db_conn=conn, query="https://acme.com/jobs/123")
        assert result["success"] is True
        # Auto-detect should have triggered fetch
        mock_post.assert_called()

    def test_search_success(self, tool, mock_db):
        conn, cursor = mock_db
        mock_response = [
            {"title": "Job at Acme", "url": "https://acme.com/job", "snippet": "Great job"},
        ]
        with (
            patch("tools.web_search.os.getenv", return_value="test-key"),
            patch("tools.web_search.requests.get") as mock_get,
        ):
            mock_get.return_value.json.return_value = {"results": mock_response}
            mock_get.return_value.raise_for_status = lambda: None
            result = tool.execute(db_conn=conn, query="software engineer", action="search")
        assert result["success"] is True
        assert result["count"] == 1

    def test_fetch_success(self, tool, mock_db):
        conn, cursor = mock_db
        with (
            patch("tools.web_search.os.getenv", return_value="test-key"),
            patch("tools.web_search.requests.post") as mock_post,
        ):
            mock_post.return_value.json.return_value = {
                "text": "Job description here",
                "title": "Software Engineer - Acme"
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = tool.execute(db_conn=conn, query="https://acme.com/job", action="fetch")
        assert result["success"] is True
        assert "Job description" in result["content"]

    def test_empty_args_defensive(self, tool, mock_db):
        conn, cursor = mock_db
        with patch("tools.web_search.os.getenv", return_value="test-key"):
            result = tool.execute(db_conn=conn)
        assert result["success"] is False
        assert "Missing required parameter" in result["error"]