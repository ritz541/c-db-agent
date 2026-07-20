"""
Email Tool — Resume storage, cover letter drafting, and sending

Sub-tools:
  1. StoreResumeTool - Save your resume to DB
  2. ListResumesTool - See stored resumes
  3. LoadResumeFromPdfTool - Read PDF and store as resume
  4. DraftApplicationTool - Generate tailored email using DeepSeek
  5. ListApplicationsTool - View drafted/sent applications
  6. SendEmailTool - Send a drafted application via SMTP
"""

import os
import json
import smtplib
import ssl
import structlog
import tenacity
import sentry_sdk
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# PDF text extraction
from pypdf import PdfReader
from .base import BaseTool


logger = structlog.get_logger()


# ── HELPER: LLM CALL FOR EMAIL DRAFTING ─────────────────────────────

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
    before_sleep=lambda rs: logger.warning("email_llm.retry", attempt=rs.attempt_number),
)
def _call_llm(prompt: str) -> str:
    """Helper: call DeepSeek via LiteLLM and return the response text."""
    import litellm
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    with sentry_sdk.start_span(op="llm", description="email_tool._call_llm"):
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            timeout=30,  # Don't hang forever
        )
    return resp.choices[0].message.content.strip()


# ── TOOL 1: STORE RESUME ────────────────────────────────────────────

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
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    INSERT INTO resumes (name, content, pdf_path)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET content = EXCLUDED.content, pdf_path = EXCLUDED.pdf_path;
                """, (name, text, pdf_path))
            db_conn.commit()
            logger.info("resume.stored", name=name, pdf_path=pdf_path)
            msg = f"Resume '{name}' saved."
            if pdf_path:
                msg += f" PDF at: {pdf_path}"
            return {"success": True, "message": msg, "name": name}
        except Exception as e:
            logger.error("resume.store_failed", name=name, error=str(e))
            return {"success": False, "error": str(e)}


# ── TOOL 2: LIST RESUMES ───────────────────────────────────────────

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


# ── TOOL 3: LOAD RESUME FROM PDF ───────────────────────────────────

class LoadResumeFromPdfTool(BaseTool):
    """Read a PDF file from disk, extract its text, and store it in the database."""
    
    def get_name(self) -> str:
        return "load_resume_from_pdf"
    
    def get_description(self) -> str:
        return (
            "Read a PDF file from disk, extract its text, and store it in the database "
            "as your resume. Use this when you have a new or updated resume PDF."
        )
    
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Full path to the PDF file, e.g. '/home/ritz/Downloads/resume.pdf'"
                },
                "name": {
                    "type": "string",
                    "description": "Optional label for this resume (default: 'default')"
                }
            },
            "required": ["pdf_path"]
        }
    
    def execute(self, db_conn, pdf_path: str, name: str = "default") -> dict:
        """
        Read a PDF file from disk, extract its text, and store it in the DB.
        
        Use this when you have a new/updated resume PDF you want to load.
        """
        try:
            # Check the file exists
            if not os.path.isfile(pdf_path):
                logger.error("resume.pdf_not_found", path=pdf_path)
                return {"success": False, "error": f"File not found: {pdf_path}"}

            # Extract text from PDF
            logger.info("resume.pdf_extracting", path=pdf_path)
            reader = PdfReader(pdf_path)
            text_parts = []
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
            full_text = "\n".join(text_parts)

            if not full_text.strip():
                logger.warning("resume.pdf_no_text", path=pdf_path)
                return {"success": False, "error": "No text could be extracted from the PDF."}

            # Store in DB using the existing function
            store_tool = StoreResumeTool()
            result = store_tool.execute(db_conn=db_conn, text=full_text, name=name)
            if result["success"]:
                logger.info("resume.pdf_loaded", path=pdf_path, name=name)
                result["message"] = f"Resume loaded from {pdf_path} and stored as '{name}'."
                result["text_length"] = len(full_text)
            return result

        except Exception as e:
            logger.error("resume.pdf_failed", path=pdf_path, error=str(e))
            return {"success": False, "error": str(e)}


# ── TOOL 4: DRAFT APPLICATION ──────────────────────────────────────

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
            # Fetch the resume from DB
            with db_conn.cursor() as cur:
                cur.execute("SELECT content FROM resumes ORDER BY created_at DESC LIMIT 1")
                row = cur.fetchone()
                if not row:
                    return {
                        "success": False,
                        "error": "No resume found. Store one first using store_resume().",
                    }
                resume_text = row[0]

            # Generate the email via DeepSeek
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

            # Save to applications table
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


# ── TOOL 5: LIST APPLICATIONS ──────────────────────────────────────

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


# ── TOOL 6: SEND EMAIL ─────────────────────────────────────────────

class SendEmailTool(BaseTool):
    """Send a drafted application email via Gmail SMTP."""
    
    def get_name(self) -> str:
        return "send_email"
    
    def get_description(self) -> str:
        return (
            "Send a drafted application email. Provide the application ID from "
            "draft_application(). The email will be sent via SMTP with your PDF "
            "resume attached."
        )
    
    def get_parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "number",
                    "description": "The ID of the drafted application to send (returned by draft_application)"
                }
            },
            "required": ["application_id"]
        }
    
    def execute(self, db_conn, application_id: int) -> dict:
        """
        Send a drafted application email via Gmail SMTP, with PDF resume attached.
        Fetches the draft from applications table, sends it, updates status to 'sent'.
        """
        try:
            logger.info("email.sending", app_id=application_id)
            # Fetch the draft
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT company, role_title, recipient_email, tailored_body, status
                    FROM applications WHERE id = %s
                """, (application_id,))
                row = cur.fetchone()
                if not row:
                    logger.error("email.send_failed", app_id=application_id, reason="not_found")
                    return {"success": False, "error": f"No application found with ID {application_id}."}
                company, role, recipient, body, status = row
                if status == "sent":
                    logger.error("email.send_failed", app_id=application_id, reason="already_sent")
                    return {"success": False, "error": f"Application {application_id} already sent."}

                # Fetch the PDF path from latest resume
                cur.execute("SELECT pdf_path FROM resumes ORDER BY created_at DESC LIMIT 1")
                resume_row = cur.fetchone()
                pdf_path = resume_row[0] if resume_row else ""

            # Build the email with attachment
            subject = f"Application for {role} at {company} - Ritesh Chavan"
            msg = MIMEMultipart("mixed")  # mixed allows attachments
            msg["From"] = os.getenv("SMTP_EMAIL")
            msg["To"] = recipient
            msg["Subject"] = subject

            # Attach the cover letter body
            msg.attach(MIMEText(body, "plain"))

            # Attach the PDF resume if the file exists
            if pdf_path and os.path.isfile(pdf_path):
                logger.info("email.attaching_pdf", path=pdf_path)
                with open(pdf_path, "rb") as f:
                    attachment = MIMEBase("application", "pdf")
                    attachment.set_payload(f.read())
                    encoders.encode_base64(attachment)
                    attachment.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename="Ritesh_Chavan_Resume.pdf",
                    )
                    msg.attach(attachment)

            # Send via SMTP
            smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", 587))
            smtp_user = os.getenv("SMTP_EMAIL")
            smtp_pass = os.getenv("SMTP_APP_PASSWORD")

            logger.info("email.connecting_smtp", server=smtp_server)
            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, recipient, msg.as_string())
            logger.info("email.sent", app_id=application_id, to=recipient)

            # Mark as sent
            with db_conn.cursor() as cur:
                cur.execute("UPDATE applications SET status = 'sent' WHERE id = %s", (application_id,))
            db_conn.commit()

            attached = ""
            if pdf_path and os.path.isfile(pdf_path):
                attached = " (with PDF resume attached)"

            return {
                "success": True,
                "application_id": application_id,
                "to": recipient,
                "subject": subject,
                "message": f"Email sent to {recipient} regarding {role} at {company}!{attached}",
            }

        except Exception as e:
            logger.error("email.send_failed", app_id=application_id, error=str(e))
            return {"success": False, "error": str(e)}


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


# ── EXPORT SINGLETON INSTANCES ─────────────────────────────────────

store_resume_tool = StoreResumeTool()
list_resumes_tool = ListResumesTool()
load_resume_from_pdf_tool = LoadResumeFromPdfTool()
draft_application_tool = DraftApplicationTool()
list_applications_tool = ListApplicationsTool()
send_email_tool = SendEmailTool()
delete_draft_tool = DeleteDraftTool()
