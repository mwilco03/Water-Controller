"""
Water Treatment Controller - Backup/Restore Endpoint Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.rtu import RTU


class TestBackupCreate:
    """Tests for POST /api/v1/system/backup"""

    def test_create_backup_empty(self, client: TestClient):
        """Test creating backup with no RTUs."""
        response = client.post("/api/v1/system")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

        # Verify ZIP contents
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer) as zf:
            assert "config.json" in zf.namelist()
            assert "metadata.json" in zf.namelist()

            config = json.loads(zf.read("config.json"))
            assert config["version"] == "2.0.0"
            assert config["rtus"] == []

    def test_create_backup_with_data(self, client: TestClient, running_rtu: RTU):
        """Test creating backup with RTU data."""
        response = client.post("/api/v1/system")

        assert response.status_code == 200

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer) as zf:
            config = json.loads(zf.read("config.json"))
            assert len(config["rtus"]) == 1
            assert config["rtus"][0]["station_name"] == running_rtu.station_name

            metadata = json.loads(zf.read("metadata.json"))
            assert metadata["rtus"] == 1


class TestBackupRestore:
    """Tests for POST /api/v1/system/restore"""

    def _create_backup_file(
        self,
        station_name: str = "TEST-RTU",
        ip_address: str = "192.168.1.100"
    ) -> io.BytesIO:
        """Create a valid backup file for testing."""
        config_data = {
            "version": "2.0.0",
            "created_at": "2024-01-01T00:00:00Z",
            "backup_id": "20240101_000000",
            "rtus": [
                {
                    "station_name": station_name,
                    "ip_address": ip_address,
                    "vendor_id": 0x1234,
                    "device_id": 0x5678,
                    "slot_count": 8,
                    "slots": [
                        {"slot_number": 1, "module_id": "AI8", "module_type": "analog_input"}
                    ],
                    "sensors": [
                        {
                            "tag": "TK-101-LVL",
                            "channel": 0,
                            "sensor_type": "level",
                            "unit": "ft",
                            "scale_min": 0,
                            "scale_max": 4095,
                            "eng_min": 0.0,
                            "eng_max": 20.0,
                        }
                    ],
                    "controls": [],
                    "alarms": [],
                    "pid_loops": [],
                }
            ],
        }

        metadata = {
            "id": "20240101_000000",
            "created_at": "2024-01-01T00:00:00Z",
            "version": "2.0.0",
            "rtus": 1,
            "sensors": 1,
            "controls": 0,
            "alarms": 0,
            "pid_loops": 0,
        }

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("config.json", json.dumps(config_data))
            zf.writestr("metadata.json", json.dumps(metadata))

        zip_buffer.seek(0)
        return zip_buffer

    def test_restore_backup(self, client: TestClient, db_session: Session):
        """Test restoring from backup file."""
        backup_file = self._create_backup_file()

        response = client.post(
            "/api/v1/system/restore",
            files={"file": ("backup.zip", backup_file, "application/zip")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["restored"]["rtus"] == 1
        assert data["data"]["restored"]["sensors"] == 1

        # Verify RTU was created
        rtu = db_session.query(RTU).filter(RTU.station_name == "TEST-RTU").first()
        assert rtu is not None
        assert rtu.ip_address == "192.168.1.100"

    def test_restore_backup_replace_mode(
        self,
        client: TestClient,
        db_session: Session,
        running_rtu: RTU
    ):
        """Test restore replaces existing RTU by default."""
        # Create backup with same station name
        backup_file = self._create_backup_file(
            station_name=running_rtu.station_name,
            ip_address="10.0.0.99"
        )

        response = client.post(
            "/api/v1/system/restore",
            files={"file": ("backup.zip", backup_file, "application/zip")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is True

        # Verify RTU was replaced
        db_session.expire_all()
        rtu = db_session.query(RTU).filter(
            RTU.station_name == running_rtu.station_name
        ).first()
        assert rtu.ip_address == "10.0.0.99"

    def test_restore_backup_merge_mode(
        self,
        client: TestClient,
        db_session: Session,
        running_rtu: RTU
    ):
        """Test restore in merge mode skips existing RTUs."""
        original_ip = running_rtu.ip_address

        # Create backup with same station name
        backup_file = self._create_backup_file(
            station_name=running_rtu.station_name,
            ip_address="10.0.0.99"
        )

        response = client.post(
            "/api/v1/system/restore",
            params={"merge": "true"},
            files={"file": ("backup.zip", backup_file, "application/zip")}
        )

        assert response.status_code == 200

        # Verify RTU was not replaced
        db_session.expire_all()
        rtu = db_session.query(RTU).filter(
            RTU.station_name == running_rtu.station_name
        ).first()
        assert rtu.ip_address == original_ip

    def test_restore_invalid_file(self, client: TestClient):
        """Test restore with invalid file."""
        invalid_file = io.BytesIO(b"not a zip file")

        response = client.post(
            "/api/v1/system/restore",
            files={"file": ("backup.zip", invalid_file, "application/zip")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is False
        assert "Invalid backup file" in data["data"]["error"]

    def test_restore_incompatible_version(self, client: TestClient):
        """Test restore with incompatible backup version."""
        config_data = {"version": "1.0.0", "rtus": []}

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("config.json", json.dumps(config_data))
        zip_buffer.seek(0)

        response = client.post(
            "/api/v1/system/restore",
            files={"file": ("backup.zip", zip_buffer, "application/zip")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["success"] is False
        assert "Incompatible backup version" in data["data"]["error"]
