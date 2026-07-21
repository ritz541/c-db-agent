"""
🗄️ CockroachDB Query Tool

Executes SQL queries against CockroachDB with safety validation.
Supports SELECT, INSERT, CREATE, and ALTER operations while blocking destructive commands.
"""

import traceback
import datetime
from decimal import Decimal
import structlog
import sqlglot
from .base import BaseTool


logger = structlog.get_logger()


# Default table schema for the job-application assistant use case.
# Override via DatabaseQueryTool(table_schema=...) to make the tool generic.
DEFAULT_TABLE_SCHEMA: dict[str, dict] = {
    "calculations": {
        "columns": "id, expression, result, created_at",
        "hint": "math expression results",
    },
    "resumes": {
        "columns": "id, name, created_at",
        "hint": "stored resumes",
    },
    "applications": {
        "columns": "id, company, role_title, status, created_at",
        "hint": "job applications",
    },
}


def _format_schema(table_schema: dict[str, dict]) -> str:
    """Render a table schema dict into a compact human/LLM-readable string."""
    if not table_schema:
        return (
            "No fixed schema is hard-coded; inspect the database directly "
            "(e.g. SELECT table_name FROM information_schema.tables) before querying."
        )
    parts = []
    for table, meta in table_schema.items():
        cols = meta.get("columns", "")
        hint = meta.get("hint")
        entry = f"'{table}': ({cols})"
        if hint:
            entry += f" — {hint}"
        parts.append(entry)
    return "\n".join(f"{i + 1}) {p}" for i, p in enumerate(parts))


def _serialize_value(value):
    """
    Convert database values to JSON-safe types.
    
    datetime, date, time → ISO string
    Decimal → float or string
    bytes → string (decoded)
    Everything else → as-is (int, float, str, None, bool)
    """
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return float(value)
    elif isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    elif isinstance(value, set):
        return list(value)
    return value


def is_safe_query(sql: str) -> bool:
    """
    Check if the SQL query is safe to execute using AST parsing.
    
    We parse the SQL and whitelist allowed statement types. This catches
    both explicit and obfuscated destructive operations.
    
    Args:
        sql: The SQL query to validate
        
    Returns:
        bool: True if the query is safe to execute
    """
    try:
        # Parse SQL into AST - this normalizes/obfuscates attacks automatically
        # Use postgres dialect since CockroachDB is wire-compatible
        parsed = sqlglot.parse_one(sql, read="postgres")
        
        # Get the statement type (e.g., "Select", "Insert", "Drop")
        # sqlglot uses CamelCase class names
        stmt_type = type(parsed).__name__
        
        # Check for destructive operations
        if stmt_type in ("Drop", "Truncate", "Delete"):
            logger.warning("db.query_blocked", sql=sql[:100], reason=f"destructive: {stmt_type}")
            return False
        
        # For ALTER statements, only allow TABLE with ADD actions (no DROP)
        if stmt_type == "Alter":
            # Check if it's ALTER TABLE (not ALTER DATABASE, etc.)
            kind = getattr(parsed, "kind", None)
            if kind and str(kind).upper() != "TABLE":
                logger.warning("db.query_blocked", sql=sql[:100], reason=f"alter not table: {kind}")
                return False
            # Check if it contains DROP actions
            sql_upper = sql.upper()
            if "DROP" in sql_upper:
                logger.warning("db.query_blocked", sql=sql[:100], reason="alter contains DROP")
                return False
        
        # Whitelist allowed statements (CamelCase matches sqlglot class names)
        ALLOWED = {"Select", "Insert", "Create", "CreateTable", "CreateIndex", "CreateView", "Alter"}
        if stmt_type not in ALLOWED:
            logger.warning("db.query_blocked", sql=sql[:100], reason=f"not allowed: {stmt_type}")
            return False
            
        return True
        
    except Exception as e:
        # Parse errors mean the SQL is malformed or obfuscated maliciously
        logger.warning("db.query_parse_failed", sql=sql[:100], error=str(e))
        return False
class DatabaseQueryTool(BaseTool):
    """
    Tool for executing SQL queries against CockroachDB.

    The set of known tables is configurable via ``table_schema`` so the tool
    is not hard-wired to the job-application use case. It still performs the
    same AST-based safety validation regardless of schema.
    """

    def __init__(
        self,
        table_schema: dict[str, dict] | None = None,
        name: str = "query_database",
    ) -> None:
        # Allow pre-instantiated singletons (e.g. db_query_tool = DatabaseQueryTool())
        # to keep the default job-assistant schema, while letting callers override.
        self._table_schema = table_schema if table_schema is not None else dict(DEFAULT_TABLE_SCHEMA)
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_description(self) -> str:
        schema_text = _format_schema(self._table_schema)
        return (
            "Run a SQL query against the CockroachDB (PostgreSQL-compatible) database. "
            "Use this to fetch data, inspect records, or run calculations. "
            f"Known tables and columns:\n{schema_text}\n"
            "For tables not listed above, introspect the schema first "
            "(e.g. SELECT * FROM information_schema.tables) rather than guessing."
        )

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "The SQL query to execute. "
                        "Allowed: SELECT, INSERT, CREATE TABLE, CREATE INDEX, ALTER TABLE. "
                        "Blocked: DROP, TRUNCATE, DELETE, UPDATE."
                    )
                }
            },
            "required": ["sql"]
        }

    def execute(self, db_conn, sql: str) -> dict:
        """
        Execute a SQL query against CockroachDB and return the results.
        
        Args:
            db_conn: Connection to CockroachDB
            sql: The SQL query to run (generated by the LLM from your question)
        
        Returns:
            dict with keys: "success", "columns", "rows", "row_count", "message"
        """
        try:
            # ── 1. SAFETY CHECK ──────────────────────────────────────────
            if not is_safe_query(sql):
                logger.warning("db.query_blocked", sql=sql[:100])
                return {
                    "success": False,
                    "error": (
                        "BLOCKED: This query contains destructive operations "
                        "(DROP, TRUNCATE, DELETE, etc.). "
                        "Only SELECT, INSERT, and CREATE operations are allowed."
                    ),
                    "sql": sql,
                }

            # ── 2. EXECUTE THE QUERY ─────────────────────────────────────
            logger.info("db.query_executing", sql=sql[:100])
            with db_conn.cursor() as cur:
                cur.execute(sql)

                # If the query produced rows (e.g. SELECT), fetch them
                if cur.description:
                    # Get column names from the cursor description
                    columns = [desc[0] for desc in cur.description]
                    # Fetch all rows
                    rows = cur.fetchall()
                    row_count = len(rows)
                    logger.info("db.query_success", row_count=row_count, sql=sql[:100])

                    # Format the results nicely, serializing datetime/Decimal/etc.
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": [[_serialize_value(v) for v in row] for row in rows],
                        "row_count": row_count,
                        "message": (
                            f"Query returned {row_count} row(s)" 
                            if row_count > 0 
                            else "Query returned no rows"
                        ),
                        "sql": sql,
                    }
                else:
                    # No rows returned (e.g. INSERT, CREATE TABLE)
                    # Get the row count affected (if applicable)
                    row_count = cur.rowcount
                    db_conn.commit()
                    logger.info("db.query_success", row_count=row_count, sql=sql[:100])
                    return {
                        "success": True,
                        "columns": [],
                        "rows": [],
                        "row_count": row_count if row_count > 0 else 0,
                        "message": (
                            f"Query executed successfully. {row_count} row(s) affected."
                            if row_count and row_count > 0
                            else "Query executed successfully."
                        ),
                        "sql": sql,
                    }

        except Exception as e:
            # Catch and return SQL errors (wrong syntax, missing tables, etc.)
            logger.error("db.query_failed", sql=sql[:100], error=str(e))
            return {
                "success": False,
                "error": str(e),
                "sql": sql,
                "message": f"SQL error: {e}",
            }


# Export singleton instance for easy import
db_query_tool = DatabaseQueryTool()
