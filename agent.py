#!/usr/bin/env python3
"""
AI Agent with Plugin-Based Tool System

This agent uses LiteLLM to call DeepSeek with tools that can be
dynamically discovered and loaded.

Architecture:
- Tools are in tools/ directory, each extending BaseTool
- ToolRegistry auto-discovers all tools (no manual registration)
- Adding a new tool = create a file, zero changes to existing code

Run: python agent.py
"""

import os
import sys
import json
import uuid
import tenacity

# ── Load Environment Variables ───────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Import configuration
from config import get_settings

# Import observability (will be refactored later, but keeping for now)
import sentry_sdk
import structlog

# Import infrastructure
from infrastructure.db_pool import init_db_pool, get_connection, return_connection, close_pool

# Import tool registry (auto-discovery magic happens here)
from tools.registry import registry

# Import core modules
from core.llm_client import LLMClient
from core.chat_session import ChatSession
from core.prompts import get_system_prompt


def init_observability(settings):
    """Initialize Sentry and structlog."""
    sentry_sdk.init(
        dsn=settings.sentry_dsn or "https://placeholder@oXXX.ingest.sentry.io/XXX",
        send_default_pii=True,
        traces_sample_rate=1.0,
        environment="development",
    )
    sentry_sdk.set_tag("agent.name", "c-db-agent")
    sentry_sdk.set_tag("agent.version", "2.0")
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer(),
        ]
    )
    
    return structlog.get_logger()


def main():
    """Main entry point - orchestrates all components."""
    
    # Load settings
    try:
        settings = get_settings()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize observability
    logger = init_observability(settings)
    logger.info("agent.starting")
    
    # Initialize database connection pool
    try:
        init_db_pool(settings.cockroachdb_url)
        logger.info("db.pool_created")
        
        # Auto-load resume from PDF if path is set in .env
        pdf_path = os.getenv("RESUME_PDF_PATH", "")
        if pdf_path and os.path.isfile(pdf_path):
            conn = get_connection()
            try:
                from tools.email_tool import load_resume_from_pdf_tool
                result = load_resume_from_pdf_tool.execute(
                    db_conn=conn,
                    pdf_path=pdf_path
                )
                if result["success"]:
                    logger.info("resume.loaded", path=pdf_path)
                else:
                    logger.warning("resume.load_skipped", error=result.get("error"))
            finally:
                return_connection(conn)
        else:
            logger.info("resume.pdf_not_found")
            
    except Exception as e:
        logger.error("db.pool_creation_failed", error=str(e))
        print(f"Failed to create database connection pool: {e}")
        sys.exit(1)
    
    # Auto-discover and register all tools (THE MAGIC!)
    registry.auto_discover()
    logger.info("tools.loaded", count=len(registry.list_tools()))
    
    # Create LLM client
    llm_client = LLMClient(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key
    )
    
    # Create and run chat session
    session = ChatSession(
        llm_client=llm_client,
        tool_registry=registry,
        system_prompt=get_system_prompt()
    )
    
    try:
        session.run()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        close_pool()
        logger.info("agent.shutdown")


if __name__ == "__main__":
    main()
