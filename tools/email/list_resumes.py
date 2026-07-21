"""
List Resumes Tool — See stored resumes
"""

import structlog
from ..base import BaseTool

logger = structlog.get_logger()


class ListResumesTool(BaseTool):
    """List all stored resumes."""

    def get_name(self) -> str:
        return "list_resumes"

    def get_description(self) -> str:
        return "List all stored resumes and when they were saved."

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {}
        }

    def execute(self, db_conn) -> dict:
        """List all stored resumes."""
        try:
            with db_conn.cursor() as cur:
                cur.execute("SELECT name, created_at FROM resumes ORDER BY created_at DESC")
                rows = cur.fetchall()
                resumes = [{"name": r[0], "created_at": str(r[1])} for r in rows]
                logger.info("resume.listed", count=len(resumes))
                return {
                    "success": True,
                    "resumes": resumes,
                    "count": len(resumes),
                    "message": f"Found {len(resumes)} resume(s)." if resumes else "No resumes stored yet.",
                }
        except Exception as e:
            logger.error("resume.list_failed", error=str(e))
            return {"success": False, "error": str(e)}


list_resumes_tool = ListResumesTool()