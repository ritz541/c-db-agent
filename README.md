# 🤖 c-db Agent

A simple Python AI agent that uses **LiteLLM** to call **DeepSeek** with two tools — a **calculator** (with DB storage) and a **CockroachDB query tool** (natural language → SQL).

## ✨ Features

| Tool | Description |
|------|-------------|
| **🔢 Calculator** | Evaluate math expressions (`15 * 37`, `sqrt(144) + 8`). Results are automatically stored in a `calculations` table in CockroachDB. |
| **🗄️ CockroachDB Query** | Ask questions in plain English — the agent generates SQL, runs it, and returns the results. Safety filters block destructive operations like `DROP` / `TRUNCATE` / `DELETE`. |

### Example Conversations

```
You: What's 187 * 42?
  → 187 * 42 = 7,854 (saved to DB)

You: Show me my calculation history
  → Queries the calculations table and returns all rows

You: What tables do I have?
  → Lists all tables in your CockroachDB instance

You: What's the average result of all calculations?
  → Generates: SELECT AVG(CAST(result AS numeric)) FROM calculations
```

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A [DeepSeek API key](https://platform.deepseek.com/)
- A CockroachDB instance (Serverless or Dedicated)

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
```

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

## 🔒 Safety

The database tool blocks destructive SQL:

| Allowed | Blocked |
|---------|---------|
| `SELECT` | `DROP TABLE` |
| `INSERT` | `TRUNCATE` |
| `CREATE TABLE` | `DELETE FROM` |
| `ALTER TABLE ADD` | `UPDATE` |

## 📁 Project Structure

```
c-db-agent/
├── agent.py            # Main agent loop (LiteLLM + DeepSeek)
├── tools/
│   ├── calculator.py   # Math evaluator + DB storage
│   └── db_tool.py      # SQL executor with safety checks
├── .env.example        # Configuration template
└── requirements.txt    # Python dependencies
```

## 📄 License

MIT
