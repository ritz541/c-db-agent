import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from core.models.llm import LLMResponse
from core.models.message import AgentMessage
from runtime.memory.extractor import extract_memories


@pytest.mark.asyncio
class TestExtractMemories:

    async def test_extract_memories_success(self):
        mock_llm_provider = MagicMock()
        mock_json_content = json.dumps(
            [
                {
                    "content": "User prefers Python",
                    "memory_type": "preference",
                    "importance": 0.8,
                    "tags": ["python"],
                }
            ]
        )
        mock_llm_provider.generate_response = AsyncMock(
            return_value=LLMResponse(content=mock_json_content, tool_calls=[])
        )

        messages = [
            AgentMessage(role="user", content="I prefer using Python for scripting.")
        ]
        memories = await extract_memories(mock_llm_provider, messages)

        assert len(memories) == 1
        assert memories[0].content == "User prefers Python"
        assert memories[0].memory_type == "preference"
        assert memories[0].importance == 0.8

    async def test_extract_memories_empty(self):
        mock_llm_provider = MagicMock()
        messages = []
        memories = await extract_memories(mock_llm_provider, messages)
        assert memories == []
