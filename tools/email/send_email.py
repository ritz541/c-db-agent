"""
Send Email Tool — Send drafted application via Gmail SMTP
"""

import os
import structlog
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from ..base import BaseTool

logger = structlog.get_logger()


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
        """Send a drafted application email via Gmail SMTP, with PDF resume attached."""
        try:
            logger.info("email.sending", app_id=application_id)
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

                cur.execute("SELECT pdf_path FROM resumes ORDER BY created_at DESC LIMIT 1")
                resume_row = cur.fetchone()
                pdf_path = resume_row[0] if resume_row else ""

            subject = f"Application for {role} at {company} - Ritesh Chavan"
            msg = MIMEMultipart("mixed")
            msg["From"] = os.getenv("SMTP_EMAIL")
            msg["To"] = recipient
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain"))

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


send_email_tool = SendEmailTool()