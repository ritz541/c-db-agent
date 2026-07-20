"""
🔢 Calculator Tool

This tool:
1. Takes a math expression (e.g. "15 * 37", "sqrt(144) + 8")
2. Evaluates it safely using Python's math module
3. Stores the expression + result in a "calculations" table in CockroachDB
4. Returns the result

Why store in DB?
  - You can later ask: "Show me my calculation history"
  - You can analyze: "What's the average result?"
  - Persistence across sessions!
"""

import math
import traceback


def calculate(expression: str, db_conn) -> dict:
    """
    Evaluate a math expression and store it in the database.

    Parameters
    ----------
    expression : str
        A math expression like "15 * 37" or "sqrt(144) + 8 * 2"
    db_conn : psycopg2 connection
        Connection to CockroachDB used to store the result

    Returns
    -------
    dict with keys: "success", "result", "expression", "stored_in_db"
    """
    try:
        # ── 1. RESTRICTED EVALUATION ────────────────────────────────
        # We use eval() with a VERY restricted namespace.
        # Only "math" functions are available — no file I/O, no system calls.
        # This is safe for math expressions only.
        allowed_names = {
            # Math constants
            "pi": math.pi,
            "e": math.e,
            # Basic math functions
            "sqrt": math.sqrt,
            "abs": abs,
            "round": round,
            "pow": pow,
            # Trigonometry
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            # Logarithmic / exponential
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            # Others
            "floor": math.floor,
            "ceil": math.ceil,
            "factorial": math.factorial,
            "degrees": math.degrees,
            "radians": math.radians,
        }

        # Evaluate the expression in the restricted namespace
        # __builtins__ is set to {} to prevent dangerous Python builtins
        result = eval(expression, {"__builtins__": {}}, allowed_names)

        # ── 2. STORE IN DATABASE ────────────────────────────────────
        # Create the table if it doesn't exist
        with db_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calculations (
                    id SERIAL PRIMARY KEY,
                    expression TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Insert this calculation into the table
            cur.execute(
                "INSERT INTO calculations (expression, result) VALUES (%s, %s)",
                (expression, str(result)),
            )
        # Commit the transaction so the data is saved
        db_conn.commit()

        return {
            "success": True,
            "expression": expression,
            "result": str(result),
            "stored_in_db": True,
            "message": f"{expression} = {result} (saved to DB)"
        }

    except Exception as e:
        # If anything goes wrong, return a helpful error
        return {
            "success": False,
            "expression": expression,
            "result": None,
            "stored_in_db": False,
            "error": str(e),
            "message": f"Could not evaluate '{expression}': {e}"
        }
