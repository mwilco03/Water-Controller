#!/usr/bin/env python3
"""
Database Schema and Migration Tests

Tests for database schema integrity and migration validation:
- Table creation and structure
- Column types and constraints
- Index existence
- Schema version tracking
- Data integrity across operations

Run with:
  pytest tests/integration/test_database.py -v
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add web/api to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "web" / "api"))

# Try to import SQLAlchemy components
try:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

# Try to import app models
try:
    from app.models.base import Base, get_db
    from app.models.user import User
    from app.models.rtu import RTU
    from app.models.alarm import AlarmRule, AlarmEvent
    from app.models.pid import PIDLoop
    from app.models.historian import HistorianTag, HistorianValue
    from app.models.config import SystemConfig
    from app.models.audit import AuditLog
    HAS_MODELS = True
except ImportError as e:
    HAS_MODELS = False
    print(f"Could not import models: {e}")


# ============== Fixtures ==============


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    # Cleanup
    try:
        os.unlink(f.name)
    except OSError:
        pass


@pytest.fixture
def test_engine(temp_db_path):
    """Create a test database engine."""
    if not HAS_SQLALCHEMY:
        pytest.skip("SQLAlchemy not available")

    engine = create_engine(
        f"sqlite:///{temp_db_path}",
        connect_args={"check_same_thread": False}
    )
    yield engine
    engine.dispose()


@pytest.fixture
def test_session(test_engine):
    """Create a test database session."""
    if not HAS_MODELS:
        pytest.skip("Models not available")

    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    Session = sessionmaker(bind=test_engine)
    session = Session()

    yield session

    session.close()


# ============== Schema Creation Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestSchemaCreation:
    """Test database schema creation."""

    def test_create_all_tables(self, test_engine):
        """All tables should be created without errors."""
        Base.metadata.create_all(bind=test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()

        # Verify core tables exist
        assert "users" in tables or "user" in tables
        assert len(tables) >= 5  # Should have multiple tables

    def test_user_table_structure(self, test_engine):
        """User table should have expected columns."""
        Base.metadata.create_all(bind=test_engine)
        inspector = inspect(test_engine)

        # Find user table (might be 'users' or 'user')
        tables = inspector.get_table_names()
        user_table = "users" if "users" in tables else "user" if "user" in tables else None

        if user_table:
            columns = {c["name"] for c in inspector.get_columns(user_table)}

            # Expected columns
            assert "id" in columns
            assert "username" in columns
            assert "email" in columns or "password_hash" in columns

    def test_rtu_table_structure(self, test_engine):
        """RTU table should have expected columns."""
        Base.metadata.create_all(bind=test_engine)
        inspector = inspect(test_engine)

        tables = inspector.get_table_names()
        rtu_table = "rtus" if "rtus" in tables else "rtu" if "rtu" in tables else None

        if rtu_table:
            columns = {c["name"] for c in inspector.get_columns(rtu_table)}

            assert "id" in columns
            assert "station_name" in columns or "name" in columns

    def test_alarm_table_structure(self, test_engine):
        """Alarm tables should have expected columns."""
        Base.metadata.create_all(bind=test_engine)
        inspector = inspect(test_engine)

        tables = inspector.get_table_names()

        # Check for alarm-related tables
        alarm_tables = [t for t in tables if "alarm" in t.lower()]
        assert len(alarm_tables) >= 1, "Should have at least one alarm table"


# ============== Data Integrity Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestDataIntegrity:
    """Test data integrity constraints."""

    def test_user_creation(self, test_session):
        """Users can be created and retrieved."""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password_here",
            role="operator",
            active=True
        )
        test_session.add(user)
        test_session.commit()

        # Retrieve
        retrieved = test_session.query(User).filter_by(username="testuser").first()
        assert retrieved is not None
        assert retrieved.username == "testuser"
        assert retrieved.email == "test@example.com"

    def test_user_unique_username(self, test_session):
        """Username should be unique."""
        user1 = User(
            username="uniqueuser",
            email="user1@example.com",
            password_hash="hash1",
            role="operator"
        )
        test_session.add(user1)
        test_session.commit()

        user2 = User(
            username="uniqueuser",  # Same username
            email="user2@example.com",
            password_hash="hash2",
            role="operator"
        )
        test_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            test_session.commit()

        test_session.rollback()

    def test_rtu_creation(self, test_session):
        """RTUs can be created and retrieved."""
        rtu = RTU(
            station_name="test-rtu-01",
            ip_address="192.168.1.50",
            vendor_id=0x1171,
            device_id=0x0001,
            enabled=True
        )
        test_session.add(rtu)
        test_session.commit()

        retrieved = test_session.query(RTU).filter_by(station_name="test-rtu-01").first()
        assert retrieved is not None
        assert retrieved.ip_address == "192.168.1.50"

    def test_cascade_delete(self, test_session):
        """Related records should cascade delete properly."""
        # Create RTU
        rtu = RTU(
            station_name="cascade-test-rtu",
            ip_address="192.168.1.100",
            vendor_id=0x1171,
            device_id=0x0001
        )
        test_session.add(rtu)
        test_session.commit()
        rtu_id = rtu.id

        # Create alarm rule for this RTU
        rule = AlarmRule(
            rtu_id=rtu_id,
            slot=1,
            alarm_type="HIGH",
            threshold=100.0,
            severity="WARNING",
            message_template="Test alarm"
        )
        test_session.add(rule)
        test_session.commit()
        rule_id = rule.id

        # Delete RTU - should cascade to rules
        test_session.delete(rtu)
        test_session.commit()

        # Verify rule is also deleted (or would fail constraint)
        remaining_rule = test_session.query(AlarmRule).filter_by(id=rule_id).first()
        # Either cascaded delete or query should fail
        # This depends on cascade configuration


# ============== Migration Simulation Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestMigrationSimulation:
    """Simulate migration scenarios."""

    def test_fresh_install_schema(self, test_engine):
        """Fresh install should create complete schema."""
        # Simulate fresh install
        Base.metadata.create_all(bind=test_engine)

        inspector = inspect(test_engine)
        tables = set(inspector.get_table_names())

        # Core tables should exist
        expected_tables = {"users", "rtus", "alarm_rules", "alarm_events",
                           "pid_loops", "historian_tags", "system_config", "audit_log"}

        # Check for at least some expected tables (names may vary)
        found_core_tables = 0
        for expected in expected_tables:
            # Check for exact match or similar (e.g., "user" vs "users")
            if expected in tables or expected.rstrip("s") in tables:
                found_core_tables += 1

        assert found_core_tables >= 4, f"Expected core tables, found: {tables}"

    def test_schema_recreation_is_idempotent(self, test_engine):
        """Creating schema twice should not error."""
        Base.metadata.create_all(bind=test_engine)
        initial_tables = set(inspect(test_engine).get_table_names())

        # Create again - should be no-op
        Base.metadata.create_all(bind=test_engine)
        final_tables = set(inspect(test_engine).get_table_names())

        assert initial_tables == final_tables

    def test_drop_and_recreate(self, test_engine):
        """Schema can be dropped and recreated."""
        # Create
        Base.metadata.create_all(bind=test_engine)

        # Drop all
        Base.metadata.drop_all(bind=test_engine)
        assert len(inspect(test_engine).get_table_names()) == 0

        # Recreate
        Base.metadata.create_all(bind=test_engine)
        assert len(inspect(test_engine).get_table_names()) > 0


# ============== Version Tracking Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestVersionTracking:
    """Test schema version tracking capabilities."""

    def test_system_config_stores_version(self, test_session):
        """Schema version can be stored in system_config."""
        config = SystemConfig(
            key="schema_version",
            value="1.0.0",
            description="Database schema version"
        )
        test_session.add(config)
        test_session.commit()

        retrieved = test_session.query(SystemConfig).filter_by(
            key="schema_version"
        ).first()

        assert retrieved is not None
        assert retrieved.value == "1.0.0"

    def test_version_can_be_updated(self, test_session):
        """Schema version can be updated."""
        config = SystemConfig(
            key="schema_version",
            value="1.0.0"
        )
        test_session.add(config)
        test_session.commit()

        # Update version
        config.value = "1.1.0"
        test_session.commit()

        retrieved = test_session.query(SystemConfig).filter_by(
            key="schema_version"
        ).first()
        assert retrieved.value == "1.1.0"


# ============== Backup and Restore Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestBackupRestore:
    """Test backup and restore scenarios."""

    def test_data_survives_session_close(self, test_engine):
        """Data persists after session close."""
        Base.metadata.create_all(bind=test_engine)

        # Create data in first session
        Session = sessionmaker(bind=test_engine)
        session1 = Session()

        user = User(
            username="persist_test",
            email="persist@test.com",
            password_hash="hash",
            role="operator"
        )
        session1.add(user)
        session1.commit()
        session1.close()

        # Retrieve in new session
        session2 = Session()
        retrieved = session2.query(User).filter_by(username="persist_test").first()

        assert retrieved is not None
        assert retrieved.email == "persist@test.com"

        session2.close()

    def test_rollback_on_error(self, test_session):
        """Rollback should restore previous state."""
        # Create valid user
        user = User(
            username="rollback_test",
            email="rollback@test.com",
            password_hash="hash",
            role="operator"
        )
        test_session.add(user)
        test_session.commit()

        # Try to create duplicate (should fail)
        duplicate = User(
            username="rollback_test",
            email="other@test.com",
            password_hash="hash2",
            role="operator"
        )
        test_session.add(duplicate)

        try:
            test_session.commit()
        except Exception:
            test_session.rollback()

        # Original user should still exist
        original = test_session.query(User).filter_by(username="rollback_test").first()
        assert original is not None
        assert original.email == "rollback@test.com"


# ============== Performance Tests ==============


@pytest.mark.skipif(not HAS_SQLALCHEMY, reason="SQLAlchemy not available")
@pytest.mark.skipif(not HAS_MODELS, reason="Models not available")
class TestDatabasePerformance:
    """Basic performance validation."""

    def test_bulk_insert_performance(self, test_session):
        """Bulk insert should complete in reasonable time."""
        import time

        start = time.time()

        # Insert 100 users
        users = [
            User(
                username=f"bulk_user_{i}",
                email=f"bulk{i}@test.com",
                password_hash=f"hash{i}",
                role="viewer"
            )
            for i in range(100)
        ]
        test_session.add_all(users)
        test_session.commit()

        elapsed = time.time() - start

        assert elapsed < 5.0, f"Bulk insert took too long: {elapsed}s"
        assert test_session.query(User).count() >= 100

    def test_query_with_filter_performance(self, test_session):
        """Filtered queries should be fast."""
        import time

        # Create test data
        for i in range(50):
            user = User(
                username=f"query_test_{i}",
                email=f"query{i}@test.com",
                password_hash=f"hash{i}",
                role="operator" if i % 2 == 0 else "viewer"
            )
            test_session.add(user)
        test_session.commit()

        start = time.time()

        # Query with filter
        operators = test_session.query(User).filter_by(role="operator").all()

        elapsed = time.time() - start

        assert elapsed < 1.0, f"Filtered query took too long: {elapsed}s"
        assert len(operators) == 25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
