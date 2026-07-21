import json
import re
from typing import Any
import structlog

from core.interfaces.llm import LLMProviderInterface
from core.models.context import ExecutionContext
from core.models.memory import MemoryItem
from core.models.message import AgentMessage

logger = structlog.get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a Memory Extraction Assistant. Analyze the conversation history and extract high-value facts or user preferences.
Return JSON array of memory objects with fields:
- content (string)
- memory_type (string, e.g. "preference", "fact", "constraint")
- importance (float, 0.0 to 1.0)
- tags (list of strings)
"""


async def extract_memories(
    llm_provider: LLMProviderInterface,
    messages: list[AgentMessage],
    context: ExecutionContext | None = None,
) -> list[MemoryItem]:
    """Extract memory items from conversation messages using LLM."""
    if not messages:
        return []

    convo_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
    prompt_messages = [
        AgentMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
        AgentMessage(
            role="user", content=f"Extract memories from this conversation:\n{convo_text}"
        ),
    ]

    try:
        response = await llm_provider.generate_response(
            messages=prompt_messages, context=context
        )
        content = response.content or ""

        # Extract JSON from markdown code blocks or text
        json_match = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        if json_match:
            raw_json = json_match.group(0)
        else:
            raw_json = content

        extracted_data = json.loads(raw_json)
        memories = []
        if isinstance(extracted_data, list):
            for item in extracted_data:
                if isinstance(item, dict) and "content" in item:
                    memories.append(
                        MemoryItem(
                            content=item["content"],
                            memory_type=item.get("memory_type", "general"),
                            importance=float(item.get("importance", 0.5)),
                            tags=item.get("tags", []),
                        )
                    )
        return memories
    except Exception as e:
        logger.warning("memory_extractor.failed", error=str(e))
        return []
