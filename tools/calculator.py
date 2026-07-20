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
import structlog
from .base import BaseTool


logger = structlog.get_logger()


class CalculatorTool(BaseTool):
    """
    Tool for evaluating math expressions and storing results in DB.
    """
    
    def get_name(self) -> str:
        return "calculate"
    
    def get_description(self) -> str:
        return (
            "Evaluate a math expression and stores the expression + result "
            "in the database. Supports: +, -, *, /, **, sqrt(), sin(), "
            "cos(), log(), etc."
        )
    
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression to evaluate, e.g. '15 * 37' or 'sqrt(144) + 8'"
                }
            },
            "required": ["expression"]
        }
    
    def execute(self, db_conn, expression: str) -> dict:
        """
        Evaluate a math expression and store it in the database.
        
        Args:
            db_conn: Connection to CockroachDB
            expression: A math expression like "15 * 37" or "sqrt(144) + 8 * 2"
        
        Returns:
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
            logger.info("calculate.attempting", expression=expression)
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            logger.info("calculate.success", expression=expression, result=str(result))

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
            logger.info("calculate.stored_in_db", expression=expression)

            return {
                "success": True,
                "expression": expression,
                "result": str(result),
                "stored_in_db": True,
                "message": f"{expression} = {result} (saved to DB)"
            }

        except Exception as e:
            # If anything goes wrong, return a helpful error
            logger.error("calculate.failed", expression=expression, error=str(e))
            return {
                "success": False,
                "expression": expression,
                "result": None,
                "stored_in_db": False,
                "error": str(e),
                "message": f"Could not evaluate '{expression}': {e}"
            }


# Export singleton instance for easy import
calculator_tool = CalculatorTool()
