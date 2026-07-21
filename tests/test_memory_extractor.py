"""
Tests for memory_extractor.py — extract_memory function.
"""

import json
import pytest
from unittest.mock import MagicMock, Mock, patch, AsyncMock

from core.memory_extractor import extract_memory


def make_completion_response(content: str) -> MagicMock:
    """Helper: create a mock litellm completion response with given text content."""
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = None
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return mock_response


def make_llm_client(mock_complete) -> MagicMock:
    """Helper: create a mock LLMClient."""
    client = MagicMock()
    client.complete = mock_complete
    return client


@pytest.fixture
def mock_llm():
    """Fixture for a mock LLM complete method."""
    return MagicMock()


# ── Basic extraction scenarios ──────────────────────────────────

class TestExtractMemoryBasic:
    @pytest.mark.asyncio
    async def test_create_memory_above_threshold(self, mock_llm):
        """LLM returns a memory above importance threshold → should store."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            "memory_type": "semantic",
            "importance": 8,
            "content": "User prefers Python over Java",
            "tags": ["python", "java", "preference"],
            "reason": "Important user preference",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[{"role": "user", "content": "I prefer Python"}],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=6,
        )

        assert len(result) == 1
        assert result[0]["action"] == "create"
        assert result[0]["memory_type"] == "semantic"
        assert result[0]["importance"] == 8
        assert result[0]["content"] == "User prefers Python over Java"
        assert "target_memory" not in result[0]

    @pytest.mark.asyncio
    async def test_ignore_when_should_store_false(self, mock_llm):
        """LLM returns should_store=false → should return empty list."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "ignore",
            "should_store": False,
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[{"role": "user", "content": "Hello"}],
            existing_memories=[],
            user_id="user-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_ignore_action_explicit(self, mock_llm):
        """LLM returns action=ignore → should return empty list."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "ignore",
            "should_store": True,
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_importance_below_threshold(self, mock_llm):
        """LLM returns importance below threshold → should return empty list."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            "memory_type": "episodic",
            "importance": 3,
            "content": "User yawned",
            "tags": [],
            "reason": "Not important",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=6,
        )

        assert result == []


# ── Update action ────────────────────────────────────────────────

class TestExtractMemoryUpdate:
    @pytest.mark.asyncio
    async def test_update_with_target_memory(self, mock_llm):
        """LLM returns update action with target_memory → should include target_memory_id."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "update",
            "should_store": True,
            "memory_type": "semantic",
            "importance": 9,
            "content": "User now prefers Rust over Python",
            "tags": ["rust"],
            "target_memory": "mem-123",
            "reason": "User changed preference",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[{"memory_id": "mem-123", "content": "User likes Python"}],
            user_id="user-1",
            importance_threshold=6,
        )

        assert len(result) == 1
        assert result[0]["action"] == "update"
        assert result[0]["target_memory"] == "mem-123"


# ── JSON parsing ─────────────────────────────────────────────────

class TestExtractMemoryJsonParsing:
    @pytest.mark.asyncio
    async def test_json_in_markdown_code_block(self, mock_llm):
        """LLM might wrap JSON in markdown ```json ... ``` — should parse anyway."""
        mock_llm.return_value = make_completion_response("""```json
{
    "action": "create",
    "should_store": true,
    "memory_type": "semantic",
    "importance": 7,
    "content": "User mentioned a preference",
    "tags": ["test"],
    "reason": "testing"
}
```""")

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[{"role": "user", "content": "test"}],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        assert len(result) == 1
        assert result[0]["action"] == "create"

    @pytest.mark.asyncio
    async def test_malformed_json(self, mock_llm):
        """Malformed JSON → should return empty list (caught by exception handler)."""
        mock_llm.return_value = make_completion_response("This is not JSON at all {broken")

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_extra_text_around_json(self, mock_llm):
        """Extra text before/after JSON → should extract JSON object."""
        mock_llm.return_value = make_completion_response(
            "Here's what I found:\n{\"action\": \"create\", \"should_store\": true, "
            "\"memory_type\": \"semantic\", \"importance\": 7, "
            "\"content\": \"test\", \"tags\": [], \"reason\": \"test\"}\nHope that helps!"
        )

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        assert len(result) == 1


# ── Conversation history filtering ──────────────────────────────

class TestExtractMemoryConversationFiltering:
    @pytest.mark.asyncio
    async def test_system_messages_excluded(self, mock_llm):
        """System messages should be filtered out from conversation text."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            "memory_type": "semantic",
            "importance": 7,
            "content": "User fact",
            "tags": [],
            "reason": "test",
        }))

        await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "My name is Alice"},
                {"role": "assistant", "content": "Nice to meet you Alice!"},
            ],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        # Verify that the LLM was called with a prompt that does NOT include "You are a helpful"
        # but DOES include "USER: My name is Alice"
        prompt_arg = mock_llm.call_args[1]["messages"][0]["content"]
        assert "You are a helpful" not in prompt_arg
        assert "USER: My name is Alice" in prompt_arg
        assert "ASSISTANT: Nice to meet you Alice!" in prompt_arg

    @pytest.mark.asyncio
    async def test_empty_conversation_uses_placeholder(self, mock_llm):
        """Empty conversation history should use '(no content)' placeholder."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "ignore",
            "should_store": False,
        }))

        await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
        )

        prompt_arg = mock_llm.call_args[1]["messages"][0]["content"]
        assert "(no content)" in prompt_arg


# ── Existing memories ────────────────────────────────────────────

class TestExtractMemoryExistingMemories:
    @pytest.mark.asyncio
    async def test_existing_memories_included_in_prompt(self, mock_llm):
        """Existing memories should be included in the extraction prompt."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "ignore",
            "should_store": False,
        }))

        await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[{"role": "user", "content": "Hi"}],
            existing_memories=[
                {"memory_id": "mem-1", "memory_type": "semantic", "importance": 8, "content": "User likes Python"},
            ],
            user_id="user-1",
        )

        prompt_arg = mock_llm.call_args[1]["messages"][0]["content"]
        assert "mem-1" in prompt_arg
        assert "User likes Python" in prompt_arg
        assert "[semantic]" in prompt_arg

    @pytest.mark.asyncio
    async def test_no_existing_memories_uses_placeholder(self, mock_llm):
        """When no existing memories, should use '(no existing memories)' placeholder."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "ignore",
            "should_store": False,
        }))

        await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[{"role": "user", "content": "Hi"}],
            existing_memories=[],
            user_id="user-1",
        )

        prompt_arg = mock_llm.call_args[1]["messages"][0]["content"]
        assert "(no existing memories)" in prompt_arg


# ── Tag normalization ────────────────────────────────────────────

class TestExtractMemoryTagNormalization:
    @pytest.mark.asyncio
    async def test_tags_lowercased_and_no_spaces(self, mock_llm):
        """Tags should be lowercased and spaces removed."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            "memory_type": "semantic",
            "importance": 8,
            "content": "User likes something",
            "tags": ["Python", "Machine Learning", "DATA SCIENCE"],
            "reason": "test",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        assert result[0]["tags"] == ["python", "machinelearning", "datascience"]

    @pytest.mark.asyncio
    async def test_tags_limited_to_five(self, mock_llm):
        """Tags should be capped at 5."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            "memory_type": "semantic",
            "importance": 7,
            "content": "test",
            "tags": ["a", "b", "c", "d", "e", "f", "g"],
            "reason": "test",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        assert len(result[0]["tags"]) == 5


# ── Error handling ──────────────────────────────────────────────

class TestExtractMemoryErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_throws_exception(self, mock_llm):
        """LLM throws exception → should return empty list gracefully."""
        mock_llm.side_effect = Exception("API error")

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_empty_llm_response(self, mock_llm):
        """LLM returns empty content → JSON parse fails → empty list."""
        empty_response = make_completion_response("")
        mock_llm.return_value = empty_response

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
        )

        assert result == []


# ── Default values ──────────────────────────────────────────────

class TestExtractMemoryDefaults:
    @pytest.mark.asyncio
    async def test_missing_fields_get_defaults(self, mock_llm):
        """Missing fields in LLM response should use sensible defaults."""
        mock_llm.return_value = make_completion_response(json.dumps({
            "action": "create",
            "should_store": True,
            # Missing: memory_type, tags, reason
            "importance": 8,
            "content": "Something important",
        }))

        result = await extract_memory(
            llm_client=make_llm_client(mock_llm),
            conversation_history=[],
            existing_memories=[],
            user_id="user-1",
            importance_threshold=5,
        )

        assert result[0]["memory_type"] == "episodic"  # default
        assert result[0]["tags"] == []
        assert result[0]["reason"] == ""
