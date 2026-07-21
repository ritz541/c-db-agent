"""
Draft Application Tool — Generate tailored cover letter using DeepSeek
"""

import structlog
from . import _call_llm
from ..base import BaseTool

logger = structlog.get_logger()


class DraftApplicationTool(BaseTool):
    """Generate a tailored cover letter email for a job application."""

    def get_name(self) -> str:
        return "draft_application"

    def get_description(self) -> str:
        return (
            "Generate a tailored cover letter email for a job application. "
            "Reads your stored resume + the job description, writes a professional email, "
            "and saves it as a draft. You can then send it with send_email()."
        )

    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Company name"
                },
                "role_title": {
                    "type": "string",
                    "description": "Job title you're applying for"
                },
                "recipient_email": {
                    "type": "string",
                    "description": "HR/hiring manager email address"
                },
                "job_description": {
                    "type": "string",
                    "description": "The full job description text"
                }
            },
            "required": ["company", "role_title", "recipient_email", "job_description"]
        }

    def execute(self, db_conn, company: str, role_title: str,
                recipient_email: str, job_description: str) -> dict:
        """Generate a tailored cover-letter email using DeepSeek."""
        try:
            with db_conn.cursor() as cur:
                cur.execute("SELECT content FROM resumes ORDER BY created_at DESC LIMIT 1")
                row = cur.fetchone()
                if not row:
                    return {
                        "success": False,
                        "error": "No resume found. Store one first using store_resume().",
                    }
                resume_text = row[0]

            prompt = f"""You are writing a job application email on behalf of Ritesh Chavan.

Resume:
{resume_text}

Job Role: {role_title}
Company: {company}
Job Description:
{job_description}

Write a SHORT email body (plain text, no markdown) that:
1. Mentions 1-2 specific skills from the resume that match the job
2. Sounds like a real person wrote it (not a template)
3. Is 2-3 short paragraphs max
4. Ends with: "Best regards, Ritesh Chavan" and links (GitHub: github.com/ritz541, Portfolio: chavanpatil.com)

Output only the email body. Start with "Dear Hiring Manager," or similar."""

            email_body = _call_llm(prompt)

            with db_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS applications (
                        id SERIAL PRIMARY KEY,
                        company TEXT NOT NULL,
                        role_title TEXT NOT NULL,
                        recipient_email TEXT NOT NULL,
                        job_description TEXT,
                        tailored_body TEXT NOT NULL,
                        status TEXT DEFAULT 'draft',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    INSERT INTO applications (company, role_title, recipient_email, job_description, tailored_body)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                """, (company, role_title, recipient_email, job_description, email_body))
                app_id = cur.fetchone()[0]
            db_conn.commit()

            return {
                "success": True,
                "application_id": app_id,
                "company": company,
                "role": role_title,
                "recipient": recipient_email,
                "tailored_body": email_body,
                "status": "draft",
                "message": f"Draft created for {role_title} at {company} (ID: {app_id}). Send it with send_email({app_id}).",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


draft_application_tool = DraftApplicationTool()