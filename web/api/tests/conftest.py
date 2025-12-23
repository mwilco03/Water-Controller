"""
Water Treatment Controller - Test Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Pytest fixtures for API testing.
"""

import os
import pytest
from datetime import datetime, timezone
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Set test environment before importing app
os.environ["WTC_DB_PATH"] = ":memory:"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app
from app.models.base import Base, get_db
from app.models.rtu import RTU, Slot, Sensor, Control, RtuState, SlotStatus


# Create test database engine
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db() -> Generator[Session, None, None]:
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create test client with database override."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_rtu(db_session: Session) -> RTU:
    """Create a sample RTU for testing."""
    rtu = RTU(
        station_name="test-rtu-1",
        ip_address="192.168.1.10",
        vendor_id="0x002A",
        device_id="0x0405",
        slot_count=8,
        state=RtuState.OFFLINE,
        state_since=datetime.now(timezone.utc),
    )
    db_session.add(rtu)
    db_session.flush()

    # Create slots
    for i in range(1, 9):
        slot = Slot(
            rtu_id=rtu.id,
            slot_number=i,
            status=SlotStatus.EMPTY,
        )
        db_session.add(slot)

    db_session.commit()
    db_session.refresh(rtu)
    return rtu


@pytest.fixture
def running_rtu(db_session: Session) -> RTU:
    """Create a sample RTU in RUNNING state."""
    rtu = RTU(
        station_name="running-rtu",
        ip_address="192.168.1.20",
        vendor_id="0x002A",
        device_id="0x0405",
        slot_count=8,
        state=RtuState.RUNNING,
        state_since=datetime.now(timezone.utc),
    )
    db_session.add(rtu)
    db_session.flush()

    # Create slots with one configured
    for i in range(1, 9):
        slot = Slot(
            rtu_id=rtu.id,
            slot_number=i,
            module_type="AI-8" if i == 1 else None,
            status=SlotStatus.OK if i == 1 else SlotStatus.EMPTY,
        )
        db_session.add(slot)

    db_session.commit()
    db_session.refresh(rtu)
    return rtu


@pytest.fixture
def sample_sensor(db_session: Session, running_rtu: RTU) -> Sensor:
    """Create a sample sensor for testing."""
    slot = db_session.query(Slot).filter(
        Slot.rtu_id == running_rtu.id,
        Slot.slot_number == 1
    ).first()

    sensor = Sensor(
        rtu_id=running_rtu.id,
        slot_id=slot.id,
        tag="TK-101-LVL",
        channel=0,
        sensor_type="level",
        unit="ft",
        scale_min=0.0,
        scale_max=32767.0,
        eng_min=0.0,
        eng_max=20.0,
    )
    db_session.add(sensor)
    db_session.commit()
    db_session.refresh(sensor)
    return sensor
