"""
Store Resume Tool — Save your resume to DB
"""

import os
import datetime
import structlog
from ..base import BaseTool

logger = structlog.get_logger()


class StoreResumeTool(BaseTool):
    """Store a resume in the database."""

    def get_name(self) -> str:
        return "store_resume"

    def get_description(self) -> str:
        return "Store your resume text in the database for later use in job applications."

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Full text of your resume"
                },
                "name": {
                    "type": "string",
                    "description": "Optional label for this resume (e.g. 'default')"
                }
            },
            "required": ["text"]
        }

    def execute(self, db_conn, text: str, name: str = "default") -> dict:
        """Store a resume in the database. Also saves the PDF path from .env."""
        try:
            pdf_path = os.getenv("RESUME_PDF_PATH", "")
            with db_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS resumes (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        content TEXT NOT NULL,
                        pdf_path TEXT DEFAULT '',
                        pdf_mtime TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Check if we have an existing resume with the same PDF path and mtime
                pdf_mtime = None
                if pdf_path and os.path.isfile(pdf_path):
                    pdf_mtime = datetime.datetime.fromtimestamp(
                        os.path.getmtime(pdf_path), tz=datetime.timezone.utc
                    )
                    cur.execute(
                        "SELECT pdf_mtime FROM resumes WHERE pdf_path = %s AND name = %s",
                        (pdf_path, name)
                    )
                    existing = cur.fetchone()
                    if existing and existing[0]:
                        stored_mtime = existing[0]
                        # Handle timezone-naive datetime from DB
                        if hasattr(stored_mtime, 'tzinfo') and not stored_mtime.tzinfo:
                            stored_mtime = stored_mtime.replace(tzinfo=datetime.timezone.utc)
                        # Only skip if PDF hasn't been modified
                        if not pdf_mtime or (stored_mtime and pdf_mtime <= stored_mtime):
                            logger.info("resume.up_to_date", name=name, pdf_path=pdf_path)
                            return {"success": True, "message": f"Resume '{name}' is already up-to-date.", "name": name}
                
                cur.execute("""
                    INSERT INTO resumes (name, content, pdf_path, pdf_mtime)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE 
                        SET content = EXCLUDED.content, 
                            pdf_path = EXCLUDED.pdf_path,
                            pdf_mtime = EXCLUDED.pdf_mtime;
                """, (name, text, pdf_path, pdf_mtime))
            db_conn.commit()
            logger.info("resume.stored", name=name, pdf_path=pdf_path)
            msg = f"Resume '{name}' saved."
            if pdf_path:
                msg += f" PDF at: {pdf_path}"
            return {"success": True, "message": msg, "name": name}
        except Exception as e:
            logger.error("resume.store_failed", name=name, error=str(e))
            return {"success": False, "error": str(e)}


store_resume_tool = StoreResumeTool()