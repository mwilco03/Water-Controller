"""
Water Treatment Controller - RTU API Endpoint Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

API endpoint tests for RTU operations.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.models.rtu import RTU, Control, RtuState, Sensor, Slot, SlotStatus


class TestRtuEndpoints:
    """Tests for RTU CRUD endpoints."""

    def test_list_rtus_empty(self, client):
        """GET /api/v1/rtus should return empty list when no RTUs exist."""
        response = client.get("/api/v1/rtus")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_list_rtus(self, client, sample_rtu):
        """GET /api/v1/rtus should return all RTUs."""
        response = client.get("/api/v1/rtus")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["station_name"] == sample_rtu.station_name

    def test_get_rtu(self, client, sample_rtu):
        """GET /api/v1/rtus/{name} should return RTU details."""
        response = client.get(f"/api/v1/rtus/{sample_rtu.station_name}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["station_name"] == sample_rtu.station_name
        assert data["data"]["ip_address"] == sample_rtu.ip_address
        assert data["data"]["state"] == sample_rtu.state

    def test_get_rtu_not_found(self, client):
        """GET /api/v1/rtus/{name} should return 404 for nonexistent RTU."""
        response = client.get("/api/v1/rtus/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_create_rtu(self, client, db_session):
        """POST /api/v1/rtus should create a new RTU."""
        response = client.post(
            "/api/v1/rtus",
            json={
                "station_name": "new-rtu",
                "ip_address": "192.168.1.100",
                "vendor_id": "0x002A",
                "device_id": "0x0001",
                "slot_count": 8,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["station_name"] == "new-rtu"
        assert data["data"]["state"] == RtuState.OFFLINE

        # Verify RTU was created in database
        rtu = db_session.query(RTU).filter(RTU.station_name == "new-rtu").first()
        assert rtu is not None

        # Verify slots were created
        slots = db_session.query(Slot).filter(Slot.rtu_id == rtu.id).count()
        assert slots == 8

    def test_create_rtu_duplicate_name(self, client, sample_rtu):
        """POST /api/v1/rtus should reject duplicate station names."""
        response = client.post(
            "/api/v1/rtus",
            json={
                "station_name": sample_rtu.station_name,
                "ip_address": "192.168.1.200",
                "vendor_id": "0x002A",
                "device_id": "0x0001",
            },
        )
        assert response.status_code == 409

    def test_delete_rtu(self, client, sample_rtu, db_session):
        """DELETE /api/v1/rtus/{name} should delete RTU and cascade."""
        rtu_id = sample_rtu.id
        response = client.delete(f"/api/v1/rtus/{sample_rtu.station_name}")
        assert response.status_code == 200

        # Verify RTU was deleted
        rtu = db_session.query(RTU).filter(RTU.id == rtu_id).first()
        assert rtu is None

        # Verify slots were cascade deleted
        slots = db_session.query(Slot).filter(Slot.rtu_id == rtu_id).count()
        assert slots == 0

    def test_delete_running_rtu_fails(self, client, running_rtu):
        """DELETE /api/v1/rtus/{name} should fail for RUNNING RTU."""
        response = client.delete(f"/api/v1/rtus/{running_rtu.station_name}")
        # Should fail because RTU is in RUNNING state
        assert response.status_code == 409


class TestRtuStateEndpoints:
    """Tests for RTU state management endpoints."""

    def test_get_rtu_state(self, client, sample_rtu):
        """GET /api/v1/rtus/{name}/state should return current state."""
        response = client.get(f"/api/v1/rtus/{sample_rtu.station_name}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["state"] == sample_rtu.state

    def test_rtu_state_filtering(self, client, sample_rtu, running_rtu):
        """GET /api/v1/rtus?state=... should filter by state."""
        response = client.get("/api/v1/rtus", params={"state": RtuState.RUNNING})
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["station_name"] == running_rtu.station_name

        response = client.get("/api/v1/rtus", params={"state": RtuState.OFFLINE})
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["station_name"] == sample_rtu.station_name


class TestSlotEndpoints:
    """Tests for slot management endpoints."""

    def test_list_slots(self, client, sample_rtu):
        """GET /api/v1/rtus/{name}/slots should return all slots."""
        response = client.get(f"/api/v1/rtus/{sample_rtu.station_name}/slots")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == sample_rtu.slot_count

    def test_get_slot(self, client, running_rtu):
        """GET /api/v1/rtus/{name}/slots/{num} should return slot details."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/slots/1")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["slot_number"] == 1
        assert data["data"]["module_type"] == "AI-8"
        assert data["data"]["status"] == SlotStatus.OK

    def test_get_slot_not_found(self, client, sample_rtu):
        """GET /api/v1/rtus/{name}/slots/{num} should return 404 for invalid slot."""
        response = client.get(f"/api/v1/rtus/{sample_rtu.station_name}/slots/99")
        assert response.status_code == 404


class TestSensorEndpoints:
    """Tests for sensor management endpoints."""

    def test_list_sensors_empty(self, client, running_rtu):
        """GET /api/v1/rtus/{name}/sensors should return empty list."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/sensors")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_list_sensors(self, client, running_rtu, sample_sensor):
        """GET /api/v1/rtus/{name}/sensors should return sensors."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/sensors")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["tag"] == sample_sensor.tag

    def test_get_sensor_by_tag(self, client, sample_sensor):
        """GET /api/v1/sensors/{tag} should return sensor details."""
        response = client.get(f"/api/v1/sensors/{sample_sensor.tag}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["tag"] == sample_sensor.tag
        assert data["data"]["sensor_type"] == sample_sensor.sensor_type


class TestControlEndpoints:
    """Tests for control management endpoints."""

    def test_list_controls_empty(self, client, running_rtu):
        """GET /api/v1/rtus/{name}/controls should return empty list."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/controls")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_create_control(self, client, running_rtu, db_session):
        """POST /api/v1/rtus/{name}/controls should create a control."""
        # First get a slot
        slot = db_session.query(Slot).filter(
            Slot.rtu_id == running_rtu.id,
            Slot.slot_number == 1
        ).first()

        response = client.post(
            f"/api/v1/rtus/{running_rtu.station_name}/controls",
            json={
                "tag": "P-101",
                "slot_id": slot.id,
                "channel": 0,
                "control_type": "discrete",
                "equipment_type": "pump",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["tag"] == "P-101"
        assert data["data"]["control_type"] == "discrete"


class TestRtuStats:
    """Tests for RTU statistics endpoints."""

    def test_get_rtu_stats(self, client, running_rtu, sample_sensor, db_session):
        """GET /api/v1/rtus/{name}/stats should return RTU statistics."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/stats")
        assert response.status_code == 200
        data = response.json()

        # Should include counts
        assert "sensor_count" in data["data"]
        assert "control_count" in data["data"]
        assert data["data"]["sensor_count"] == 1  # From sample_sensor fixture
