"""
Water Treatment Controller - Persistence Layer Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Integration tests for the persistence layer.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.rtu import RTU, Control, RtuState, Sensor, Slot, SlotStatus
from app.models.user import UserSession


# Override get_db for testing
_test_db = None


def get_test_db():
    """Get test database session."""
    global _test_db
    if _test_db is not None:
        yield _test_db


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Create a fresh database session for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    # Override the persistence layer's get_db
    global _test_db
    _test_db = db

    # Patch the persistence module
    import app.persistence.rtu as rtu_module
    original_get_db = rtu_module.get_db
    rtu_module.get_db = lambda: _db_context_manager(db)

    try:
        yield db
    finally:
        _test_db = None
        rtu_module.get_db = original_get_db
        db.close()
        Base.metadata.drop_all(bind=engine)


class _db_context_manager:
    """Simple context manager for testing."""
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *args):
        pass


class TestRtuPersistence:
    """Tests for RTU persistence operations."""

    def test_create_rtu_device(self, db_session):
        """Creating an RTU should create default slots."""
        from app.persistence.rtu import create_rtu_device, get_rtu_device

        device_id = create_rtu_device({
            "station_name": "test-rtu-1",
            "ip_address": "192.168.1.10",
            "vendor_id": 1171,
            "device_id": 1,
            "slot_count": 8,
        })

        assert device_id > 0

        # Verify device was created
        device = get_rtu_device("test-rtu-1")
        assert device is not None
        assert device["station_name"] == "test-rtu-1"
        assert device["ip_address"] == "192.168.1.10"
        assert device["vendor_id"] == "0x0493"  # 1171 in hex
        assert device["state"] == RtuState.OFFLINE

        # Verify slots were created
        slots = db_session.query(Slot).filter(Slot.rtu_id == device_id).all()
        assert len(slots) == 8
        for i, slot in enumerate(sorted(slots, key=lambda s: s.slot_number)):
            assert slot.slot_number == i + 1
            assert slot.status == SlotStatus.EMPTY

    def test_get_rtu_devices(self, db_session):
        """Should return all RTU devices ordered by name."""
        from app.persistence.rtu import create_rtu_device, get_rtu_devices

        create_rtu_device({"station_name": "rtu-b", "ip_address": "192.168.1.2"})
        create_rtu_device({"station_name": "rtu-a", "ip_address": "192.168.1.1"})
        create_rtu_device({"station_name": "rtu-c", "ip_address": "192.168.1.3"})

        devices = get_rtu_devices()

        assert len(devices) == 3
        assert devices[0]["station_name"] == "rtu-a"
        assert devices[1]["station_name"] == "rtu-b"
        assert devices[2]["station_name"] == "rtu-c"

    def test_update_rtu_device(self, db_session):
        """Should update RTU device properties."""
        from app.persistence.rtu import create_rtu_device, get_rtu_device, update_rtu_device

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
            "slot_count": 8,
        })

        result = update_rtu_device("test-rtu", {
            "ip_address": "192.168.1.20",
            "vendor_id": 42,
            "device_id": 1,
        })

        assert result is True
        device = get_rtu_device("test-rtu")
        assert device["ip_address"] == "192.168.1.20"
        assert device["vendor_id"] == "0x002A"  # 42 in hex

    def test_delete_rtu_device(self, db_session):
        """Should delete RTU and cascade to slots/sensors/controls."""
        from app.persistence.rtu import (
            create_rtu_device,
            delete_rtu_device,
            get_rtu_device,
            upsert_rtu_sensor,
        )

        device_id = create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
            "slot_count": 8,
        })

        # Add a sensor
        upsert_rtu_sensor({
            "rtu_station": "test-rtu",
            "sensor_id": "TK-101-LVL",
            "sensor_type": "level",
        })

        # Delete the RTU
        result = delete_rtu_device("test-rtu")
        assert result is True

        # Verify RTU is gone
        device = get_rtu_device("test-rtu")
        assert device is None

        # Verify slots are gone
        slots = db_session.query(Slot).filter(Slot.rtu_id == device_id).all()
        assert len(slots) == 0

    def test_update_rtu_state(self, db_session):
        """Should update RTU state with reason."""
        from app.persistence.rtu import create_rtu_device, get_rtu_device, update_rtu_state

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        update_rtu_state("test-rtu", RtuState.CONNECTING, reason="Operator request")

        device = get_rtu_device("test-rtu")
        assert device["state"] == RtuState.CONNECTING
        assert device["transition_reason"] == "Operator request"


class TestSensorPersistence:
    """Tests for sensor persistence operations."""

    def test_upsert_sensor_insert(self, db_session):
        """Should insert new sensor."""
        from app.persistence.rtu import create_rtu_device, get_rtu_sensors, upsert_rtu_sensor

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
            "slot_count": 8,
        })

        sensor_id = upsert_rtu_sensor({
            "rtu_station": "test-rtu",
            "sensor_id": "TK-101-LVL",
            "sensor_type": "level",
            "unit": "ft",
            "scale_min": 0,
            "scale_max": 100,
        })

        assert sensor_id > 0

        sensors = get_rtu_sensors("test-rtu")
        assert len(sensors) == 1
        assert sensors[0]["sensor_id"] == "TK-101-LVL"
        assert sensors[0]["sensor_type"] == "level"
        assert sensors[0]["unit"] == "ft"

    def test_upsert_sensor_update(self, db_session):
        """Should update existing sensor."""
        from app.persistence.rtu import create_rtu_device, get_rtu_sensors, upsert_rtu_sensor

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        # Insert
        upsert_rtu_sensor({
            "rtu_station": "test-rtu",
            "sensor_id": "TK-101-LVL",
            "sensor_type": "level",
            "unit": "ft",
        })

        # Update
        upsert_rtu_sensor({
            "rtu_station": "test-rtu",
            "sensor_id": "TK-101-LVL",
            "sensor_type": "level",
            "unit": "m",  # Changed unit
        })

        sensors = get_rtu_sensors("test-rtu")
        assert len(sensors) == 1
        assert sensors[0]["unit"] == "m"

    def test_clear_rtu_sensors(self, db_session):
        """Should clear all sensors for an RTU."""
        from app.persistence.rtu import (
            clear_rtu_sensors,
            create_rtu_device,
            get_rtu_sensors,
            upsert_rtu_sensor,
        )

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        upsert_rtu_sensor({"rtu_station": "test-rtu", "sensor_id": "S1", "sensor_type": "level"})
        upsert_rtu_sensor({"rtu_station": "test-rtu", "sensor_id": "S2", "sensor_type": "flow"})

        count = clear_rtu_sensors("test-rtu")
        assert count == 2

        sensors = get_rtu_sensors("test-rtu")
        assert len(sensors) == 0


class TestControlPersistence:
    """Tests for control persistence operations."""

    def test_upsert_control_insert(self, db_session):
        """Should insert new control."""
        from app.persistence.rtu import create_rtu_device, get_rtu_controls, upsert_rtu_control

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        control_id = upsert_rtu_control({
            "rtu_station": "test-rtu",
            "control_id": "P-101",
            "control_type": "discrete",
            "equipment_type": "pump",
        })

        assert control_id > 0

        controls = get_rtu_controls("test-rtu")
        assert len(controls) == 1
        assert controls[0]["control_id"] == "P-101"
        assert controls[0]["control_type"] == "discrete"
        assert controls[0]["equipment_type"] == "pump"

    def test_upsert_control_legacy_command_type(self, db_session):
        """Should map legacy command_type to control_type."""
        from app.persistence.rtu import create_rtu_device, get_rtu_controls, upsert_rtu_control

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        # Using legacy command_type
        upsert_rtu_control({
            "rtu_station": "test-rtu",
            "control_id": "P-101",
            "command_type": "on_off",
        })

        controls = get_rtu_controls("test-rtu")
        assert controls[0]["control_type"] == "discrete"
        assert controls[0]["command_type"] == "on_off"  # Backward compatible


class TestSessionPersistence:
    """Tests for session persistence operations."""

    def test_user_session_groups_serialization(self, db_session):
        """UserSession should serialize groups to JSON and back."""
        groups = ["admin", "operators", "viewers"]
        session = UserSession(
            token="test-token-123",
            username="testuser",
            role="admin",
            groups=json.dumps(groups),
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        result = session.to_dict()

        # groups should be deserialized to a list
        assert isinstance(result["groups"], list)
        assert result["groups"] == groups

    def test_user_session_groups_list_property(self, db_session):
        """UserSession.groups_list property should work bidirectionally."""
        session = UserSession(
            token="test-token-456",
            username="testuser",
            role="operator",
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )

        # Set groups using property
        session.groups_list = ["group1", "group2"]
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        # Read groups using property
        assert session.groups_list == ["group1", "group2"]

    def test_user_session_invalid_json_groups(self, db_session):
        """UserSession should handle invalid JSON in groups gracefully."""
        session = UserSession(
            token="test-token-789",
            username="testuser",
            role="viewer",
            groups="not valid json",
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        result = session.to_dict()

        # Should return empty list for invalid JSON
        assert result["groups"] == []
        assert session.groups_list == []


class TestSlotPersistence:
    """Tests for slot operations."""

    def test_get_rtu_slots(self, db_session):
        """Should return all slots for an RTU."""
        from app.persistence.rtu import create_rtu_device, get_rtu_slots

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
            "slot_count": 4,
        })

        slots = get_rtu_slots("test-rtu")

        assert len(slots) == 4
        for i, slot in enumerate(slots):
            assert slot["slot_number"] == i + 1
            assert slot["status"] == SlotStatus.EMPTY

    def test_update_slot(self, db_session):
        """Should update slot module information."""
        from app.persistence.rtu import create_rtu_device, get_rtu_slots, update_slot

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
            "slot_count": 4,
        })

        result = update_slot("test-rtu", 1, module_type="AI-8", status=SlotStatus.OK)

        assert result is True

        slots = get_rtu_slots("test-rtu")
        slot_1 = next(s for s in slots if s["slot_number"] == 1)
        assert slot_1["module_type"] == "AI-8"
        assert slot_1["status"] == SlotStatus.OK


class TestInventoryPersistence:
    """Tests for inventory operations."""

    def test_get_rtu_inventory(self, db_session):
        """Should return complete RTU inventory."""
        from app.persistence.rtu import (
            create_rtu_device,
            get_rtu_inventory,
            upsert_rtu_control,
            upsert_rtu_sensor,
        )

        create_rtu_device({
            "station_name": "test-rtu",
            "ip_address": "192.168.1.10",
        })

        upsert_rtu_sensor({
            "rtu_station": "test-rtu",
            "sensor_id": "S1",
            "sensor_type": "level",
        })

        upsert_rtu_control({
            "rtu_station": "test-rtu",
            "control_id": "C1",
            "control_type": "discrete",
        })

        inventory = get_rtu_inventory("test-rtu")

        assert inventory is not None
        assert inventory["rtu_station"] == "test-rtu"
        assert len(inventory["sensors"]) == 1
        assert len(inventory["controls"]) == 1
        assert inventory["sensors"][0]["sensor_id"] == "S1"
        assert inventory["controls"][0]["control_id"] == "C1"
