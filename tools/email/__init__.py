"""
Shared utilities for email tools.
"""

import os
import structlog
import tenacity
import sentry_sdk

# PDF text extraction
from pypdf import PdfReader

logger = structlog.get_logger()


def register_schema():
    """Register the email tools' schema with the schema manager."""
    from infrastructure.schema_manager import schema_manager, Migration
    
    # Resumes table
    resumes_migration = Migration(
        version="001",
        description="Create resumes table",
        up_sql="""
            CREATE TABLE IF NOT EXISTS resumes (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                pdf_path TEXT DEFAULT '',
                pdf_mtime TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """,
        down_sql="DROP TABLE IF EXISTS resumes;"
    )
    
    # Add pdf_mtime column if missing (schema drift fix)
    add_pdf_mtime_migration = Migration(
        version="001a",
        description="Add pdf_mtime column to existing resumes table",
        up_sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'resumes' AND column_name = 'pdf_mtime'
                ) THEN
                    ALTER TABLE resumes ADD COLUMN pdf_mtime TIMESTAMP;
                END IF;
            END $$;
        """,
        down_sql="ALTER TABLE resumes DROP COLUMN IF EXISTS pdf_mtime;"
    )
    
    # Applications table
    applications_migration = Migration(
        version="002",
        description="Create applications table",
        up_sql="""
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
        """,
        down_sql="DROP TABLE IF EXISTS applications;"
    )
    
    schema_manager.register_migration("email", resumes_migration)
    schema_manager.register_migration("email", add_pdf_mtime_migration)
    schema_manager.register_migration("email", applications_migration)


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
    with sentry_sdk.start_span(op="llm", description="email._call_llm"):
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            timeout=30,
        )
    return resp.choices[0].message.content.strip()