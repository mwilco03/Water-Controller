"""
Water Treatment Controller - PID Endpoint Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.rtu import RTU, Sensor, Control, Slot
from app.models.pid import PidLoop, PidMode


@pytest.fixture
def sample_sensor(db_session: Session, running_rtu: RTU) -> Sensor:
    """Create a sample sensor for PID testing."""
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
        range_min=0.0,
        range_max=20.0,
    )
    db_session.add(sensor)
    db_session.commit()
    db_session.refresh(sensor)
    return sensor


@pytest.fixture
def sample_control(db_session: Session, running_rtu: RTU) -> Control:
    """Create a sample control for PID testing."""
    slot = db_session.query(Slot).filter(
        Slot.rtu_id == running_rtu.id,
        Slot.slot_number == 1
    ).first()

    control = Control(
        rtu_id=running_rtu.id,
        slot_id=slot.id,
        tag="VLV-101",
        channel=0,
        control_type="analog",
        equipment_type="valve",
    )
    db_session.add(control)
    db_session.commit()
    db_session.refresh(control)
    return control


@pytest.fixture
def sample_pid_loop(
    db_session: Session,
    running_rtu: RTU,
    sample_sensor: Sensor,
    sample_control: Control
) -> PidLoop:
    """Create a sample PID loop for testing."""
    loop = PidLoop(
        rtu_id=running_rtu.id,
        name="Tank Level Control",
        pv_sensor_tag=sample_sensor.tag,
        cv_control_tag=sample_control.tag,
        setpoint=10.0,
        kp=1.5,
        ki=0.1,
        kd=0.05,
        output_min=0.0,
        output_max=100.0,
        mode=PidMode.AUTO,
        enabled=True,
    )
    db_session.add(loop)
    db_session.commit()
    db_session.refresh(loop)
    return loop


class TestPidLoopList:
    """Tests for GET /api/v1/rtus/{name}/pid"""

    def test_list_pid_loops_empty(self, client: TestClient, running_rtu: RTU):
        """Test listing PID loops when none exist."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/pid")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []

    def test_list_pid_loops_with_data(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test listing PID loops with data."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/pid")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["name"] == "Tank Level Control"
        assert data["data"][0]["setpoint"] == 10.0
        assert data["data"][0]["mode"] == "AUTO"


class TestPidLoopCreate:
    """Tests for POST /api/v1/rtus/{name}/pid"""

    def test_create_pid_loop(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_sensor: Sensor,
        sample_control: Control
    ):
        """Test creating a new PID loop."""
        response = client.post(
            f"/api/v1/rtus/{running_rtu.station_name}/pid",
            json={
                "name": "Pressure Control",
                "process_variable": sample_sensor.tag,
                "control_output": sample_control.tag,
                "setpoint": 50.0,
                "kp": 2.0,
                "ki": 0.5,
                "kd": 0.1,
                "output_min": 0.0,
                "output_max": 100.0,
                "mode": "AUTO",
                "enabled": True,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "Pressure Control"
        assert data["data"]["setpoint"] == 50.0
        assert "id" in data["data"]

    def test_create_pid_loop_invalid_sensor(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_control: Control
    ):
        """Test creating PID loop with invalid sensor tag."""
        response = client.post(
            f"/api/v1/rtus/{running_rtu.station_name}/pid",
            json={
                "name": "Bad Loop",
                "process_variable": "NONEXISTENT",
                "control_output": sample_control.tag,
                "setpoint": 50.0,
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestPidLoopGet:
    """Tests for GET /api/v1/rtus/{name}/pid/{loop_id}"""

    def test_get_pid_loop(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test getting a specific PID loop."""
        response = client.get(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == sample_pid_loop.id
        assert data["data"]["name"] == "Tank Level Control"

    def test_get_pid_loop_not_found(self, client: TestClient, running_rtu: RTU):
        """Test getting non-existent PID loop."""
        response = client.get(f"/api/v1/rtus/{running_rtu.station_name}/pid/99999")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "PID_LOOP_NOT_FOUND"


class TestPidLoopUpdate:
    """Tests for PUT /api/v1/rtus/{name}/pid/{loop_id}"""

    def test_update_pid_loop(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test updating a PID loop."""
        response = client.put(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}",
            json={
                "name": "Updated Loop Name",
                "setpoint": 15.0,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["updated"] is True


class TestPidLoopDelete:
    """Tests for DELETE /api/v1/rtus/{name}/pid/{loop_id}"""

    def test_delete_pid_loop(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test deleting a PID loop."""
        response = client.delete(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["deleted"] is True


class TestSetpointUpdate:
    """Tests for PUT /api/v1/rtus/{name}/pid/{loop_id}/setpoint"""

    def test_update_setpoint(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test updating PID setpoint."""
        response = client.put(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}/setpoint",
            json={"setpoint": 12.5}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["old_setpoint"] == 10.0
        assert data["data"]["new_setpoint"] == 12.5


class TestTuningUpdate:
    """Tests for PUT /api/v1/rtus/{name}/pid/{loop_id}/tuning"""

    def test_update_tuning(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test updating PID tuning parameters."""
        response = client.put(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}/tuning",
            json={"kp": 2.0, "ki": 0.2, "kd": 0.1}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["old_tuning"]["kp"] == 1.5
        assert data["data"]["new_tuning"]["kp"] == 2.0


class TestModeUpdate:
    """Tests for PUT /api/v1/rtus/{name}/pid/{loop_id}/mode"""

    def test_update_mode(
        self,
        client: TestClient,
        running_rtu: RTU,
        sample_pid_loop: PidLoop
    ):
        """Test updating PID mode."""
        response = client.put(
            f"/api/v1/rtus/{running_rtu.station_name}/pid/{sample_pid_loop.id}/mode",
            json={"mode": "MANUAL"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["old_mode"] == "AUTO"
        assert data["data"]["new_mode"] == "MANUAL"
