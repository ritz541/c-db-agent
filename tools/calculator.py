"""
🔢 Calculator Tool

Evaluates math expressions and stores results in CockroachDB.
Supports basic arithmetic, trigonometry, logarithms, and more.
"""

import math
import traceback
import structlog
from .base import BaseTool


logger = structlog.get_logger()


def register_schema():
    """Register the calculator tool's schema with the schema manager."""
    from infrastructure.schema_manager import schema_manager
    
    create_sql = """
        CREATE TABLE IF NOT EXISTS calculations (
            id SERIAL PRIMARY KEY,
            expression TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    
    schema_manager.register_table("calculator", create_sql)


class CalculatorTool(BaseTool):
    """
    Tool for evaluating math expressions and storing results in DB.
    """
    def get_capabilities(self) -> set[str]:
        return {"math", "database"}

    
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
    
    def execute(self, db_conn=None, expression: str = "", context=None, **kwargs) -> dict:
        """
        Evaluate a math expression and store it in the database.
        
        Args:
            db_conn: Connection to CockroachDB
            expression: A math expression like "15 * 37" or "sqrt(144) + 8 * 2"
        
        Returns:
            dict with keys: "success", "result", "expression", "stored_in_db"
        """
        try:
            # Restricted evaluation with safe math functions only
            allowed_names = {
                "pi": math.pi, "e": math.e,
                "sqrt": math.sqrt, "abs": abs, "round": round, "pow": pow,
                "sin": math.sin, "cos": math.cos, "tan": math.tan,
                "asin": math.asin, "acos": math.acos, "atan": math.atan,
                "log": math.log, "log10": math.log10, "exp": math.exp,
                "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial,
                "degrees": math.degrees, "radians": math.radians,
            }

            logger.info("calculate.attempting", expression=expression)
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            logger.info("calculate.success", expression=expression, result=str(result))

            stored_in_db = False
            if db_conn:
                with db_conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS calculations (
                            id SERIAL PRIMARY KEY,
                            expression TEXT NOT NULL,
                            result TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                with db_conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO calculations (expression, result) VALUES (%s, %s)",
                        (expression, str(result)),
                    )
                db_conn.commit()
                stored_in_db = True
                logger.info("calculate.stored_in_db", expression=expression)

            return {
                "success": True,
                "expression": expression,
                "result": str(result),
                "stored_in_db": stored_in_db,
                "message": f"{expression} = {result}" + (" (saved to DB)" if stored_in_db else ""),
            }

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
