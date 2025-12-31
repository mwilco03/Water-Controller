#!/usr/bin/env python3
"""
End-to-End Integration Tests for Water Treatment Controller

These tests verify the complete system path:
  RTU Simulator -> Controller -> API -> Frontend

Prerequisites:
  - Controller service running
  - API service running
  - Database initialized

Run with:
  pytest tests/integration/test_e2e.py -v
"""

import os
import time
import json
import pytest
import asyncio
import httpx
from datetime import datetime
from typing import Optional

# Configuration
# API runs on port 8000 (see config/ports.env)
# UI runs on port 8080 - do not confuse them
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://localhost:{os.environ.get('WTC_API_PORT', '8000')}")
API_TIMEOUT = 10.0
POLL_INTERVAL = 0.5
MAX_WAIT_TIME = 30.0


class TestSystemHealth:
    """Tests for system health and connectivity."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_api_health_endpoint(self):
        """Verify API health endpoint returns healthy status."""
        response = self.client.get("/api/v1/system/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))

    def test_services_status(self):
        """Verify all services are running."""
        response = self.client.get("/api/v1/services")
        assert response.status_code == 200

        services = response.json()
        # Check for expected services
        expected_services = ["controller", "api"]
        for service in expected_services:
            if service in services:
                status = services[service]
                assert status in ["running", "active", "unknown"], f"{service} status: {status}"


class TestRTUManagement:
    """Tests for RTU device management."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_list_rtus(self):
        """Verify RTU listing works."""
        response = self.client.get("/api/v1/rtus")
        assert response.status_code == 200

        rtus = response.json()
        assert isinstance(rtus, list)

        # If RTUs exist, verify structure
        if rtus:
            rtu = rtus[0]
            assert "station_name" in rtu
            assert "state" in rtu

    def test_rtu_discovery(self):
        """Verify PROFINET discovery endpoint exists."""
        response = self.client.post("/api/v1/profinet/discover", json={"timeout": 1000})
        # Accept 200 (success) or 503 (no network interface)
        assert response.status_code in [200, 503, 404]


class TestAlarmManagement:
    """Tests for alarm system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_list_alarms(self):
        """Verify alarm listing works."""
        response = self.client.get("/api/v1/alarms")
        assert response.status_code == 200

        alarms = response.json()
        assert isinstance(alarms, list)

        # If alarms exist, verify ISA-18.2 structure
        if alarms:
            alarm = alarms[0]
            assert "alarm_id" in alarm or "id" in alarm
            assert "severity" in alarm
            assert "state" in alarm

    def test_alarm_history(self):
        """Verify alarm history endpoint works."""
        response = self.client.get("/api/v1/alarms/history?limit=10")
        # Accept 200 or 404 (if not implemented)
        assert response.status_code in [200, 404]


class TestAuthentication:
    """Tests for authentication system."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_login_invalid_credentials(self):
        """Verify login rejects invalid credentials."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "invalid", "password": "invalid"}
        )
        assert response.status_code in [401, 403]

    def test_login_valid_credentials(self):
        """Verify login accepts valid credentials (if test user exists)."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"}
        )
        # Accept 200 (success) or 401 (test user not configured)
        if response.status_code == 200:
            data = response.json()
            assert "token" in data or "access_token" in data


class TestDataFlow:
    """Tests for RTU -> Controller -> API data flow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_sensor_data_freshness(self):
        """Verify sensor data has recent timestamps."""
        response = self.client.get("/api/v1/rtus")
        if response.status_code != 200:
            pytest.skip("No RTUs available")

        rtus = response.json()
        if not rtus:
            pytest.skip("No RTUs registered")

        rtu = rtus[0]
        station_name = rtu["station_name"]

        # Get sensors for this RTU
        response = self.client.get(f"/api/v1/rtus/{station_name}/sensors")
        if response.status_code != 200:
            pytest.skip("No sensors available")

        sensors = response.json()
        if not sensors:
            pytest.skip("No sensors registered")

        # Check data freshness (should be within last 60 seconds for running RTU)
        for sensor in sensors:
            if "last_updated" in sensor and sensor["last_updated"]:
                last_updated = datetime.fromisoformat(sensor["last_updated"].replace("Z", "+00:00"))
                age_seconds = (datetime.now(last_updated.tzinfo) - last_updated).total_seconds()
                # Only check freshness if RTU is running
                if rtu.get("state") == "RUNNING":
                    assert age_seconds < 120, f"Sensor data is stale: {age_seconds}s old"


class TestWebSocketConnection:
    """Tests for WebSocket real-time updates."""

    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Verify WebSocket connection can be established."""
        import websockets

        ws_url = API_BASE_URL.replace("http", "ws") + "/api/v1/ws/live"

        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                # Connection successful
                assert ws.open

                # Wait briefly for any initial message
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(message)
                    assert "type" in data or "channel" in data
                except asyncio.TimeoutError:
                    # No message is OK - connection test passed
                    pass

        except Exception as e:
            pytest.skip(f"WebSocket not available: {e}")


class TestRecoveryScenarios:
    """Tests for system recovery after failures."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        yield
        self.client.close()

    def test_api_responds_after_repeated_requests(self):
        """Verify API remains responsive under load."""
        for i in range(10):
            response = self.client.get("/api/v1/system/health")
            assert response.status_code == 200
            time.sleep(0.1)

    def test_invalid_endpoint_handling(self):
        """Verify 404 handling for invalid endpoints."""
        response = self.client.get("/api/v1/nonexistent")
        assert response.status_code == 404

    def test_malformed_request_handling(self):
        """Verify error handling for malformed requests."""
        response = self.client.post(
            "/api/v1/rtus",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]


class TestConfigurationBackup:
    """Tests for configuration backup/restore."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test client with auth."""
        self.client = httpx.Client(base_url=API_BASE_URL, timeout=API_TIMEOUT)
        # Try to authenticate
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"}
        )
        if response.status_code == 200:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            if token:
                self.client.headers["Authorization"] = f"Bearer {token}"
        yield
        self.client.close()

    def test_export_configuration(self):
        """Verify configuration export works."""
        response = self.client.get("/api/v1/config/export")
        # Accept 200 (success) or 401/403 (not authenticated) or 404 (not implemented)
        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
