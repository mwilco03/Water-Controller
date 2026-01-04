"""
Water Treatment Controller - Alembic Environment Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Configures Alembic migrations to use the application's database settings.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the app directory to the path so we can import models
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.ports import get_database_url
from app.models.base import Base

# Import all models to ensure they're registered with Base.metadata
from app.models import rtu, user, alarm, historian, pid, audit, discovery, template  # noqa: F401
from app.models import config as config_models  # noqa: F401

# Alembic Config object
config = context.config

# Configure logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from app configuration
config.set_main_option("sqlalchemy.url", get_database_url())

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This generates SQL scripts without connecting to the database.
    Useful for generating migration SQL for manual review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
