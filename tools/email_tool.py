"""
Email Tool — Resume storage, cover letter drafting, and sending

Sub-tools:
  1. store_resume(text, name?)     — Save your resume to DB
  2. list_resumes()                 — See stored resumes
  3. draft_application(...)         — Generate tailored email using DeepSeek
  4. list_applications(status?)     — View drafted/sent applications
  5. send_email(app_id)             — Send a drafted application via SMTP
"""

import os
import json
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


# RESUME

def store_resume(text: str, db_conn, name: str = "default") -> dict:
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
        msg = f"Resume '{name}' saved."
        if pdf_path:
            msg += f" PDF at: {pdf_path}"
        return {"success": True, "message": msg, "name": name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_resumes(db_conn) -> dict:
    """List all stored resumes."""
    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT name, created_at FROM resumes ORDER BY created_at DESC")
            rows = cur.fetchall()
            resumes = [{"name": r[0], "created_at": str(r[1])} for r in rows]
            return {
                "success": True,
                "resumes": resumes,
                "count": len(resumes),
                "message": f"Found {len(resumes)} resume(s)." if resumes else "No resumes stored yet.",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

# APPLICATIONS (DRAFT + LIST)

def _call_llm(prompt: str) -> str:
    """Helper: call DeepSeek via LiteLLM and return the response text."""
    import litellm
    model = os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    resp = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_key=api_key,
    )
    return resp.choices[0].message.content.strip()


def draft_application(
    company: str,
    role_title: str,
    recipient_email: str,
    job_description: str,
    db_conn,
) -> dict:
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

Write a professional, tailored email body (plain text, no markdown) that:
1. References specific skills from the resume that match the job description
2. Shows enthusiasm for the role and company
3. Is concise — 3-4 short paragraphs max
4. Includes a polite closing with name and links (GitHub: github.com/ritz541, Portfolio: chavanpatil.com)

Only output the email body itself — no subject line, no greetings wrapper.
Start directly with "Dear Hiring Manager," or similar."""

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


def list_applications(db_conn, status: str = None) -> dict:
    """List applications, optionally filtered by status (draft/sent)."""
    try:
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
            return {
                "success": True,
                "applications": apps,
                "count": len(apps),
                "message": f"Found {len(apps)} application(s)." if apps else "No applications yet.",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

# SEND EMAIL

def send_email(application_id: int, db_conn) -> dict:
    """
    Send a drafted application email via Gmail SMTP, with PDF resume attached.
    Fetches the draft from applications table, sends it, updates status to 'sent'.
    """
    try:
        # Fetch the draft
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT company, role_title, recipient_email, tailored_body, status
                FROM applications WHERE id = %s
            """, (application_id,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"No application found with ID {application_id}."}
            company, role, recipient, body, status = row
            if status == "sent":
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

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())

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
        return {"success": False, "error": str(e)}
