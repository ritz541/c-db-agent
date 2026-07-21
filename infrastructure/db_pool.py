"""
Database Connection Pool Module

Handles PostgreSQL/CockroachDB connection pooling.
Uses psycopg2's SimpleConnectionPool for efficiency.
"""

import os
import psycopg2
from psycopg2 import pool
import structlog

from config import get_settings


logger = structlog.get_logger()

# Global connection pool
_db_pool = None


def init_db_pool(db_url: str):
    """
    Initialize the database connection pool.
    
    Args:
        db_url: CockroachDB/PostgreSQL connection URL
    """
    global _db_pool
    
    try:
        _db_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=db_url,
        )
        logger.info("db.pool_created")
    except Exception as e:
        logger.error("db.pool_creation_failed", error=str(e))
        raise


def get_connection():
    """
    Get a connection from the pool.
    
    Returns:
        psycopg2.extensions.connection: A database connection
    
    Raises:
        RuntimeError: If pool is not initialized
    """
    if _db_pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
    
    return _db_pool.getconn()


def return_connection(conn):
    """
    Return a connection to the pool.
    
    Args:
        conn: Connection to return
    """
    if _db_pool is not None:
        _db_pool.putconn(conn)


def close_pool():
    """Close all connections in the pool."""
    global _db_pool
    
    if _db_pool is not None:
        _db_pool.closeall()
        _db_pool = None
        logger.info("db.pool_closed")


def auto_load_resume(pdf_path: str, conn):
    """
    Auto-load resume from PDF if path is configured.
    
    Args:
        pdf_path: Path to PDF file
        conn: Database connection
    """
    if not pdf_path or not os.path.isfile(pdf_path):
        logger.info("resume.pdf_not_found")
        return
    
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
            
    except Exception as e:
        logger.warning("resume.load_failed", error=str(e))
