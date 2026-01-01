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

from sqlalchemy.orm import Session

from ..models.base import Base, SessionLocal, engine

logger = logging.getLogger(__name__)

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
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Yields a SQLAlchemy session that works with both SQLite and PostgreSQL.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """
    Initialize the database schema using SQLAlchemy.

    Creates all tables defined in the models if they don't exist.
    Works with both SQLite (development) and PostgreSQL (production).
    """
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
    except Exception as e:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.critical(
            f"Database initialization failed: {e}. "
            "Application cannot persist data. "
            "Check database path permissions and disk space, then restart."
        )
        return False


def is_initialized() -> bool:
    """Check if database has been initialized"""
    return _db_state.initialized
