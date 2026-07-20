"""
FastAPI backend for c-db Agent TUI.

Wraps the refactored c-db agent in a REST API.
The Rust TUI communicates with this backend over HTTP.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sys
import os

# Add parent directory to path so we can import agent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.registry import registry
from core.chat_session import ChatSession
from core.llm_client import LLMClient
from config import get_settings

app = FastAPI(title="c-db Agent API", version="1.0.0")

# ── Request/Response Models ─────────────────────────────────────

class Message(BaseModel):
    """A chat message."""
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    """Request to chat with the agent."""
    message: str

class ChatResponse(BaseModel):
    """Response from the agent."""
    role: str = "assistant"
    content: str

class ToolInfo(BaseModel):
    """Information about a tool."""
    name: str
    description: str

# ── Initialize Agent ─────────────────────────────────────────

# Load settings
settings = get_settings()

# Initialize LLM client
llm_client = LLMClient(
    model=settings.llm_model,
    api_key=settings.deepseek_api_key
)

# Initialize tool registry
registry.auto_discover()

# Create chat session
chat_session = ChatSession(
    llm_client=llm_client,
    tool_registry=registry,
    system_prompt="You are a helpful AI assistant."
)

# ── API Endpoints ─────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "agent": "c-db", "version": "1.0.0"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the agent and get a response.
    
    This is the main endpoint for chatting with the agent.
    """
    try:
        # Process the user message
        response = chat_session.process_user_input(request.message)
        
        if response:
            return ChatResponse(content=response)
        else:
            return ChatResponse(content="I'm not sure how to respond to that.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

@app.get("/tools", response_model=List[ToolInfo])
async def list_tools():
    """
    List all available tools.
    
    Returns the list of tools that the agent can use.
    """
    tools = []
    for tool_name in registry.list_tools():
        tool = registry.get_tool(tool_name)
        if tool:
            tools.append(ToolInfo(
                name=tool.get_name(),
                description=tool.get_description()
            ))
    
    return tools

@app.get("/history", response_model=List[Message])
async def get_history():
    """
    Get the conversation history.
    
    Returns all messages in the current session.
    """
    messages = []
    for msg in chat_session.messages:
        if msg["role"] in ["user", "assistant"]:
            messages.append(Message(
                role=msg["role"],
                content=msg.get("content", "")
            ))
    
    return messages

@app.post("/reset")
async def reset_session():
    """
    Reset the conversation (start a new session).
    """
    global chat_session
    
    chat_session = ChatSession(
        llm_client=llm_client,
        tool_registry=registry,
        system_prompt="You are a helpful AI assistant."
    )
    
    return {"status": "Session reset"}

# ── Main ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    print("="*60)
    print("  c-db Agent API")
    print("  Starting FastAPI server...")
    print("="*60)
    print()
    print("  TUI Connection:")
    print("    cd c-db-tui && cargo run")
    print()
    print("  API Docs:")
    print("    http://127.0.0.1:8000/docs")
    print("="*60)
    
    uvicorn.run(app, host="127.0.0.1", port=8000)
