#!/usr/bin/env python3
"""
Test script to verify the runtime framework refactoring works correctly.
"""

import sys
from dotenv import load_dotenv

load_dotenv()

print("Test 1: Checking core architecture imports...")
try:
    from agent.builder import Agent, AgentBuilder
    from container.services import RuntimeServices
    from core.events.base import Event
    from core.interfaces.runtime import RuntimeEngineInterface
    from core.models.context import ExecutionContext
    from runtime.llm.litellm_provider import LiteLLMProvider
    from tools.base import BaseTool
    from tools.registry import registry

    print("  ✓ All architecture imports successful")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    sys.exit(1)

print("\nTest 2: Checking tool auto-discovery...")
try:
    registry.auto_discover()
    discovered = registry.list_tools()
    print(f"  ✓ Discovered {len(discovered)} tools: {', '.join(discovered)}")
except Exception as e:
    print(f"  ✗ Auto-discovery failed: {e}")
    sys.exit(1)

print("\nTest 3: Checking Agent Builder...")
try:
    agent = Agent.builder().with_llm("deepseek/deepseek-chat").build()
    print("  ✓ Agent initialized with builder")
except Exception as e:
    print(f"  ✗ Agent Builder failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("All tests passed! ✓")
print("=" * 60)
