"""
Test configuration and fixtures.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, Mock
import tempfile

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


@pytest.fixture
def mock_settings():
    """Mock configuration settings for testing."""
    os.environ.setdefault('DEEPSEEK_API_KEY', 'test-key')
    os.environ.setdefault('COCKROACHDB_URL', 'postgresql://test:test@localhost:26257/test')
    os.environ.setdefault('LLM_MODEL', 'deepseek/deepseek-v4-flash')
    
    from config import Settings
    return Settings()


@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for testing email tools."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
        f.write("%PDF-1.4\n%fake pdf content")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def sample_resume_data():
    """Sample resume data for testing."""
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-0123",
        "skills": ["Python", "JavaScript", "SQL"],
        "experience": [
            {
                "company": "Tech Corp",
                "role": "Software Engineer",
                "years": "2020-2023"
            }
        ]
    }
