"""
Tests for email tools (resume storage, drafting, sending, deletion).
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from tools.email_tool import (
    StoreResumeTool,
    ListResumesTool,
    LoadResumeFromPdfTool,
    DraftApplicationTool,
    ListApplicationsTool,
    SendEmailTool,
    DeleteDraftTool,
)


# ── StoreResumeTool ──────────────────────────────────────────────────


class TestStoreResume:
    @pytest.fixture
    def tool(self):
        return StoreResumeTool()

    def test_name(self, tool):
        assert tool.get_name() == "store_resume"

    def test_store_basic(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, text="My resume content")
        assert result["success"] is True
        assert result["name"] == "default"
        conn.commit.assert_called()

    def test_store_with_name(self, tool, mock_db):
        conn, cursor = mock_db
        result = tool.execute(db_conn=conn, text="My resume", name="v2")
        assert result["success"] is True
        assert result["name"] == "v2"

    def test_store_db_error(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.execute.side_effect = Exception("connection lost")
        result = tool.execute(db_conn=conn, text="My resume")
        assert result["success"] is False
        assert "error" in result


# ── ListResumesTool ──────────────────────────────────────────────────


class TestListResumes:
    @pytest.fixture
    def tool(self):
        return ListResumesTool()

    def test_name(self, tool):
        assert tool.get_name() == "list_resumes"

    def test_empty_list(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchall.return_value = []
        result = tool.execute(db_conn=conn)
        assert result["success"] is True
        assert result["count"] == 0
        assert "No resumes" in result["message"]

    def test_with_resumes(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchall.return_value = [
            ("default", "2026-07-21T10:00:00"),
            ("v2", "2026-07-20T09:00:00"),
        ]
        result = tool.execute(db_conn=conn)
        assert result["success"] is True
        assert result["count"] == 2
        assert result["resumes"][0]["name"] == "default"


# ── LoadResumeFromPdfTool ────────────────────────────────────────────


class TestLoadResumeFromPdf:
    @pytest.fixture
    def tool(self):
        return LoadResumeFromPdfTool()

    def test_name(self, tool):
        assert tool.get_name() == "load_resume_from_pdf"

    def test_file_not_found(self, tool, mock_db):
        conn, cursor = mock_db
        with patch("tools.email_tool.os.path.isfile", return_value=False):
            result = tool.execute(db_conn=conn, pdf_path="/nonexistent/resume.pdf")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_empty_pdf(self, tool, mock_db):
        conn, cursor = mock_db
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_reader.pages[0].extract_text.return_value = ""
        with (
            patch("tools.email_tool.os.path.isfile", return_value=True),
            patch("tools.email_tool.PdfReader", return_value=mock_reader),
        ):
            result = tool.execute(db_conn=conn, pdf_path="/fake/resume.pdf")
        assert result["success"] is False
        assert "no text" in result["error"].lower()

    def test_successful_pdf_load(self, tool, mock_db):
        conn, cursor = mock_db
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_reader.pages[0].extract_text.return_value = "Resume content here"
        with (
            patch("tools.email_tool.os.path.isfile", return_value=True),
            patch("tools.email_tool.PdfReader", return_value=mock_reader),
        ):
            result = tool.execute(db_conn=conn, pdf_path="/fake/resume.pdf")
        assert result["success"] is True
        assert result["text_length"] == len("Resume content here")


# ── DraftApplicationTool ────────────────────────────────────────────


class TestDraftApplication:
    @pytest.fixture
    def tool(self):
        return DraftApplicationTool()

    def test_name(self, tool):
        assert tool.get_name() == "draft_application"

    def test_no_resume_stored(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = None
        result = tool.execute(
            db_conn=conn, company="Acme", role_title="Dev",
            recipient_email="hr@acme.com", job_description="Build stuff"
        )
        assert result["success"] is False
        assert "No resume" in result["error"]

    def test_draft_success(self, tool, mock_db):
        conn, cursor = mock_db
        # First fetchone: resume content
        # Second fetchone: RETURNING id from INSERT
        cursor.fetchone.side_effect = [
            ("My resume text",),
            (1,),
        ]
        with patch("tools.email_tool._call_llm", return_value="Dear Hiring Manager,\nI am interested..."):
            result = tool.execute(
                db_conn=conn, company="Acme", role_title="Dev",
                recipient_email="hr@acme.com", job_description="Build stuff"
            )
        assert result["success"] is True
        assert result["company"] == "Acme"
        assert result["status"] == "draft"
        conn.commit.assert_called()


# ── ListApplicationsTool ────────────────────────────────────────────


class TestListApplications:
    @pytest.fixture
    def tool(self):
        return ListApplicationsTool()

    def test_name(self, tool):
        assert tool.get_name() == "list_applications"

    def test_empty_list(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchall.return_value = []
        result = tool.execute(db_conn=conn)
        assert result["success"] is True
        assert result["count"] == 0

    def test_with_applications(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchall.return_value = [
            (1, "Acme", "Dev", "hr@acme.com", "draft", "2026-07-21T10:00:00"),
        ]
        result = tool.execute(db_conn=conn)
        assert result["success"] is True
        assert result["count"] == 1
        assert result["applications"][0]["company"] == "Acme"

    def test_filter_by_status(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchall.return_value = []
        result = tool.execute(db_conn=conn, status="sent")
        assert result["success"] is True
        cursor.execute.assert_called()


# ── SendEmailTool ────────────────────────────────────────────────────


class TestSendEmail:
    @pytest.fixture
    def tool(self):
        return SendEmailTool()

    def test_name(self, tool):
        assert tool.get_name() == "send_email"

    def test_application_not_found(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = None
        result = tool.execute(db_conn=conn, application_id=999)
        assert result["success"] is False
        assert "No application found" in result["error"]

    def test_already_sent(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = (
            "Acme", "Dev", "hr@acme.com", "body", "sent"
        )
        result = tool.execute(db_conn=conn, application_id=1)
        assert result["success"] is False
        assert "already sent" in result["error"].lower()

    def test_send_success(self, tool, mock_db):
        conn, cursor = mock_db
        # First fetchone: the draft
        # Second fetchone: pdf_path
        cursor.fetchone.side_effect = [
            ("Acme", "Dev", "hr@acme.com", "Dear Hiring Manager...", "draft"),
            ("",),  # no pdf_path
        ]
        env = {
            "SMTP_EMAIL": "test@gmail.com",
            "SMTP_APP_PASSWORD": "app-pass",
            "SMTP_SERVER": "smtp.gmail.com",
            "SMTP_PORT": "587",
        }
        with (
            patch("tools.email_tool.smtplib.SMTP") as mock_smtp,
            patch("tools.email_tool.os.path.isfile", return_value=False),
            patch.dict(os.environ, env),
        ):
            result = tool.execute(db_conn=conn, application_id=1)
        assert result["success"] is True
        assert result["to"] == "hr@acme.com"
        conn.commit.assert_called()


# ── DeleteDraftTool ──────────────────────────────────────────────────


class TestDeleteDraft:
    @pytest.fixture
    def tool(self):
        return DeleteDraftTool()

    def test_name(self, tool):
        assert tool.get_name() == "delete_application"

    def test_not_found(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = None
        result = tool.execute(db_conn=conn, application_id=999)
        assert result["success"] is False
        assert "No application found" in result["error"]

    def test_cannot_delete_sent(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = ("sent",)
        result = tool.execute(db_conn=conn, application_id=1)
        assert result["success"] is False
        assert "already sent" in result["error"].lower()

    def test_delete_draft(self, tool, mock_db):
        conn, cursor = mock_db
        cursor.fetchone.return_value = ("draft",)
        result = tool.execute(db_conn=conn, application_id=1)
        assert result["success"] is True
        conn.commit.assert_called()
