#!/usr/bin/env python3
"""
Test script to verify the refactoring works correctly.
"""

import sys
from dotenv import load_dotenv
load_dotenv()

# Test 1: Check imports
print("Test 1: Checking imports...")
try:
    from tools.base import BaseTool
    from tools.registry import registry
    from core.llm_client import LLMClient
    from core.chat_session import ChatSession
    from core.prompts import get_system_prompt
    from infrastructure.db_pool import init_db_pool, get_connection, close_pool
    print("  ✓ All imports successful")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Check tool auto-discovery
print("\nTest 2: Checking tool auto-discovery...")
try:
    registry.auto_discover()
    tools = registry.list_tools()
    print(f"  ✓ Discovered {len(tools)} tools: {', '.join(tools)}")
    
    # Verify all expected tools are present
    expected_tools = [
        "calculate", "query_database", 
        "store_resume", "list_resumes", "load_resume_from_pdf",
        "draft_application", "list_applications", "send_email"
    ]
    
    missing = [t for t in expected_tools if t not in tools]
    if missing:
        print(f"  ✗ Missing tools: {', '.join(missing)}")
        sys.exit(1)
    else:
        print(f"  ✓ All expected tools found")
        
except Exception as e:
    print(f"  ✗ Auto-discovery failed: {e}")
    sys.exit(1)

# Test 3: Check tool schema generation
print("\nTest 3: Checking tool schemas...")
try:
    schemas = registry.get_schemas()
    print(f"  ✓ Generated {len(schemas)} schemas")
    
    # Verify schema structure
    for schema in schemas:
        assert "type" in schema
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
    
    print("  ✓ All schemas have correct structure")
    
except Exception as e:
    print(f"  ✗ Schema generation failed: {e}")
    sys.exit(1)

# Test 4: Check database pool
print("\nTest 4: Checking database pool...")
try:
    from config import get_settings
    settings = get_settings()
    init_db_pool(settings.cockroachdb_url)
    
    conn = get_connection()
    assert conn is not None
    print("  ✓ Database pool initialized")
    
    # Test a simple query
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        result = cur.fetchone()
        assert result[0] == 1
        print("  ✓ Database connection works")
    
    close_pool()
    print("  ✓ Database pool closed")
    
except Exception as e:
    print(f"  ✗ Database pool failed: {e}")
    sys.exit(1)

# Test 5: Check LLM client
print("\nTest 5: Checking LLM client...")
try:
    from config import get_settings
    settings = get_settings()
    
    llm_client = LLMClient(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key
    )
    print("  ✓ LLM client initialized")
    
except Exception as e:
    print(f"  ✗ LLM client failed: {e}")
    sys.exit(1)

# Test 6: Check system prompt
print("\nTest 6: Checking system prompt...")
try:
    prompt = get_system_prompt()
    assert len(prompt) > 0
    print(f"  ✓ System prompt generated ({len(prompt)} chars)")
    
except Exception as e:
    print(f"  ✗ System prompt failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("=" * 60)
print("\nThe refactoring is working correctly:")
print("  - Tools are auto-discovered")
print("  - Schemas are generated correctly")
print("  - Database pool works")
print("  - LLM client initializes")
print("  - System prompt loads")
print("\nNext step: Add a new tool to verify the plugin architecture!")
