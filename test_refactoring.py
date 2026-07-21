"""
Thin compatibility shim kept at the repo root.

Historically this file called ``sys.exit(1)`` at import time, which made
``pytest`` crash on collection whenever it was run from the repo root. The real
checks now live in ``tests/refactoring_smoke.py`` (pytest-native, no side
effects). This shim simply re-exports them so old references still work.
"""

from tests.refactoring_smoke import (  # noqa: F401
    test_agent_builder_minimal,
    test_core_architecture_imports,
    test_registry_auto_discovery,
)
