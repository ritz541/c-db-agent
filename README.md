# 🤖 c-db Agent

A plugin-based AI agent built with **LiteLLM** and **DeepSeek**, featuring auto-discovery of tools. Just drop a Python file in `tools/` and it's automatically available to the agent!

## ✨ Features

### Current Tools

| Tool | Description |
|------|-------------|
| **🔢 Calculator** | Evaluate math expressions (`15 * 37`, `sqrt(144) + 8`). Results stored in CockroachDB. |
| **🗄️ Database Query** | Natural language → SQL. Safety filters block destructive operations. |
| **📄 Resume Tools** | Store, list, and load resumes from PDF. |
| **✉️ Email Tools** | Draft tailored cover letters and send via SMTP. |
| **🌤️ Weather** | Demo plugin (auto-discovered!). |

### Plugin Architecture 🚀

**Add a new tool in 30 seconds:**

```python
# tools/my_tool.py
from tools.base import BaseTool

class MyTool(BaseTool):
    def get_name(self): return "my_tool"
    def get_description(self): return "Does awesome stuff"
    def get_parameters(self): return {...}
    def execute(self, db_conn, **kwargs): return {"success": True}

my_tool = MyTool()  # That's it! Auto-discovered ✓
```

**Zero changes to existing code!**

---

## 💬 Example Conversations

```
You: What's 187 * 42?
  → 187 * 42 = 7,854 (saved to DB)

You: Show me my calculation history
  → Queries the calculations table and returns all rows

You: What tables do I have?
  → Lists all tables in your CockroachDB instance

You: Draft an application for Software Engineer at Acme
  → Generates tailored cover letter using your resume
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A [DeepSeek API key](https://platform.deepseek.com/)
- A CockroachDB instance (Serverless or Dedicated)
- Gmail account (for email sending)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/ritz541/c-db-agent.git
cd c-db-agent

# 2. Create virtual env & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure your .env
cp .env.example .env
# Edit .env with your DeepSeek API key and CockroachDB URL

# 4. Run the agent
python agent.py
```

### Configuration

Edit `.env` to set your credentials:

```env
DEEPSEEK_API_KEY=sk-your-key-here
COCKROACHDB_URL=postgresql://user:password@host:26257/defaultdb?sslmode=verify-full
LLM_MODEL=deepseek/deepseek-v4-flash   # Change to any LiteLLM-supported model

# Email (optional, for send_email tool)
SMTP_EMAIL=your-email@gmail.com
SMTP_APP_PASSWORD=your-app-password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Resume (optional, for auto-loading)
RESUME_PDF_PATH=/path/to/your/resume.pdf
```

---

## 🏗️ Architecture

### Plugin-Based Design

```
c-db/
├── agent.py                 # 138 lines - Thin orchestrator
├── config.py                # Configuration management
├── tools/                  # TOOLS (Plugin-style!)
│   ├── __init__.py        # Auto-discovery setup
│   ├── base.py            # BaseTool abstract class
│   ├── registry.py        # Auto-discovery engine
│   ├── calculator.py      # Math tool
│   ├── db_tool.py         # Database tool
│   ├── email_tool.py      # Email tools (6 tools in 1 file!)
│   └── weather.py         # Demo plugin (auto-discovered!)
├── core/                   # Agent logic
│   ├── llm_client.py     # LLM API wrapper
│   ├── chat_session.py    # Chat loop
│   └── prompts.py        # System prompt (optimized!)
└── infrastructure/         # External services
    └── db_pool.py        # Database connection pool
```

### How Auto-Discovery Works

1. **Startup**: `registry.auto_discover()` scans `tools/` directory
2. **Find**: All classes inheriting from `BaseTool`
3. **Register**: Automatically added to available tools
4. **Use**: LLM can call them immediately

**No manual registration needed!**

---

## 🧠 How It Works

```
You type → agent.py → LiteLLM → DeepSeek API
                           ↓
                    Needs a tool call?
                           ↓
                   ┌──────┴──────┐
                   ↓              ↓
            calculator.py    db_tool.py
            (eval + DB)     (SQL executor)
                   ↓              ↓
              Result sent back to DeepSeek
                           ↓
                   Final answer printed
```

### Tech Stack

- **[LiteLLM](https://litellm.ai)** — Unified API for 200+ LLM providers
- **[psycopg2](https://www.psycopg.org/)** — PostgreSQL driver (CockroachDB wire-compatible)
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** — Environment variable management
- **[structlog](https://www.structlog.org/)** — Structured logging
- **[Sentry](https://sentry.io/)** — Error tracking and performance monitoring

---

## 🔒 Safety

The database tool blocks destructive SQL:

| Allowed | Blocked |
|---------|---------|
| `SELECT` | `DROP TABLE` |
| `INSERT` | `TRUNCATE` |
| `CREATE TABLE` | `DELETE FROM` |
| `ALTER TABLE ADD` | `UPDATE` |

---

## 📊 Optimization

### System Prompt
- **Before refactoring**: ~375 tokens (bloated with tool list)
- **After refactoring**: ~97 tokens (minimal + efficient)
- **Savings**: 278 tokens per API call (~$0.0006/call on DeepSeek)

**Why?** Tool schemas are sent separately in the API call (`tools` parameter). No need to repeat in the prompt!

---

## 🧪 Testing

```bash
# Run the test suite
source .venv/bin/activate
python test_refactoring.py
```

**Output:**
```
Test 1: Checking imports...
  ✓ All imports successful

Test 2: Checking tool auto-discovery...
  ✓ Discovered 9 tools
  ✓ All expected tools found

...

All tests passed! ✓
```

---

## 🚀 Adding a New Tool

### Step 1: Create the Tool File

```python
# tools/calendar_tool.py
from tools.base import BaseTool
import structlog

logger = structlog.get_logger()

class CalendarTool(BaseTool):
    def get_name(self):
        return "get_calendar_events"
    
    def get_description(self):
        return "Get upcoming calendar events"
    
    def get_parameters(self):
        return {
            "type": "object",
            "properties": {
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days to look ahead"
                }
            },
            "required": ["days_ahead"]
        }
    
    def execute(self, db_conn, days_ahead: int):
        # Your logic here
        return {
            "success": True,
            "events": [...]
        }

calendar_tool = CalendarTool()
```

### Step 2: That's It! ✨

```bash
# Restart the agent
python agent.py

# The tool is automatically:
#   - Discovered
#   - Registered
#   - Available to the LLM
```

---

## 📁 Project Structure

```
c-db-agent/
├── agent.py            # Main orchestrator (138 lines)
├── config.py           # Configuration with validation
├── tools/             # Plugin directory (auto-discovered)
│   ├── base.py       # Base class for all tools
│   ├── registry.py   # Auto-discovery engine
│   ├── calculator.py # Math evaluation tool
│   ├── db_tool.py    # SQL query tool
│   ├── email_tool.py # Email tools (6 tools)
│   └── weather.py    # Demo plugin
├── core/              # Agent logic
│   ├── llm_client.py
│   ├── chat_session.py
│   └── prompts.py
├── infrastructure/     # External services
│   └── db_pool.py
├── tests/             # Unit tests
├── .env.example       # Configuration template
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

---

## 🤝 Contributing

1. Fork the repo
2. Create a tool: `tools/my_tool.py`
3. Test it: `python test_refactoring.py`
4. Submit a PR

**No need to modify `agent.py` or `registry.py`!**

---

## 📄 License

MIT

---

## 🎯 Roadmap

- [ ] Add unit tests for all tools
- [ ] Add web UI (FastAPI + React)
- [ ] Add more built-in tools (calendar, file manager, etc.)
- [ ] Support for tool dependencies
- [ ] Tool versioning

---

**Built with ❤️ by [Ritesh Chavan](https://github.com/ritz541)**
