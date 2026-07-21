# ADR-001: Core Kernel Architecture & Decoupled Runtime

## Status
Accepted

## Context
`c-db` evolved from a basic script calling LiteLLM into a complex agent codebase. To support multiple frontends (Textual UI, CLI, web APIs, Discord bots) and maintainable extension, the core kernel must be completely decoupled from concrete infrastructure providers and UI frameworks.

## Decision
We enforce a strict layered architecture centered around `core/`:
1. **Zero External Dependencies in `core/`**: The core kernel contains only interfaces, domain models, event definitions, error hierarchies, and constants.
2. **Interface Axiom**: All framework components implement abstract base classes in `core/interfaces/`.
3. **Decoupled UI**: UI components exist outside the kernel (e.g. `ui/cli/runner.py`), interacting with the runtime strictly through the `RuntimeEngineInterface` and consuming events from `EventBus`.

## Consequences
- Clean separation of concerns allows swapping LLM providers, state stores, or memory backends without modifying business logic.
- UI adapters can be developed independently without tightly coupling to backend execution logic.
