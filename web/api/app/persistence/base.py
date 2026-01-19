"""
Water Treatment Controller - Database Base Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Database connection and session management using SQLAlchemy.

This module provides a unified database layer that works with both
SQLite (development) and PostgreSQL (production) via SQLAlchemy ORM.
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models.base import Base, SessionLocal, engine

logger = logging.getLogger(__name__)


def _migrate_audit_log_table_schema():
    """
    Migrate audit_log table schema for existing deployments.

    Historical issue: The audit_log table had different column names:
    - 'time' instead of 'timestamp'
    - 'user_id' instead of 'user'
    - 'resource' instead of 'resource_type'/'resource_id'
    - Missing 'id' column

    Per CLAUDE.md: "docker compose up should start a fully working system" -
    this enables self-healing for existing deployments.
    """
    try:
        with engine.connect() as conn:
            dialect = engine.dialect.name
            if dialect != "postgresql":
                return  # Only needed for PostgreSQL (Docker setup)

            # Check if audit_log table exists with old schema ('time' column)
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'audit_log' AND column_name = 'time'"
            ))
            if result.fetchone():
                # Old schema detected - need to recreate table
                logger.info("Detected old audit_log schema, recreating table...")

                # Drop the old table (CASCADE to remove hypertable metadata)
                conn.execute(text("DROP TABLE IF EXISTS audit_log CASCADE"))
                conn.commit()

                # Recreate with correct schema
                conn.execute(text("""
                    CREATE TABLE audit_log (
                        id SERIAL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        "user" VARCHAR(64),
                        action VARCHAR(32) NOT NULL,
                        resource_type VARCHAR(32),
                        resource_id VARCHAR(64),
                        details TEXT,
                        ip_address VARCHAR(45)
                    )
                """))
                conn.commit()

                # Convert to hypertable
                conn.execute(text(
                    "SELECT create_hypertable('audit_log', 'timestamp', "
                    "if_not_exists => TRUE)"
                ))
                conn.commit()

                # Create indexes
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_log_id "
                    "ON audit_log (id)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_log_user "
                    "ON audit_log (\"user\")"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_log_action "
                    "ON audit_log (action)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_log_resource "
                    "ON audit_log (resource_type, resource_id)"
                ))
                conn.commit()

                # Add retention policy
                conn.execute(text(
                    "SELECT add_retention_policy('audit_log', "
                    "INTERVAL '365 days', if_not_exists => TRUE)"
                ))
                conn.commit()

                logger.info("Migrated audit_log table to new schema")

    except Exception as e:
        # Non-fatal: if migration fails, log but continue
        logger.warning(f"Audit log table migration: {e}")


def _migrate_users_table_schema():
    """
    Migrate users table schema for existing deployments.

    Historical issue: The users table had 'enabled' column but SQLAlchemy model
    expects 'active', 'sync_to_rtus', and 'updated_at' columns.

    Per CLAUDE.md: "docker compose up should start a fully working system" -
    this enables self-healing for existing deployments.
    """
    try:
        with engine.connect() as conn:
            dialect = engine.dialect.name
            if dialect != "postgresql":
                return  # Only needed for PostgreSQL (Docker setup)

            # Check if users table exists
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'users'"
            ))
            if not result.fetchone():
                return  # Table doesn't exist yet, init.sql will create it

            # Check if we need to rename 'enabled' to 'active'
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'enabled'"
            ))
            if result.fetchone():
                conn.execute(text(
                    "ALTER TABLE users RENAME COLUMN enabled TO active"
                ))
                conn.commit()
                logger.info("Migrated users.enabled -> users.active")

            # Add sync_to_rtus column if missing
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'sync_to_rtus'"
            ))
            if not result.fetchone():
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN sync_to_rtus BOOLEAN "
                    "NOT NULL DEFAULT TRUE"
                ))
                conn.commit()
                logger.info("Added users.sync_to_rtus column")

            # Add updated_at column if missing
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'updated_at'"
            ))
            if not result.fetchone():
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN updated_at TIMESTAMPTZ "
                    "NOT NULL DEFAULT NOW()"
                ))
                conn.commit()
                logger.info("Added users.updated_at column")

    except Exception as e:
        # Non-fatal: if migration fails, log but continue
        logger.warning(f"Users table migration: {e}")


def _cleanup_duplicate_indexes():
    """
    Remove duplicate indexes that may have been created by older code.

    Historical issue: Some Column definitions had both index=True AND explicit
    Index() in __table_args__, causing duplicate index creation attempts on restart.
    This function drops any auto-generated indexes that conflict with explicit ones.

    Per CLAUDE.md: "docker compose up should start a fully working system" -
    this enables self-healing for existing deployments.
    """
    # Map of auto-generated index names to their explicit replacements
    # Format: auto_index_name -> (table, explicit_index_name)
    duplicate_indexes = [
        # AlarmEvent: had index=True on rtu_station + explicit ix_alarm_events_rtu_station
        ("ix_alarm_events_rtu_station", "alarm_events"),
        # ScheduledMaintenance: had index=True on rtu_station + explicit ix_scheduled_maintenance_rtu
        ("ix_scheduled_maintenance_rtu", "scheduled_maintenance"),
    ]

    try:
        with engine.connect() as conn:
            # Check if we're on PostgreSQL (has pg_indexes) or SQLite
            dialect = engine.dialect.name

            for index_name, table_name in duplicate_indexes:
                try:
                    if dialect == "postgresql":
                        # PostgreSQL: Check if index exists before dropping
                        result = conn.execute(text(
                            "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
                        ), {"idx": index_name})
                        if result.fetchone():
                            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                            conn.commit()
                            logger.info(f"Cleaned up duplicate index: {index_name}")
                    else:
                        # SQLite: DROP INDEX IF EXISTS is safe
                        conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                        conn.commit()
                except Exception as e:
                    # Non-fatal: index might not exist or already be correct
                    logger.debug(f"Index cleanup for {index_name}: {e}")

    except Exception as e:
        # Non-fatal: if cleanup fails, create_all will handle it
        logger.debug(f"Index cleanup skipped: {e}")

# Database path (for backward compatibility with env var)
DB_PATH = os.environ.get('WTC_DB_PATH', '/var/lib/water-controller/wtc.db')


class _DatabaseState:
    """
    Encapsulated database initialization state.
    Avoids module-level mutable global per Section 1.6.
    """
    __slots__ = ('_initialized',)

    def __init__(self) -> None:
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def mark_initialized(self) -> None:
        self._initialized = True


_db_state = _DatabaseState()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions in persistence layer.

    Use this for standalone scripts and persistence functions:
        with get_db_context() as db:
            db.query(...)

    For FastAPI dependency injection, use models.base.get_db instead:
        db: Session = Depends(get_db)

    Yields a SQLAlchemy session that works with both SQLite and PostgreSQL.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Short alias for persistence layer (all persistence modules use this)
get_db = get_db_context


def init_database():
    """
    Initialize the database schema using SQLAlchemy.

    Creates all tables defined in the models if they don't exist.
    Works with both SQLite (development) and PostgreSQL (production).

    Includes self-healing for historical schema issues.
    """
    # Migrate audit_log table schema for existing deployments
    # This enables self-healing per CLAUDE.md
    _migrate_audit_log_table_schema()

    # Migrate users table schema for existing deployments
    # This enables self-healing per CLAUDE.md
    _migrate_users_table_schema()

    # Clean up any duplicate indexes from older code versions
    # This enables self-healing for existing deployments per CLAUDE.md
    _cleanup_duplicate_indexes()

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized via SQLAlchemy")

    # Initialize singleton config records
    _init_singleton_configs()


def _init_singleton_configs():
    """Initialize singleton configuration records (id=1) if they don't exist."""
    from ..models.config import ADConfig, LogForwardingConfig, ModbusServerConfig

    with get_db() as db:
        # ModbusServerConfig
        if not db.query(ModbusServerConfig).filter(ModbusServerConfig.id == 1).first():
            db.add(ModbusServerConfig(id=1))

        # LogForwardingConfig
        if not db.query(LogForwardingConfig).filter(LogForwardingConfig.id == 1).first():
            db.add(LogForwardingConfig(id=1))

        # ADConfig
        if not db.query(ADConfig).filter(ADConfig.id == 1).first():
            db.add(ADConfig(id=1))

        db.commit()
        logger.debug("Singleton configuration records initialized")


def initialize() -> bool:
    """
    Explicitly initialize the database.
    Call this from application startup, not at import time.
    """
    if _db_state.initialized:
        return True

    try:
        init_database()
        _db_state.mark_initialized()
        logger.info("Database initialized successfully")
        return True
    except SQLAlchemyError as e:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.critical(
            f"Database initialization failed: {e}. "
            "Application cannot persist data. "
            "Check database path permissions and disk space, then restart."
        )
        return False
    except OSError as e:
        # File system errors (permissions, disk full, etc.)
        logger.critical(
            f"Database file system error: {e}. "
            "Cannot access database file. "
            "Check permissions and available disk space."
        )
        return False


def is_initialized() -> bool:
    """Check if database has been initialized"""
    return _db_state.initialized
