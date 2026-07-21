"""
List Applications Tool — View drafted/sent applications
"""

import structlog
from ..base import BaseTool

logger = structlog.get_logger()


class ListApplicationsTool(BaseTool):
    """List job applications, optionally filtered by status."""

    def get_name(self) -> str:
        return "list_applications"

    def get_description(self) -> str:
        return "List your job applications, optionally filtered by status ('draft' or 'sent')."

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'draft' or 'sent'. Omit to see all."
                }
            }
        }

    def execute(self, db_conn, status: str = None) -> dict:
        """List applications, optionally filtered by status (draft/sent)."""
        try:
            logger.info("application.listing", status=status)
            with db_conn.cursor() as cur:
                if status:
                    cur.execute("""
                        SELECT id, company, role_title, recipient_email, status, created_at
                        FROM applications WHERE status = %s ORDER BY created_at DESC
                    """, (status,))
                else:
                    cur.execute("""
                        SELECT id, company, role_title, recipient_email, status, created_at
                        FROM applications ORDER BY created_at DESC
                    """)
                rows = cur.fetchall()
                apps = [
                    {"id": r[0], "company": r[1], "role": r[2],
                     "recipient": r[3], "status": r[4], "created_at": str(r[5])}
                    for r in rows
                ]
                logger.info("application.listed", count=len(apps))
                return {
                    "success": True,
                    "applications": apps,
                    "count": len(apps),
                    "message": f"Found {len(apps)} application(s)." if apps else "No applications yet.",
                }
        except Exception as e:
            logger.error("application.list_failed", error=str(e))
            return {"success": False, "error": str(e)}


list_applications_tool = ListApplicationsTool()