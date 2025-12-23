"""
Water Treatment Controller - Configuration Template Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.rtu import RTU, Slot, Sensor, Control
from app.models.template import ConfigTemplate


@pytest.fixture
def sample_template(db_session: Session) -> ConfigTemplate:
    """Create a sample configuration template."""
    template = ConfigTemplate(
        name="Water Treatment Standard",
        description="Standard configuration for water treatment RTUs",
        category="water-treatment",
        vendor_id=0x1234,
        device_id=0x5678,
        slot_count=16,
        config_data={
            "slots": [
                {"slot_number": 0, "module_type": "analog_input", "module_id": "AI8"},
                {"slot_number": 1, "module_type": "digital_output", "module_id": "DO8"},
            ],
            "sensors": [
                {
                    "tag": "TK-101-LVL",
                    "slot_number": 0,
                    "channel": 0,
                    "sensor_type": "level",
                    "unit": "ft",
                    "scale_min": 0,
                    "scale_max": 4095,
                    "eng_min": 0.0,
                    "eng_max": 20.0,
                },
            ],
            "controls": [
                {
                    "tag": "PMP-101",
                    "slot_number": 1,
                    "channel": 0,
                    "control_type": "discrete",
                    "equipment_type": "pump",
                },
            ],
            "alarms": [
                {
                    "tag": "TK-101-LVL",
                    "alarm_type": "HIGH",
                    "priority": "HIGH",
                    "setpoint": 18.0,
                    "deadband": 0.5,
                    "message_template": "Tank level high: {value} ft",
                },
            ],
            "pid_loops": [],
        },
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


class TestTemplateList:
    """Tests for GET /api/v1/templates"""

    def test_list_templates_empty(self, client: TestClient):
        """Test listing templates when none exist."""
        response = client.get("/api/v1/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_list_templates_with_data(
        self, client: TestClient, sample_template: ConfigTemplate
    ):
        """Test listing templates with data."""
        response = client.get("/api/v1/templates")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "Water Treatment Standard"
        assert data["data"][0]["category"] == "water-treatment"

    def test_list_templates_filter_by_category(
        self, client: TestClient, sample_template: ConfigTemplate
    ):
        """Test filtering templates by category."""
        response = client.get("/api/v1/templates?category=water-treatment")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1

        # Non-matching category
        response = client.get("/api/v1/templates?category=hvac")
        data = response.json()
        assert len(data["data"]) == 0


class TestTemplateCreate:
    """Tests for POST /api/v1/templates"""

    def test_create_template(self, client: TestClient):
        """Test creating a new template."""
        response = client.post(
            "/api/v1/templates",
            json={
                "name": "Basic RTU",
                "description": "Basic RTU configuration",
                "category": "general",
                "slot_count": 8,
                "slots": [
                    {"slot_number": 0, "module_type": "analog_input", "module_id": "AI4"},
                ],
                "sensors": [],
                "controls": [],
                "alarms": [],
                "pid_loops": [],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "Basic RTU"
        assert data["data"]["slot_count"] == 8
        assert "id" in data["data"]

    def test_create_template_duplicate_name(
        self, client: TestClient, sample_template: ConfigTemplate
    ):
        """Test creating template with duplicate name fails."""
        response = client.post(
            "/api/v1/templates",
            json={
                "name": sample_template.name,
                "category": "general",
                "slot_count": 8,
                "slots": [],
                "sensors": [],
                "controls": [],
                "alarms": [],
                "pid_loops": [],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestTemplateGet:
    """Tests for GET /api/v1/templates/{id}"""

    def test_get_template(self, client: TestClient, sample_template: ConfigTemplate):
        """Test getting a specific template."""
        response = client.get(f"/api/v1/templates/{sample_template.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == sample_template.id
        assert data["data"]["name"] == "Water Treatment Standard"
        assert len(data["data"]["slots"]) == 2
        assert len(data["data"]["sensors"]) == 1

    def test_get_template_not_found(self, client: TestClient):
        """Test getting non-existent template."""
        response = client.get("/api/v1/templates/99999")

        assert response.status_code == 404


class TestTemplateDelete:
    """Tests for DELETE /api/v1/templates/{id}"""

    def test_delete_template(self, client: TestClient, sample_template: ConfigTemplate):
        """Test deleting a template."""
        response = client.delete(f"/api/v1/templates/{sample_template.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["deleted"] is True

        # Verify deleted
        response = client.get(f"/api/v1/templates/{sample_template.id}")
        assert response.status_code == 404


class TestTemplateApply:
    """Tests for POST /api/v1/templates/{id}/apply/{rtu_name}"""

    def test_apply_template(
        self,
        client: TestClient,
        sample_template: ConfigTemplate,
        running_rtu: RTU,
        db_session: Session,
    ):
        """Test applying a template to an RTU."""
        response = client.post(
            f"/api/v1/templates/{sample_template.id}/apply/{running_rtu.station_name}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["template_id"] == sample_template.id
        assert data["data"]["rtu"] == running_rtu.station_name
        assert data["data"]["applied"]["sensors"] == 1
        assert data["data"]["applied"]["controls"] == 1
        assert data["data"]["applied"]["alarms"] == 1

    def test_apply_template_rtu_not_found(
        self, client: TestClient, sample_template: ConfigTemplate
    ):
        """Test applying template to non-existent RTU."""
        response = client.post(
            f"/api/v1/templates/{sample_template.id}/apply/nonexistent-rtu"
        )

        assert response.status_code == 404

    def test_apply_template_not_found(self, client: TestClient, running_rtu: RTU):
        """Test applying non-existent template."""
        response = client.post(f"/api/v1/templates/99999/apply/{running_rtu.station_name}")

        assert response.status_code == 404


class TestTemplateFromRtu:
    """Tests for POST /api/v1/templates/from-rtu/{rtu_name}"""

    def test_create_template_from_rtu(
        self, client: TestClient, running_rtu: RTU, db_session: Session
    ):
        """Test creating a template from an RTU configuration."""
        # Add some configuration to the RTU first
        slot = db_session.query(Slot).filter(
            Slot.rtu_id == running_rtu.id, Slot.slot_number == 1
        ).first()

        sensor = Sensor(
            rtu_id=running_rtu.id,
            slot_id=slot.id,
            tag="TEST-SENSOR",
            channel=0,
            sensor_type="temperature",
            unit="degF",
            scale_min=0,
            scale_max=4095,
            eng_min=32.0,
            eng_max=212.0,
        )
        db_session.add(sensor)
        db_session.commit()

        response = client.post(
            f"/api/v1/templates/from-rtu/{running_rtu.station_name}",
            params={"name": "Captured Template", "category": "custom"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Captured Template"
        assert data["data"]["category"] == "custom"
        assert len(data["data"]["sensors"]) >= 1
        assert data["data"]["vendor_id"] == running_rtu.vendor_id

    def test_create_template_from_rtu_default_name(
        self, client: TestClient, running_rtu: RTU
    ):
        """Test creating template from RTU with auto-generated name."""
        response = client.post(f"/api/v1/templates/from-rtu/{running_rtu.station_name}")

        assert response.status_code == 200
        data = response.json()
        assert running_rtu.station_name in data["data"]["name"]

    def test_create_template_from_rtu_not_found(self, client: TestClient):
        """Test creating template from non-existent RTU."""
        response = client.post("/api/v1/templates/from-rtu/nonexistent-rtu")

        assert response.status_code == 404
