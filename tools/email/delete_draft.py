"""
Delete Draft Tool — Delete a draft application
"""

import structlog
from ..base import BaseTool

logger = structlog.get_logger()


class DeleteDraftTool(BaseTool):
    """Delete a draft application by ID. Only works on drafts, not sent applications."""

    def get_name(self) -> str:
        return "delete_application"

    def get_description(self) -> str:
        return "Delete a draft application by ID. Only works on applications with status 'draft'. Sent applications cannot be deleted."

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "number",
                    "description": "The ID of the draft application to delete"
                }
            },
            "required": ["application_id"]
        }

    def execute(self, db_conn, application_id: int) -> dict:
        """Delete a draft application."""
        try:
            logger.info("application.deleting", app_id=application_id)
            with db_conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM applications WHERE id = %s",
                    (application_id,)
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "error": f"No application found with ID {application_id}."}
                if row[0] == "sent":
                    return {"success": False, "error": f"Cannot delete application {application_id}: already sent."}
                cur.execute(
                    "DELETE FROM applications WHERE id = %s AND status = 'draft'",
                    (application_id,)
                )
            db_conn.commit()
            logger.info("application.deleted", app_id=application_id)
            return {"success": True, "message": f"Draft application {application_id} deleted."}
        except Exception as e:
            logger.error("application.delete_failed", app_id=application_id, error=str(e))
            return {"success": False, "error": str(e)}


delete_draft_tool = DeleteDraftTool()