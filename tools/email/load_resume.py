"""
Load Resume From PDF Tool — Extract text from PDF and store as resume
"""

import os
import structlog
from . import PdfReader
from .store_resume import StoreResumeTool
from ..base import BaseTool

logger = structlog.get_logger()


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
        """Read a PDF file from disk, extract its text, and store it in the DB."""
        try:
            if not os.path.isfile(pdf_path):
                logger.error("resume.pdf_not_found", path=pdf_path)
                return {"success": False, "error": f"File not found: {pdf_path}"}

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


load_resume_from_pdf_tool = LoadResumeFromPdfTool()