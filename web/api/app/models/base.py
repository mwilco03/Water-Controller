"""
Water Treatment Controller - Database Base Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy base and session management.
"""

import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from ..core.ports import get_database_url

# Database configuration - single source of truth in core/ports.py
DATABASE_URL = get_database_url()

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


class DictSerializableMixin:
    """
    Mixin that provides to_dict() method for SQLAlchemy models.

    Consolidates the *_to_dict() pattern used throughout the codebase.
    Models can override _serialize_field() or to_dict() for custom behavior.

    Usage:
        class MyModel(Base, DictSerializableMixin):
            __tablename__ = "my_table"
            ...

        # Then use:
        model.to_dict()  # Returns all columns
        model.to_dict(exclude=["password"])  # Exclude sensitive fields
        model.to_dict(include=["id", "name"])  # Only specific fields
    """

    def _serialize_field(self, key: str, value: Any) -> Any:
        """
        Serialize a single field value. Override for custom serialization.

        Args:
            key: Column name
            value: Column value

        Returns:
            Serialized value (JSON-compatible)
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def to_dict(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Convert model to dictionary.

        Args:
            include: If provided, only include these columns
            exclude: If provided, exclude these columns

        Returns:
            Dictionary representation of model
        """
        exclude = exclude or []
        result = {}

        # Get column names from SQLAlchemy mapper
        mapper = inspect(self.__class__)
        columns = [c.key for c in mapper.columns]

        for key in columns:
            if include and key not in include:
                continue
            if key in exclude:
                continue

            value = getattr(self, key, None)
            result[key] = self._serialize_field(key, value)

        return result


# Declarative base with mixin
Base = declarative_base(cls=DictSerializableMixin)


def get_db() -> Generator[Session, None, None]:
    """Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)
