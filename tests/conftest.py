"""
Test configuration and fixtures.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path so we can import tools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_db():
    """
    Mock database connection that supports the `with conn.cursor() as cur:` pattern.

    Usage in tests:
        conn, cursor = mock_db
        cursor.fetchone.return_value = (1,)
        result = tool.execute(db_conn=conn, ...)
    """
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


@pytest.fixture
def mock_llm():
    """Mock LLM API calls."""
    with patch("litellm.completion") as mock:
        yield mock
