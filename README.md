# 🤖 c-db Agent

An **event-driven AI agent runtime** (built with LiteLLM + DeepSeek) with a pluggable
tool system. It ships pre-wired as a **job-application assistant** — calculator,
CockroachDB query, resume/email tools, web search — but the runtime kernel is
generic and can host any tool set.

> **Name note:** `c-db` = "CockroachDB". The runtime itself is database-agnostic;
> CockroachDB is just the default backing store for the bundled job-assistant tools.

## ✨ Features

- **Event-driven runtime kernel** — `core/interfaces/*` abstraction layer, a
  `RuntimeServices` container, and an `EventBus` with typed domain events
  (`MessageReceived`, `ToolStarted`, `PlanCreated`, `StepFinished`, …).
- **Pluggable LLM / memory / planner / scheduler** — swap any backend behind its
  interface. Defaults: `LiteLLMProvider`, `QdrantMemoryService`, `DirectPlanner`,
  `DAGScheduler`.
- **DAG scheduler** — the planner's plan is executed by a real concurrency-bounded
  DAG scheduler (critical-path analysis, deadlock detection, per-step metrics).
  The engine consumes the scheduler's results directly.
- **Tool middleware pipeline** — `ToolDeduplicationMiddleware` suppresses duplicate
  tool calls within a run; `LoggingMiddleware` / `TimingMiddleware` instrument runs.
- **Plugin architecture** — drop a `BaseTool` subclass in `tools/` and it is
  auto-discovered on startup.
- **SQL safety** — `db_tool` validates every query with **sqlglot AST parsing**
  (not regex), blocking `DROP / TRUNCATE / DELETE / UPDATE`.
- **Observability** — structured logging via `structlog` and optional Sentry spans.

### Current Tools (bundled job-assistant set)

| Tool | Description |
|------|-------------|
| **🔢 Calculator** | Evaluate math expressions (`15 * 37`, `sqrt(144) + 8`). Results stored in CockroachDB. |
| **🗄️ Database Query** | Natural language → SQL with safety filters (blocks destructive operations). Schema is configurable (see below). |
| **📄 Resume Tools** | Store, list, and load resumes from PDF. |
| **✉️ Email Tools** | Draft tailored cover letters and send via SMTP. |
| **🌐 Web Search** | Search for job postings or fetch job descriptions from URLs. |
| **🌤️ Weather** | Demo plugin (auto-discovered). |

### Configurable DB schema (#4)

`DatabaseQueryTool` is **not hard-coded** to the job-assistant tables. The known
table schema is passed in at construction and rendered into the tool description the
LLM sees, so you can point it at any schema:

```python
# Generic schema — no job-assistant assumptions
DatabaseQueryTool(table_schema={
    "users":    {"columns": "id, email, created_at", "hint": "customer accounts"},
    "orders":   {"columns": "id, user_id, total, status", "hint": "purchase orders"},
})
```

The default (job-assistant) schema is `calculations / resumes / applications`.
Override the description's schema by passing `table_schema=`; the AST safety
validation is identical regardless of schema.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- A [DeepSeek API key](https://platform.deepseek.com/)
- A CockroachDB instance (Serverless or Dedicated) — optional for non-DB tools
- Gmail account (for email sending) — optional

### Setup
```bash
# 1. Create virtual env & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure your .env
cp .env.example .env
# Edit .env with your DeepSeek API key and CockroachDB URL

# 3. Run the agent CLI
python agent.py
```

### Configuration (`.env`)
```env
DEEPSEEK_API_KEY=«redacted:sk-…»
COCKROACHDB_URL=postgresql://user:***@host:26257/defaultdb?sslmode=verify-full
LLM_MODEL=deepseek/deepseek-v4-flash   # Change to any LiteLLM-supported model

# Email (optional)
SMTP_EMAIL=your-email@gmail.com
SMTP_APP_PASSWORD=your-app-password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Resume (optional)
RESUME_PDF_PATH=/path/to/your/resume.pdf
```

---

## 🏗️ Architecture

```
c-db/
├── agent.py                 # CLI entry point (builds Agent + CLIRunner)
├── agent/
│   └── builder.py           # AgentBuilder + Agent facade (fluent config)
├── container/
│   └── services.py          # RuntimeServices container (wires all subsystems)
├── core/                    # Framework-agnostic kernel
│   ├── interfaces/          # Planner/Executor/LLM/Memory/Scheduler abstractions
│   ├── events/              # EventBus + typed domain/system events
│   ├── models/             # Pydantic models (context, plan, tool, result, …)
│   ├── errors/             # Custom exceptions
│   └── export/             # Plan exporter
├── runtime/                 # Concrete implementations
│   ├── engine/             # RuntimeEngine — LLM turn-loop + parallel tool exec
│   ├── planning/           # DirectPlanner (keyword → plan + single_pass hint)
│   ├── scheduler/          # DAGScheduler (concurrent plan execution)
│   ├── execution/          # ToolExecutor (signature-aware dispatch)
│   ├── memory/             # QdrantMemoryService + extractor
│   ├── llm/                # LiteLLMProvider
│   ├── middleware/         # Deduplication / Logging / Timing
│   ├── recording/          # Run recorder + replay
│   └── state/              # Immutable state store / reducer
├── tools/                   # Plugin tools (auto-discovered)
│   ├── base.py             # BaseTool abstract class
│   ├── registry.py         # Auto-discovery engine
│   ├── calculator.py  db_tool.py  web_search.py  weather.py
│   └── email/              # Resume + email tools
├── infrastructure/          # External services (db_pool, schema_manager)
├── subscribers/             # Event subscribers (console, structlog)
├── ui/cli/runner.py         # CLI adapter
├── config/                  # pydantic-settings configuration
├── docs/architecture/       # ADRs (0001–0006)
└── tests/                   # Pytest suite (143+ tests)
```

### How a request flows
```
user prompt
   → RuntimeEngine.run()
       → MemoryRetrieved (if memory hits)
       → DirectPlanner.create_plan()        → PlanCreated
       → DAGScheduler.execute_plan()        (when plan has resolved args)
       → LLM turn-loop (otherwise):         generate_response → tool_calls
           → asyncio.gather(_execute_single_tool)  → ToolDeduplicationMiddleware
           → loop until no tool_calls
   → RunResult(final_output, turn_count, metadata)
```

### Plugin architecture 🚀
Add a new tool — no changes to existing code:
```python
# tools/my_tool.py
from tools.base import BaseTool

class MyTool(BaseTool):
    def get_name(self): return "my_tool"
    def get_description(self): return "Does awesome stuff"
    def get_parameters(self): return {"type": "object", "properties": {}}
    def execute(self, db_conn=None, **kwargs): return {"success": True}

my_tool = MyTool()  # Auto-discovered ✓
```

---

## 🔒 Safety
The database tool blocks destructive SQL via AST parsing:

| Allowed | Blocked |
|---------|---------|
| `SELECT` | `DROP TABLE` |
| `INSERT` | `TRUNCATE` |
| `CREATE TABLE` | `DELETE FROM` |
| `ALTER TABLE ADD` | `UPDATE` |

---

## 🧪 Testing

Run the suite **inside the virtualenv** (deps are not installed system-wide):

```bash
source .venv/bin/activate
python -m pytest          # runs everything, including the smoke test
python -m pytest tests/   # run just the tests/ directory
```

A lightweight `tests/refactoring_smoke.py` checks that the kernel imports and the
registry auto-discovers tools — it requires **no network, DB, or API key**.

> **Note:** `test_refactoring.py` at the repo root is a thin compatibility shim
> that re-exports the smoke checks. Running `pytest` from the root no longer
> crashes collection (it used to `sys.exit(1)` at import — fixed).

---

## 📄 License
MIT

---

**Built with ❤️ by [Ritesh Chavan](https://github.com/ritz541)**
