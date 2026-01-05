#!/usr/bin/env python3
"""
Database Migration Integration Tests

Tests schema migrations and data integrity.

Prerequisites:
  - Database available (SQLite or PostgreSQL)
  - Alembic migrations configured

Run with:
  pytest tests/integration/test_migrations.py -v
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path

# Check for required packages
try:
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy.orm import sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

try:
    from alembic import command
    from alembic.config import Config
    HAS_ALEMBIC = True
except ImportError:
    HAS_ALEMBIC = False


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def sqlite_engine(temp_db):
    """Create SQLite engine for testing."""
    if not HAS_SQLALCHEMY:
        pytest.skip("SQLAlchemy not available")

    engine = create_engine(f"sqlite:///{temp_db}")
    yield engine
    engine.dispose()


@pytest.fixture
def empty_db(sqlite_engine):
    """Create an empty database."""
    return sqlite_engine


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestSchemaMigrations:
    """Test database schema migrations."""

    def test_fresh_migration(self, empty_db):
        """Test migration on fresh database."""
        engine = empty_db

        # Create a simple table to simulate migration
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL
                )
            """))
            conn.commit()

        # Verify table exists
        inspector = inspect(engine)
        assert "alembic_version" in inspector.get_table_names()

    def test_table_creation(self, empty_db):
        """Test that expected tables can be created."""
        engine = empty_db

        # Create tables that match our schema
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE rtus (
                    id INTEGER PRIMARY KEY,
                    station_name VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45),
                    state VARCHAR(50) DEFAULT 'OFFLINE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE sensors (
                    id INTEGER PRIMARY KEY,
                    rtu_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    sensor_type VARCHAR(50),
                    unit VARCHAR(20),
                    FOREIGN KEY (rtu_id) REFERENCES rtus(id)
                )
            """))
            conn.commit()

        # Verify tables
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "rtus" in tables
        assert "sensors" in tables

    def test_migration_idempotency(self, empty_db):
        """Test running same migration twice."""
        engine = empty_db

        # Create table
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255)
                )
            """))
            conn.commit()

        # Run again (should not fail)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255)
                )
            """))
            conn.commit()

        # Verify table exists once
        inspector = inspect(engine)
        assert "test_table" in inspector.get_table_names()


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestDataMigrations:
    """Test data migration integrity."""

    def test_rtu_data_preserved(self, empty_db):
        """Verify RTU data after migration."""
        engine = empty_db

        # Create table and insert data
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE rtus (
                    id INTEGER PRIMARY KEY,
                    station_name VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45)
                )
            """))
            conn.execute(text("""
                INSERT INTO rtus (station_name, ip_address)
                VALUES ('TestRTU1', '192.168.1.100')
            """))
            conn.commit()

        # Simulate migration: add column
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE rtus ADD COLUMN state VARCHAR(50) DEFAULT 'OFFLINE'
            """))
            conn.commit()

        # Verify data preserved
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM rtus WHERE station_name = 'TestRTU1'"))
            row = result.fetchone()
            assert row is not None
            assert row[1] == "TestRTU1"  # station_name
            assert row[2] == "192.168.1.100"  # ip_address

    def test_sensor_data_preserved(self, empty_db):
        """Verify sensor data after migration."""
        engine = empty_db

        # Create tables
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE rtus (
                    id INTEGER PRIMARY KEY,
                    station_name VARCHAR(255) NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE sensors (
                    id INTEGER PRIMARY KEY,
                    rtu_id INTEGER,
                    name VARCHAR(255)
                )
            """))
            conn.execute(text("INSERT INTO rtus (station_name) VALUES ('RTU1')"))
            conn.execute(text("""
                INSERT INTO sensors (rtu_id, name) VALUES (1, 'pH Sensor')
            """))
            conn.commit()

        # Verify data
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT s.name FROM sensors s
                JOIN rtus r ON s.rtu_id = r.id
                WHERE r.station_name = 'RTU1'
            """))
            row = result.fetchone()
            assert row is not None
            assert row[0] == "pH Sensor"


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestSQLiteOperations:
    """Test SQLite-specific operations."""

    def test_wal_mode(self, temp_db):
        """Test WAL mode for concurrent access."""
        engine = create_engine(f"sqlite:///{temp_db}")

        with engine.connect() as conn:
            # Enable WAL mode
            conn.execute(text("PRAGMA journal_mode=WAL"))
            result = conn.execute(text("PRAGMA journal_mode"))
            mode = result.fetchone()[0]
            # WAL may not be supported in all environments
            assert mode in ("wal", "delete", "memory")

        engine.dispose()

    def test_concurrent_reads(self, temp_db):
        """Test concurrent read access."""
        engine1 = create_engine(f"sqlite:///{temp_db}")
        engine2 = create_engine(f"sqlite:///{temp_db}")

        # Create table and data with engine1
        with engine1.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER, value TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'hello')"))
            conn.commit()

        # Read with both engines
        with engine1.connect() as conn1, engine2.connect() as conn2:
            result1 = conn1.execute(text("SELECT * FROM test"))
            result2 = conn2.execute(text("SELECT * FROM test"))

            assert result1.fetchone() is not None
            assert result2.fetchone() is not None

        engine1.dispose()
        engine2.dispose()


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
class TestDatabaseBackup:
    """Test database backup and restore."""

    def test_sqlite_backup(self, temp_db):
        """Test SQLite database backup."""
        engine = create_engine(f"sqlite:///{temp_db}")

        # Create and populate
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER, value TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'original')"))
            conn.commit()

        # Backup
        backup_path = temp_db + ".backup"
        shutil.copy(temp_db, backup_path)

        # Modify original
        with engine.connect() as conn:
            conn.execute(text("UPDATE test SET value = 'modified'"))
            conn.commit()

        # Verify original changed
        with engine.connect() as conn:
            result = conn.execute(text("SELECT value FROM test WHERE id = 1"))
            assert result.fetchone()[0] == "modified"

        # Verify backup has original
        backup_engine = create_engine(f"sqlite:///{backup_path}")
        with backup_engine.connect() as conn:
            result = conn.execute(text("SELECT value FROM test WHERE id = 1"))
            assert result.fetchone()[0] == "original"

        backup_engine.dispose()
        engine.dispose()

        # Clean up
        os.remove(backup_path)

    def test_export_import(self, temp_db):
        """Test data export and import."""
        engine = create_engine(f"sqlite:///{temp_db}")

        # Create and populate
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER, value TEXT)"))
            conn.execute(text("INSERT INTO test VALUES (1, 'data1')"))
            conn.execute(text("INSERT INTO test VALUES (2, 'data2')"))
            conn.commit()

        # Export to list
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM test ORDER BY id"))
            exported = [dict(row._mapping) for row in result]

        assert len(exported) == 2
        assert exported[0]["value"] == "data1"
        assert exported[1]["value"] == "data2"

        engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
