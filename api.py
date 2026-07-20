"""
FastAPI backend for c-db Agent TUI.

Wraps the refactored c-db agent in a REST API.
The Rust TUI communicates with this backend over HTTP.
"""

from contextlib import asynccontextmanager
import json as py_json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import sys
import os

# Add parent directory to path so we can import agent modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.registry import registry
from core.chat_session import ChatSession
from core.llm_client import LLMClient
from config import get_settings
import structlog

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    yield
    close_pool()


app = FastAPI(title="c-db Agent API", version="1.0.0", lifespan=lifespan)

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

# Initialize database connection pool
from infrastructure.db_pool import init_db_pool, close_pool
try:
    init_db_pool(settings.cockroachdb_url)
    print("  ✓ Database pool initialized")
except Exception as e:
    print(f"  ⚠ Database pool failed (tools that need DB won't work): {e}")

# Initialize LLM client
llm_client = LLMClient(
    model=settings.llm_model,
    api_key=settings.deepseek_api_key
)

# Initialize tool registry
registry.auto_discover()

# Create chat session with proper system prompt
from core.prompts import get_system_prompt
chat_session = ChatSession(
    llm_client=llm_client,
    tool_registry=registry,
    system_prompt=get_system_prompt()
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

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Send a message to the agent and stream the response as SSE.
    
    Each event is a JSON line with either:
    - {"token": "text"} for streaming content
    - {"done": true} when complete
    - {"error": "msg"} on error
    """
    async def event_generator():
        try:
            # Add user message to session history
            chat_session.messages.append({
                "role": "user",
                "content": request.message
            })
            
            # Step 1: Non-streaming call to detect tool calls
            response = llm_client.complete(
                messages=chat_session.messages,
                tools=registry.get_schemas()
            )
            
            response_message = response.choices[0].message
            
            # Step 2: Handle tool calls (non-streaming)
            while response_message.tool_calls:
                chat_session.messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    try:
                        args = py_json.loads(tool_call.function.arguments)
                    except py_json.JSONDecodeError:
                        args = {}
                    
                    from infrastructure.db_pool import get_connection, return_connection
                    conn = get_connection()
                    try:
                        result = registry.execute(
                            tool_name=tool_call.function.name,
                            args=args,
                            db_conn=conn
                        )
                    except Exception as tool_e:
                        result = {"success": False, "error": str(tool_e)}
                    finally:
                        return_connection(conn)
                    
                    chat_session.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": py_json.dumps(result),
                    })
                
                # After tools, make another call to get final response
                response = llm_client.complete(
                    messages=chat_session.messages,
                    tools=registry.get_schemas()
                )
                response_message = response.choices[0].message
            
            # Step 3: Stream the final text response token by token
            final_content = response_message.content or ""
            assistant_msg = {"role": "assistant", "content": final_content}
            chat_session.messages.append(assistant_msg)
            
            # Stream chunks of the response
            chunk_size = 8
            for i in range(0, len(final_content), chunk_size):
                token = final_content[i:i+chunk_size]
                yield f"data: {py_json.dumps({'token': token})}\n\n"
                import asyncio
                await asyncio.sleep(0.01)
            
            yield f"data: {py_json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            logger.error("chat.stream_error", error=str(e))
            yield f"data: {py_json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

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
