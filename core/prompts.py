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
