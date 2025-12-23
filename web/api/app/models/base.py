"""
Water Treatment Controller - Database Base Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy base and session management.
"""

import os
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Database configuration
DB_PATH = os.environ.get("WTC_DB_PATH", "/var/lib/water-controller/wtc.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Create engine
# For SQLite, use check_same_thread=False for async compatibility
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.environ.get("WTC_DB_ECHO", "false").lower() == "true",
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)
