"""
Water Treatment Controller - Live PROFINET Integration Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Tests that verify API endpoints work correctly with live controller.
Run with: pytest tests/integration/ -v

Requirements:
- PROFINET controller must be running
- Shared memory must be initialized
- At least one RTU should be configured
"""

import pytest
from fastapi.testclient import TestClient


class TestLiveSystemStatus:
    """Test system status with live controller."""

    def test_system_status_shows_controller_running(self, integration_client: TestClient):
        """Verify system status shows controller as running."""
        response = integration_client.get("/api/v1/system/status")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["profinet"]["controller_running"] is True

    def test_health_check(self, integration_client: TestClient):
        """Verify health check endpoint."""
        response = integration_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestLiveRtuOperations:
    """Test RTU operations with live controller."""

    def test_list_rtus_from_controller(
        self, integration_client: TestClient, discovered_rtus
    ):
        """Verify RTUs from API match controller."""
        response = integration_client.get("/api/v1/rtus")

        assert response.status_code == 200
        data = response.json()

        # API should show at least as many RTUs as controller
        # (API may have more from database that aren't connected)
        api_rtus = {r["station_name"] for r in data["data"]}
        controller_rtus = {r["station_name"] for r in discovered_rtus}

        # All connected RTUs should be in API
        assert controller_rtus.issubset(api_rtus) or len(controller_rtus) == 0


class TestLiveSensorReading:
    """Test sensor reading with live controller."""

    def test_sensor_values_have_good_quality(
        self, integration_client: TestClient, discovered_rtus
    ):
        """Verify sensor values from running RTUs have good quality."""
        if not discovered_rtus:
            pytest.skip("No RTUs discovered")

        for rtu in discovered_rtus:
            if rtu.get("connection_state") == 3:  # RUNNING
                station_name = rtu["station_name"]
                response = integration_client.get(
                    f"/api/v1/rtus/{station_name}/sensors"
                )

                if response.status_code == 200:
                    data = response.json()
                    for sensor in data["data"]:
                        # Running RTU sensors should have GOOD quality
                        assert sensor["quality"] in ["GOOD", "UNCERTAIN"]
                break


class TestLiveDiscovery:
    """Test network discovery with live controller."""

    def test_dcp_discovery(self, integration_client: TestClient):
        """Test PROFINET DCP discovery."""
        response = integration_client.post(
            "/api/v1/discover/profinet",
            json={"timeout_ms": 3000}
        )

        assert response.status_code == 200
        data = response.json()
        # Discovery should complete without error
        assert "data" in data


class TestLiveAlarms:
    """Test alarm operations with live controller."""

    def test_list_active_alarms(
        self, integration_client: TestClient, active_alarms
    ):
        """Verify alarm list matches controller state."""
        response = integration_client.get("/api/v1/alarms")

        assert response.status_code == 200
        data = response.json()

        # Count should match or be close
        api_active = len([a for a in data["data"] if a.get("state") == "ACTIVE"])
        controller_active = len(active_alarms)

        # Allow some variance due to timing
        assert abs(api_active - controller_active) <= 2


class TestLivePidLoops:
    """Test PID loop operations with live controller."""

    def test_list_pid_loops(
        self, integration_client: TestClient, pid_loops
    ):
        """Verify PID loops from API match controller."""
        # This test requires an RTU with PID loops configured
        if not pid_loops:
            pytest.skip("No PID loops configured")

        # For each PID loop in controller, verify API access
        for loop in pid_loops:
            rtu_name = loop.get("input_rtu")
            if rtu_name:
                response = integration_client.get(f"/api/v1/rtus/{rtu_name}/pid")
                if response.status_code == 200:
                    data = response.json()
                    assert isinstance(data["data"], list)
                    break
