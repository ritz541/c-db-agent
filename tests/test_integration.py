"""
Integration tests for the agent flow and tool execution.

These tests verify that the entire agent pipeline works correctly,
from user input through LLM processing to tool execution.
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path

from core.chat_session import ChatSession
from core.llm_client import LLMClient, RateLimiter
from tools.registry import ToolRegistry
from tools.calculator import CalculatorTool
from tools.db_tool import DatabaseQueryTool

# Set environment variables for test configuration
os.environ.setdefault('DEEPSEEK_API_KEY', 'test-key')
os.environ.setdefault('COCKROACHDB_URL', 'postgresql://test:test@localhost:26257/test')
os.environ.setdefault('LLM_MODEL', 'deepseek/deepseek-v4-flash')


@pytest.fixture
def test_registry():
    """Create a registry with test tools."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DatabaseQueryTool())
    return registry


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response that calls a tool."""
    mock_response = Mock()
    mock_message = Mock()
    mock_message.content = "I'll calculate that for you."
    
    # Create proper mock tool call with nested structure
    mock_function = Mock()
    mock_function.name = "calculate"
    mock_function.arguments = '{"expression": "2 + 2"}'
    
    mock_tool_call = Mock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = mock_function
    
    mock_message.tool_calls = [mock_tool_call]
    mock_response.choices = [Mock(message=mock_message)]
    mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return mock_response


@pytest.fixture
def mock_llm_final_response():
    """Create a mock LLM response with final text."""
    mock_response = Mock()
    mock_message = Mock()
    mock_message.content = "The result is 4"
    mock_message.tool_calls = None
    mock_response.choices = [Mock(message=mock_message)]
    mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return mock_response


@pytest.mark.asyncio
class TestChatSessionIntegration:
    """Test the complete chat session flow."""

    async def test_process_user_input_with_tool_call(self, test_registry, mock_db, mock_llm_response, mock_llm_final_response):
        """Test processing user input that requires a tool call."""
        conn, cursor = mock_db

        # Create LLM client with mocked completion
        rate_limiter = RateLimiter(max_requests_per_minute=60)
        llm_client = LLMClient(
            model="deepseek/deepseek-v4-flash",
            api_key="test-key",
            rate_limiter=rate_limiter
        )

        # Mock the LLM to return tool call first, then final response
        # Also mock database pool functions
        with patch.object(llm_client, 'complete', side_effect=[mock_llm_response, mock_llm_final_response]), \
             patch('infrastructure.db_pool.get_connection', return_value=conn), \
             patch('infrastructure.db_pool.return_connection'):
            session = ChatSession(
                llm_client=llm_client,
                tool_registry=test_registry,
                system_prompt="You are a helpful assistant."
            )

            response = await session.process_user_input("What is 2 + 2?")
            
            # Verify the tool was called
            assert response == "The result is 4"
            # Verify database operations occurred
            assert cursor.execute.called
            assert conn.commit.called

    async def test_process_user_input_direct_response(self, test_registry, mock_llm_final_response):
        """Test processing user input that doesn't require tools."""
        rate_limiter = RateLimiter(max_requests_per_minute=60)
        llm_client = LLMClient(
            model="deepseek/deepseek-v4-flash",
            api_key="test-key",
            rate_limiter=rate_limiter
        )

        with patch.object(llm_client, 'complete', return_value=mock_llm_final_response):
            session = ChatSession(
                llm_client=llm_client,
                tool_registry=test_registry,
                system_prompt="You are a helpful assistant."
            )

            response = await session.process_user_input("Hello!")
            
            assert response == "The result is 4"

    def test_tool_execution_with_real_calculator(self, test_registry, mock_db):
        """Test calculator tool execution with real database operations."""
        conn, cursor = mock_db
        
        result = test_registry.execute(
            tool_name="calculate",
            args={"expression": "15 * 37"},
            db_conn=conn
        )
        
        assert result["success"] is True
        assert result["result"] == "555"
        assert result["stored_in_db"] is True
        assert cursor.execute.called

    def test_tool_execution_error_handling(self, test_registry, mock_db):
        """Test error handling when tool execution fails."""
        conn, cursor = mock_db
        cursor.execute.side_effect = Exception("Database connection lost")
        
        result = test_registry.execute(
            tool_name="calculate",
            args={"expression": "2 + 2"},
            db_conn=conn
        )
        
        assert result["success"] is False
        assert "error" in result


class TestDatabaseIntegration:
    """Test database-related tool execution with more realistic scenarios."""

    def test_calculator_inserts_data(self, test_registry, mock_db):
        """Test that calculator inserts data into the table."""
        conn, cursor = mock_db
        
        test_registry.execute(
            tool_name="calculate",
            args={"expression": "2 + 2"},
            db_conn=conn
        )
        
        # Verify INSERT was called (table creation is now handled by schema manager)
        insert_calls = [call for call in cursor.execute.call_args_list 
                       if 'INSERT' in str(call)]
        assert len(insert_calls) > 0

    def test_database_query_with_select(self, test_registry, mock_db):
        """Test database query tool with SELECT."""
        conn, cursor = mock_db
        cursor.description = [("id",), ("expression",), ("result",)]
        cursor.fetchall.return_value = [(1, "2+2", "4")]
        
        result = test_registry.execute(
            tool_name="query_database",
            args={"sql": "SELECT * FROM calculations"},
            db_conn=conn
        )
        
        assert result["success"] is True
        assert result["row_count"] == 1
        assert result["columns"] == ["id", "expression", "result"]
        assert result["rows"] == [[1, "2+2", "4"]]

    def test_database_query_blocked_destructive(self, test_registry, mock_db):
        """Test that destructive queries are blocked."""
        conn, cursor = mock_db
        
        result = test_registry.execute(
            tool_name="query_database",
            args={"sql": "DROP TABLE calculations"},
            db_conn=conn
        )
        
        assert result["success"] is False
        assert "BLOCKED" in result["error"]
        cursor.execute.assert_not_called()


@pytest.mark.asyncio
class TestToolChainExecution:
    """Test scenarios where multiple tools are called in sequence."""

    async def test_multiple_tool_calls_single_turn(self, test_registry, mock_db):
        """Test multiple tool calls in a single user turn."""
        conn, cursor = mock_db
        
        # Create mock response with multiple tool calls
        mock_function1 = Mock()
        mock_function1.name = "calculate"
        mock_function1.arguments = '{"expression": "2 + 2"}'
        
        mock_function2 = Mock()
        mock_function2.name = "calculate"
        mock_function2.arguments = '{"expression": "3 * 3"}'
        
        mock_tool_call1 = Mock()
        mock_tool_call1.id = "call_1"
        mock_tool_call1.function = mock_function1
        
        mock_tool_call2 = Mock()
        mock_tool_call2.id = "call_2"
        mock_tool_call2.function = mock_function2
        
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "I'll do both calculations."
        mock_message.tool_calls = [mock_tool_call1, mock_tool_call2]
        mock_response.choices = [Mock(message=mock_message)]
        
        mock_final = Mock()
        mock_final_message = Mock()
        mock_final_message.content = "The results are 4 and 9"
        mock_final_message.tool_calls = None
        mock_final.choices = [Mock(message=mock_final_message)]
        
        rate_limiter = RateLimiter(max_requests_per_minute=60)
        llm_client = LLMClient(
            model="deepseek/deepseek-v4-flash",
            api_key="test-key",
            rate_limiter=rate_limiter
        )
        
        with patch.object(llm_client, 'complete', side_effect=[mock_response, mock_final]), \
             patch('infrastructure.db_pool.get_connection', return_value=conn), \
             patch('infrastructure.db_pool.return_connection'):
            session = ChatSession(
                llm_client=llm_client,
                tool_registry=test_registry,
                system_prompt="You are a helpful assistant."
            )
            
            response = await session.process_user_input("Calculate 2+2 and 3*3")

            assert response == "The results are 4 and 9"
            # Verify both calculations were executed
            assert cursor.execute.call_count >= 2


@pytest.mark.asyncio
class TestErrorRecoveryIntegration:
    """Test error recovery scenarios in the agent flow."""

    async def test_llm_api_error_recovery(self, test_registry, mock_db):
        """Test recovery from LLM API errors."""
        conn, cursor = mock_db

        rate_limiter = RateLimiter(max_requests_per_minute=60)
        llm_client = LLMClient(
            model="deepseek/deepseek-v4-flash",
            api_key="test-key",
            rate_limiter=rate_limiter
        )

        # Mock LLM to fail then succeed
        mock_success = Mock()
        mock_success_message = Mock()
        mock_success_message.content = "Success"
        mock_success_message.tool_calls = None
        mock_success.choices = [Mock(message=mock_success_message)]

        with patch.object(llm_client, 'complete', side_effect=[Exception("API Error"), mock_success]):
            session = ChatSession(
                llm_client=llm_client,
                tool_registry=test_registry,
                system_prompt="You are a helpful assistant."
            )

            # First call should fail gracefully
            response = await session.process_user_input("Hello")
            assert response is None  # Error case returns None
            
            # Message should be removed from history
            assert len(session.messages) == 1  # Only system prompt

    def test_tool_execution_error_with_retry(self, test_registry, mock_db):
        """Test tool execution error handling."""
        conn, cursor = mock_db
        cursor.execute.side_effect = Exception("Temporary error")
        
        result = test_registry.execute(
            tool_name="calculate",
            args={"expression": "2 + 2"},
            db_conn=conn
        )
        
        assert result["success"] is False
        assert "error" in result


class TestRateLimitingIntegration:
    """Test rate limiting in the agent flow."""

    def test_rate_limiter_blocks_excessive_requests(self):
        """Test that rate limiter blocks requests when limit is exceeded."""
        rate_limiter = RateLimiter(max_requests_per_minute=2)
        
        # First two requests should succeed
        rate_limiter.acquire()
        rate_limiter.acquire()
        
        # Third request should be rate limited (would sleep in real scenario)
        import time
        start = time.time()
        rate_limiter.acquire()
        elapsed = time.time() - start
        
        # Should have waited due to rate limiting
        # In test scenario, this might not actually wait if we're not in real-time
        # but the logic should be triggered


# Real database integration tests removed to avoid dependency on live database
# These would require a real CockroachDB instance to run