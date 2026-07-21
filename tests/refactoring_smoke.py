"""Smoke test for the agent runtime framework.

Verifies that the core architecture imports cleanly and the tool registry
auto-discovers tools. This is intentionally lightweight: it does NOT require
network, a CockroachDB instance, or an LLM API key, so it is safe to run as
part of the normal `pytest` collection.

Run the full manual smoke check (with live DB + LLM) via:
    python tests/refactoring_smoke.py
"""

import pytest


def test_core_architecture_imports():
    """The runtime kernel + service container must import without side effects."""
    from agent.builder import Agent, AgentBuilder
    from container.services import RuntimeServices
    from core.events.base import Event
    from core.interfaces.runtime import RuntimeEngineInterface
    from core.models.context import ExecutionContext
    from tools.base import BaseTool
    from tools.registry import registry

    # Sanity: the symbols we depend on actually exist
    assert Agent is not None
    assert AgentBuilder is not None
    assert RuntimeServices is not None
    assert issubclass(Event, object)
    assert BaseTool is not None
    assert registry is not None


def test_registry_auto_discovery():
    """Auto-discovery should find the built-in tools after a single scan."""
    from tools.registry import registry

    registry.auto_discover()
    discovered = registry.list_tools()
    assert len(discovered) > 0, "no tools discovered"
    # The always-present built-in tools
    assert "calculate" in discovered
    assert "query_database" in discovered


def test_agent_builder_minimal():
    """AgentBuilder must construct without any external services wired in."""
    from agent.builder import AgentBuilder

    # No LLM / DB / network required for a minimal build
    agent = AgentBuilder().build()
    assert agent.engine is not None
    assert agent.services is not None


if __name__ == "__main__":
    import os
    import sys

    # Allow running as a standalone script: ensure the repo root is importable
    # so `from agent.builder import ...` resolves regardless of CWD.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Manual mode (python tests/refactoring_smoke.py) — execute the checks and
    # report. Exits non-zero only if a check fails, after printing what broke.
    checks = [
        ("core architecture imports", test_core_architecture_imports),
        ("registry auto-discovery", test_registry_auto_discovery),
        ("agent builder minimal", test_agent_builder_minimal),
    ]
    failed = False
    for name, fn in checks:
        try:
            fn()
            print(f"  [OK] {name}")
        except Exception as e:  # noqa: BLE001
            failed = True
            print(f"  [FAIL] {name}: {e}")

    if failed:
        print("\nSome checks failed.")
        sys.exit(1)
    print("\nAll smoke checks passed!")
