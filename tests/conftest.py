"""
Test configuration and fixtures.
"""

import pytest
import sys
import os

# Add parent directory to path so we can import tools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def mock_llm():
    """Mock LLM API calls."""
    with pytest.mock.patch("litellm.completion") as mock:
        yield mock


@pytest.fixture
def mock_db_conn():
    """Mock database connection."""
    conn = pytest.mock.MagicMock()
    yield conn
    conn.close()
