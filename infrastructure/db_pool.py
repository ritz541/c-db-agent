"""
Database Connection Pool Module

Handles PostgreSQL/CockroachDB connection pooling with graceful degradation.
Uses psycopg2's SimpleConnectionPool for efficiency.
"""

import os
import psycopg2
from psycopg2 import pool
import structlog
import threading
import time

from config import get_settings


logger = structlog.get_logger()

# Global connection pool
_db_pool = None
_db_available = True  # Flag for graceful degradation
_db_lock = threading.Lock()


def init_db_pool(db_url: str, minconn: int = 1, maxconn: int = 5, max_retries: int = 3, retry_delay: float = 2.0):
    """
    Initialize the database connection pool with retry logic.
    
    Args:
        db_url: CockroachDB/PostgreSQL connection URL
        minconn: Minimum number of connections in pool
        maxconn: Maximum number of connections in pool
        max_retries: Maximum number of connection attempts
        retry_delay: Delay between retries in seconds
    """
    global _db_pool, _db_available
    
    for attempt in range(max_retries):
        try:
            with _db_lock:
                _db_pool = pool.SimpleConnectionPool(
                    minconn=minconn,
                    maxconn=maxconn,
                    dsn=db_url,
                )
                _db_available = True
                logger.info("db.pool_created", minconn=minconn, maxconn=maxconn)
                return
        except Exception as e:
            logger.error(
                "db.pool_creation_failed",
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e)
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                logger.warning("db.pool_unavailable", error="Max retries exceeded")
                _db_available = False
                _db_pool = None
                # Don't raise - allow agent to run in degraded mode


def get_connection():
    """
    Get a connection from the pool with graceful degradation.
    
    Returns:
        psycopg2.extensions.connection: A database connection
    
    Raises:
        RuntimeError: If pool is not initialized and database is required
    """
    global _db_available
    
    if _db_pool is None:
        if _db_available:
            raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
        else:
            logger.warning("db.connection_requested_unavailable")
            raise RuntimeError("Database is currently unavailable. Running in degraded mode.")
    
    try:
        return _db_pool.getconn()
    except Exception as e:
        logger.error("db.connection_failed", error=str(e))
        # Mark database as unavailable if we can't get connections
        with _db_lock:
            _db_available = False
        raise RuntimeError(f"Failed to get database connection: {e}")


def return_connection(conn):
    """
    Return a connection to the pool with error handling.
    
    Args:
        conn: Connection to return
    """
    global _db_available
    
    if _db_pool is not None:
        try:
            _db_pool.putconn(conn)
        except Exception as e:
            logger.error("db.return_connection_failed", error=str(e))
            # If returning fails, the connection might be bad
            # Don't mark as unavailable yet, but log the error


def close_pool():
    """Close all connections in the pool."""
    global _db_pool, _db_available
    
    if _db_pool is not None:
        try:
            _db_pool.closeall()
            logger.info("db.pool_closed")
        except Exception as e:
            logger.error("db.pool_close_failed", error=str(e))
        finally:
            _db_pool = None
            _db_available = False


def is_db_available() -> bool:
    """
    Check if the database is currently available.
    
    Returns:
        bool: True if database is available, False otherwise
    """
    return _db_available and _db_pool is not None


def test_connection() -> bool:
    """
    Test database connectivity by attempting a simple query.
    
    Returns:
        bool: True if connection test succeeds, False otherwise
    """
    global _db_available
    
    if _db_pool is None:
        return False
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        finally:
            return_connection(conn)
    except Exception as e:
        logger.error("db.connection_test_failed", error=str(e))
        with _db_lock:
            _db_available = False
        return False


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
