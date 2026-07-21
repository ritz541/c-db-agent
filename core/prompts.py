"""
System Prompt Module

Centralizes system prompt management.
Can be extended to load prompts from files, support multiple prompts, etc.
"""

from tools.registry import registry


def get_system_prompt() -> str:
    """
    Return the system prompt for the agent.

    Uses a minimal prompt to avoid token bloat.
    Tool definitions are sent separately in the API call (tools parameter),
    so we don't need to list them here.

    Returns:
        str: System prompt (short and efficient)
    """
    return """You are a helpful AI assistant.

You have access to tools that can help accomplish tasks.
When a user asks you to do something, check if a tool can help.

Tool definitions are provided separately - use them when relevant.
Be proactive: if you can use a tool to help, use it.

CRITICAL: The database is PostgreSQL-compatible (CockroachDB). 
For listing tables, use: SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
For listing columns: SELECT column_name FROM information_schema.columns WHERE table_name = 'table_name';
Do NOT use sqlite_master or other SQLite-specific queries.

For database queries: be careful with destructive operations.
For job applications: be professional and tailored.
"""


def get_tools_description() -> str:
    """
    Generate a dynamic description of available tools.
    
    Returns:
        str: Description of all registered tools
    """
    tools = registry.list_tools()
    
    if not tools:
        return "No tools available."
    
    description = "Available tools:\n"
    for tool_name in tools:
        tool = registry.get_tool(tool_name)
        if tool:
            description += f"- **{tool_name}**: {tool.get_description()}\n"
    
    return description


def get_extraction_prompt(conversation_text: str, existing_memories_text: str) -> str:
    """
    Return the memory extraction prompt.

    Args:
        conversation_text: Recent conversation history
        existing_memories_text: Existing memories for update detection

    Returns:
        str: Formatted extraction prompt
    """
    return f"""You are a memory extraction engine. Analyze the conversation below and determine what should be remembered.

CONVERSATION:
{conversation_text}

EXISTING MEMORIES (for update detection):
{existing_memories_text}

RETURN FORMAT — JSON ONLY. No markdown, no explanation.

If nothing worth storing:
{{"action": "ignore", "should_store": false}}

If something should be stored:
{{
  "action": "create" | "update",
  "should_store": true,
  "memory_type": "working" | "episodic" | "semantic" | "procedural",
  "importance": <1-10>,
  "content": "<clear, concise statement>",
  "tags": ["tag1", "tag2"],
  "target_memory": "<memory_id to update, if action is update>",
  "reason": "<why this is worth remembering>"
}}

RULES:
- "working" memories are never stored (return action: "ignore")
- "semantic" = stable facts about the user
- "episodic" = events that happened
- "procedural" = how to do something repeatedly
- importance >= 6 means store it
- importance < 6 means ignore it
- If user corrected a previous fact, return action: "update" with target_memory
- Tags must be lowercase, no spaces, max 5 tags
- Content must be a single clear sentence"""
