"""
Tests for the calculator tool.
"""

import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calculator import calculate


def test_calculate_basic():
    """Test basic math expression."""
    mock_conn = MagicMock()
    result = calculate("2 + 2", db_conn=mock_conn)
    assert result["success"] == True
    assert result["result"] == "4"


def test_calculate_multiplication():
    """Test multiplication."""
    mock_conn = MagicMock()
    result = calculate("15 * 37", db_conn=mock_conn)
    assert result["success"] == True
    assert result["result"] == "555"


def test_calculate_sqrt():
    """Test square root."""
    mock_conn = MagicMock()
    result = calculate("sqrt(144)", db_conn=mock_conn)
    assert result["success"] == True
    assert result["result"] == "12.0"


def test_calculate_invalid():
    """Test invalid expression."""
    mock_conn = MagicMock()
    result = calculate("not_a_math_expression", db_conn=mock_conn)
    assert result["success"] == False
    assert "error" in result
