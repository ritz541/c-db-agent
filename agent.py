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
from infrastructure.schema_manager import schema_manager

# Import tool registry (auto-discovery magic happens here)
from tools.registry import registry

# Import core modules
from core.llm_client import LLMClient, RateLimiter
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
    
    # Validate settings
    from config import validate_settings
    is_valid, warnings = validate_settings(settings)
    
    if warnings:
        print("Configuration warnings:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
        print()
    
    if not is_valid:
        print("Critical configuration issues detected. Please fix them before running the agent.")
        sys.exit(1)
    
    # Initialize observability
    logger = init_observability(settings)
    logger.info("agent.starting")
    
    # Initialize database connection pool with graceful degradation
    init_db_pool(
        settings.cockroachdb_url,
        minconn=settings.db_pool_minconn,
        maxconn=settings.db_pool_maxconn,
        max_retries=settings.db_max_retries,
        retry_delay=settings.db_retry_delay
    )
    
    # Check if database is available
    from infrastructure.db_pool import is_db_available, test_connection
    if is_db_available():
        logger.info("db.available")
        # Test connection to verify it works
        if test_connection():
            logger.info("db.connection_test_passed")
        else:
            logger.warning("db.connection_test_failed")
    else:
        logger.warning("db.unavailable", message="Agent running in degraded mode without database")
        print("Warning: Database unavailable. Agent running in degraded mode.")
        print("Tools requiring database will not function properly.")
    
    # Auto-discover and register all tools (THE MAGIC!)
    registry.auto_discover()
    logger.info("tools.loaded", count=len(registry.list_tools()))
    
    # Register tool schemas and initialize database schema BEFORE resume auto-load
    from infrastructure.db_pool import is_db_available, get_connection, return_connection
    if is_db_available():
        try:
            # Register schemas from tools that have register_schema functions
            for tool_name in registry.list_tools():
                try:
                    tool_module = __import__(f"tools.{tool_name}", fromlist=[tool_name])
                    if hasattr(tool_module, 'register_schema'):
                        tool_module.register_schema()
                        logger.info("schema.registered", tool=tool_name)
                except ImportError:
                    pass  # Tool doesn't have register_schema, that's fine
                except Exception as e:
                    logger.warning("schema.registration_failed", tool=tool_name, error=str(e))
            
            # Also try to import calculator specifically since it might not load correctly
            try:
                import tools.calculator
                if hasattr(tools.calculator, 'register_schema'):
                    tools.calculator.register_schema()
                    logger.info("schema.registered", tool="calculator")
            except Exception as e:
                logger.warning("schema.calculator_registration_failed", error=str(e))
            
            # Also register schemas from subdirectories
            try:
                import tools.email
                if hasattr(tools.email, 'register_schema'):
                    tools.email.register_schema()
                    logger.info("schema.registered", tool="email")
            except Exception as e:
                logger.warning("schema.email_registration_failed", error=str(e))
            
            # Initialize schema in database
            conn = get_connection()
            try:
                # Reset email migrations if they exist with old schema to allow re-application
                try:
                    schema_manager.reset_migration(conn, "email_001")
                    schema_manager.reset_migration(conn, "email_001a")
                except Exception as e:
                    logger.debug("schema.email_reset_skipped", error=str(e))
                
                if schema_manager.initialize_schema(conn):
                    logger.info("schema.initialization_success")
                else:
                    logger.warning("schema.initialization_failed")
            finally:
                return_connection(conn)
        except Exception as e:
            logger.error("schema.setup_failed", error=str(e))
            print(f"Warning: Schema setup failed: {e}")
            print("Some tools may not function correctly.")
    
    # Auto-load resume from PDF if path is set in .env (after schema is initialized)
    if is_db_available():
        pdf_path = os.getenv("RESUME_PDF_PATH", "")
        if pdf_path and os.path.isfile(pdf_path):
            try:
                from infrastructure.db_pool import get_connection, return_connection
                conn = get_connection()
                try:
                    from tools.email.load_resume import load_resume_from_pdf_tool
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
            except Exception as e:
                logger.warning("resume.auto_load_failed", error=str(e))
        else:
            logger.info("resume.pdf_not_found")
    
    # Create LLM client
    rate_limiter = RateLimiter(max_requests_per_minute=settings.max_requests_per_minute)
    
    llm_client = LLMClient(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        rate_limiter=rate_limiter
    )
    
    # Create and run chat session
    session = ChatSession(
        llm_client=llm_client,
        tool_registry=registry,
        system_prompt=get_system_prompt(),
        max_tool_retries=settings.tool_max_retries
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
