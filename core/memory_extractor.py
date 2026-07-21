"""
Memory Extraction Module

Uses the LLM to analyze conversations and extract high-value memories.
"""

import json
import re

import structlog

from core.llm_client import LLMClient
from core.prompts import get_extraction_prompt


logger = structlog.get_logger()


async def extract_memory(
    llm_client: LLMClient,
    conversation_history: list[dict],
    existing_memories: list[dict],
    user_id: str,
    importance_threshold: int = 6,
) -> list[dict]:
    """
    Analyze recent conversation and extract memories worth storing.

    Args:
        llm_client: LLM client for extraction
        conversation_history: Recent messages (last N)
        existing_memories: Existing memories for update detection
        user_id: User identifier
        importance_threshold: Minimum importance to store (1-10)

    Returns:
        List of memory dicts with action, content, etc.
    """
    # Build conversation text (exclude system messages)
    conversation_parts = []
    for msg in conversation_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "system":
            continue
        conversation_parts.append(f"{role.upper()}: {content}")

    conversation_text = "\n".join(conversation_parts) if conversation_parts else "(no content)"

    # Build existing memories text
    if existing_memories:
        existing_parts = []
        for mem in existing_memories:
            existing_parts.append(
                f"[{mem.get('memory_type', 'semantic')}] "
                f"(importance={mem.get('importance', 0)}): "
                f"{mem.get('content', '')} "
                f"[id: {mem.get('memory_id', '')}]"
            )
        existing_memories_text = "\n".join(existing_parts)
    else:
        existing_memories_text = "(no existing memories)"

    prompt = get_extraction_prompt(conversation_text, existing_memories_text)

    try:
        response = llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
        )

        content = response.choices[0].message.content or ""

        # Parse JSON - handle potential markdown wrapping
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        result = json.loads(content)

        # Validate response
        if not result.get("should_store", False):
            return []

        action = result.get("action", "ignore")

        if action == "ignore":
            return []

        importance = result.get("importance", 0)

        if importance < importance_threshold:
            return []

        memory = {
            "action": action,
            "memory_type": result.get("memory_type", "episodic"),
            "importance": importance,
            "content": result.get("content", ""),
            "tags": [t.lower().replace(" ", "") for t in result.get("tags", [])[:5]],
            "reason": result.get("reason", ""),
        }

        if action == "update":
            memory["target_memory"] = result.get("target_memory")

        return [memory]

    except Exception as e:
        logger.error("memory.extraction_failed", error=str(e), user_id=user_id)
        return []