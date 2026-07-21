"""
Database Schema Manager

Handles database schema creation and migrations for tools.
Provides a centralized system for tools to define their required tables.
"""

import structlog
from typing import Dict, List, Callable, Optional
from datetime import datetime


logger = structlog.get_logger()


class Migration:
    """Represents a single database migration."""
    
    def __init__(self, version: str, description: str, up_sql: str, down_sql: str = ""):
        """
        Initialize a migration.
        
        Args:
            version: Migration version identifier (e.g., "001", "002")
            description: Human-readable description of what the migration does
            up_sql: SQL to execute for applying the migration
            down_sql: SQL to execute for rolling back the migration (optional)
        """
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql


class SchemaManager:
    """
    Manages database schema creation and migrations.
    
    Tools can register their required tables and migrations,
    and the SchemaManager ensures they exist in the database.
    """
    
    def __init__(self):
        """Initialize an empty schema manager."""
        self._migrations: Dict[str, Migration] = {}
        self._tool_tables: Dict[str, List[str]] = {}
        self._initialized = False
    
    def register_migration(self, tool_name: str, migration: Migration):
        """
        Register a migration for a tool.
        
        Args:
            tool_name: Name of the tool that owns this migration
            migration: Migration object to register
        """
        key = f"{tool_name}_{migration.version}"
        if key in self._migrations:
            logger.warning("schema.migration_overwrite", key=key)
        
        self._migrations[key] = migration
        
        if tool_name not in self._tool_tables:
            self._tool_tables[tool_name] = []
        self._tool_tables[tool_name].append(key)
        
        logger.info("schema.migration_registered", tool=tool_name, version=migration.version)
    
    def register_table(self, tool_name: str, create_sql: str):
        """
        Register a simple table creation for a tool.
        
        This is a convenience method for tools that just need to create a table
        without full migration support.
        
        Args:
            tool_name: Name of the tool that owns this table
            create_sql: SQL to create the table (CREATE TABLE IF NOT EXISTS ...)
        """
        # Create a migration from the table creation
        migration = Migration(
            version="001",
            description=f"Create table for {tool_name}",
            up_sql=create_sql,
            down_sql=""  # No rollback for simple table creation
        )
        self.register_migration(tool_name, migration)
    
    def get_tool_migrations(self, tool_name: str) -> List[Migration]:
        """
        Get all migrations for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            List of migrations for the tool
        """
        if tool_name not in self._tool_tables:
            return []
        
        keys = self._tool_tables[tool_name]
        return [self._migrations[key] for key in keys]
    
    def initialize_schema(self, db_conn) -> bool:
        """
        Initialize the schema by creating the migrations tracking table
        and applying all pending migrations.
        
        Args:
            db_conn: Database connection
            
        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        if self._initialized:
            logger.info("schema.already_initialized")
            return True
        
        try:
            # Create migrations tracking table
            self._create_migrations_table(db_conn)
            
            # Apply all pending migrations
            self._apply_pending_migrations(db_conn)
            
            self._initialized = True
            logger.info("schema.initialized")
            return True
            
        except Exception as e:
            logger.error("schema.initialization_failed", error=str(e))
            return False
    
    def _create_migrations_table(self, db_conn):
        """Create the table that tracks which migrations have been applied."""
        with db_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    migration_key VARCHAR(255) UNIQUE NOT NULL,
                    tool_name VARCHAR(100) NOT NULL,
                    version VARCHAR(50) NOT NULL,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        db_conn.commit()
        logger.info("schema.migrations_table_created")
    
    def _apply_pending_migrations(self, db_conn):
        """Apply all migrations that haven't been applied yet."""
        # Get applied migrations
        with db_conn.cursor() as cur:
            cur.execute("SELECT migration_key FROM schema_migrations")
            applied_keys = {row[0] for row in cur.fetchall()}
        
        # Apply pending migrations in order
        for key, migration in sorted(self._migrations.items()):
            if key not in applied_keys:
                try:
                    logger.info("schema.applying_migration", key=key, description=migration.description)
                    
                    with db_conn.cursor() as cur:
                        cur.execute(migration.up_sql)
                    
                    # Record the migration
                    tool_name = key.split('_')[0]
                    with db_conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO schema_migrations 
                            (migration_key, tool_name, version, description)
                            VALUES (%s, %s, %s, %s)
                        """, (key, tool_name, migration.version, migration.description))
                    
                    db_conn.commit()
                    logger.info("schema.migration_applied", key=key)
                    
                except Exception as e:
                    db_conn.rollback()
                    logger.error("schema.migration_failed", key=key, error=str(e))
                    raise
            else:
                # Verify that the migration was actually applied by checking if tables exist
                try:
                    # Extract table names from the migration SQL
                    import re
                    table_matches = re.findall(r'CREATE TABLE IF NOT EXISTS\s+(\w+)', migration.up_sql, re.IGNORECASE)
                    if table_matches:
                        with db_conn.cursor() as cur:
                            for table_name in table_matches:
                                cur.execute("""
                                    SELECT EXISTS (
                                        SELECT FROM information_schema.tables 
                                        WHERE table_name = %s
                                    )
                                """, (table_name.lower(),))
                                exists = cur.fetchone()[0]
                                if not exists:
                                    logger.warning(
                                        "schema.table_missing_reapplying",
                                        key=key,
                                        table=table_name
                                    )
                                    # Re-apply the migration
                                    logger.info("schema.reapplying_migration", key=key)
                                    with db_conn.cursor() as cur:
                                        cur.execute(migration.up_sql)
                                    db_conn.commit()
                                    logger.info("schema.migration_reapplied", key=key)
                except Exception as e:
                    logger.warning("schema.verification_failed", key=key, error=str(e))
    
    def get_applied_migrations(self, db_conn) -> List[Dict]:
        """
        Get list of applied migrations.
        
        Args:
            db_conn: Database connection
            
        Returns:
            List of applied migration information
        """
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT migration_key, tool_name, version, description, applied_at
                FROM schema_migrations
                ORDER BY applied_at
            """)
            
            return [
                {
                    "key": row[0],
                    "tool_name": row[1],
                    "version": row[2],
                    "description": row[3],
                    "applied_at": row[4].isoformat() if row[4] else None
                }
                for row in cur.fetchall()
            ]
    
    def rollback_migration(self, db_conn, migration_key: str) -> bool:
        """
        Rollback a specific migration.
        
        Args:
            db_conn: Database connection
            migration_key: Key of the migration to rollback
            
        Returns:
            bool: True if rollback succeeded, False otherwise
        """
        if migration_key not in self._migrations:
            logger.error("schema.rollback_unknown_migration", key=migration_key)
            return False
        
        migration = self._migrations[migration_key]
        
        if not migration.down_sql:
            logger.error("schema.rollback_no_down_sql", key=migration_key)
            return False
        
        try:
            logger.info("schema.rolling_back_migration", key=migration_key)
            
            with db_conn.cursor() as cur:
                cur.execute(migration.down_sql)
                cur.execute("DELETE FROM schema_migrations WHERE migration_key = %s", 
                           (migration_key,))
            
            db_conn.commit()
            logger.info("schema.migration_rolled_back", key=migration_key)
            return True
            
        except Exception as e:
            db_conn.rollback()
            logger.error("schema.rollback_failed", key=migration_key, error=str(e))
            return False
    
    def reset_migration(self, db_conn, migration_key: str) -> bool:
        """
        Remove a migration record from the tracking table.
        
        This is useful when migrations need to be reapplied due to schema changes.
        
        Args:
            db_conn: Database connection
            migration_key: Key of the migration to reset
            
        Returns:
            bool: True if reset succeeded, False otherwise
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute("DELETE FROM schema_migrations WHERE migration_key = %s", (migration_key,))
                deleted = cur.rowcount
            db_conn.commit()
            logger.info("schema.migration_reset", key=migration_key, deleted=deleted)
            return deleted > 0
        except Exception as e:
            db_conn.rollback()
            logger.error("schema.migration_reset_failed", key=migration_key, error=str(e))
            return False


# Global schema manager instance
schema_manager = SchemaManager()