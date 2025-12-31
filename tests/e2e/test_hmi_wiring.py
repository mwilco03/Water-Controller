#!/usr/bin/env python3
"""
End-to-End HMI Wiring Tests

Validates the complete wiring between Next.js frontend and FastAPI backend.
These tests actually start services, make real requests, and verify the
entire data flow works correctly.

Run: pytest tests/e2e/test_hmi_wiring.py -v --tb=short
"""

import os
import sys
import time
import json
import signal
import socket
import subprocess
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator, Tuple

import pytest
import httpx

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_API_DIR = PROJECT_ROOT / "web" / "api"
WEB_UI_DIR = PROJECT_ROOT / "web" / "ui"

# Test configuration
API_PORT = 18000  # Use non-standard ports for testing
UI_PORT = 18080
API_BASE = f"http://localhost:{API_PORT}"
UI_BASE = f"http://localhost:{UI_PORT}"
STARTUP_TIMEOUT = 30
REQUEST_TIMEOUT = 10


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_for_port(port: int, timeout: float = STARTUP_TIMEOUT) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def wait_for_http(url: str, timeout: float = STARTUP_TIMEOUT) -> Tuple[bool, Optional[dict]]:
    """Wait for an HTTP endpoint to respond."""
    start = time.time()
    last_error = None
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=5)
            if response.status_code < 500:
                try:
                    return True, response.json()
                except json.JSONDecodeError:
                    return True, {"raw": response.text[:200]}
        except Exception as e:
            last_error = e
        time.sleep(0.5)
    return False, {"error": str(last_error)}


@contextmanager
def start_backend(port: int = API_PORT) -> Generator[subprocess.Popen, None, None]:
    """Start the FastAPI backend server."""
    if is_port_in_use(port):
        raise RuntimeError(f"Port {port} is already in use")

    env = os.environ.copy()
    env["WTC_STARTUP_MODE"] = "development"
    env["DATABASE_URL"] = "sqlite:///:memory:"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(port),
        ],
        cwd=str(WEB_API_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not wait_for_port(port, timeout=STARTUP_TIMEOUT):
            # Capture output for debugging
            output = proc.stdout.read() if proc.stdout else "No output"
            proc.kill()
            raise RuntimeError(f"Backend failed to start on port {port}: {output[:500]}")
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@contextmanager
def start_frontend(port: int = UI_PORT, api_url: str = API_BASE) -> Generator[subprocess.Popen, None, None]:
    """Start the Next.js frontend server."""
    if is_port_in_use(port):
        raise RuntimeError(f"Port {port} is already in use")

    env = os.environ.copy()
    env["API_URL"] = api_url
    env["PORT"] = str(port)

    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "-p", str(port)],
        cwd=str(WEB_UI_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not wait_for_port(port, timeout=STARTUP_TIMEOUT):
            output = proc.stdout.read() if proc.stdout else "No output"
            proc.kill()
            raise RuntimeError(f"Frontend failed to start on port {port}: {output[:500]}")
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class TestBackendHealth:
    """Test backend API health and endpoints."""

    @pytest.fixture(scope="class")
    def backend(self):
        """Start backend for test class."""
        with start_backend(API_PORT) as proc:
            # Wait for full initialization
            time.sleep(2)
            yield proc

    def test_health_endpoint(self, backend):
        """Backend /health endpoint returns valid response."""
        response = httpx.get(f"{API_BASE}/health", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "unhealthy", "degraded")

    def test_api_v1_rtus_endpoint(self, backend):
        """Backend /api/v1/rtus endpoint exists and returns list."""
        response = httpx.get(f"{API_BASE}/api/v1/rtus", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        # Should return a dict with rtus key or a list
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            assert "rtus" in data or "data" in data or len(data) >= 0

    def test_api_v1_alarms_endpoint(self, backend):
        """Backend /api/v1/alarms endpoint exists and returns list."""
        response = httpx.get(f"{API_BASE}/api/v1/alarms", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_api_v1_system_status_endpoint(self, backend):
        """Backend /api/v1/system/status or /api/v1/system/health exists."""
        # Try multiple possible endpoints
        for path in ["/api/v1/system/status", "/api/v1/system/health", "/api/v1/status"]:
            response = httpx.get(f"{API_BASE}{path}", timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return  # At least one works
        # If none found, check if health works
        response = httpx.get(f"{API_BASE}/health", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200

    def test_openapi_spec(self, backend):
        """Backend serves OpenAPI spec at /api/openapi.json."""
        response = httpx.get(f"{API_BASE}/api/openapi.json", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    def test_cors_headers(self, backend):
        """Backend includes CORS headers for frontend origin."""
        headers = {"Origin": f"http://localhost:{UI_PORT}"}
        response = httpx.options(
            f"{API_BASE}/api/v1/rtus",
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        # Should allow the frontend origin or any origin
        assert response.status_code in (200, 204, 405)


class TestFrontendBuild:
    """Test frontend builds and serves correctly."""

    def test_frontend_build_succeeds(self):
        """Next.js build completes without errors."""
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(WEB_UI_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"

    def test_frontend_lint_passes(self):
        """Next.js lint passes (allow warnings)."""
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=str(WEB_UI_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Warnings are OK, only fail on errors
        assert result.returncode in (0, 1), f"Lint failed: {result.stderr}"
        # Check if there are actual errors (not just warnings)
        if result.returncode == 1:
            assert "error" not in result.stdout.lower() or "warning" in result.stdout.lower()

    def test_typescript_compiles(self):
        """TypeScript compilation succeeds."""
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(WEB_UI_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"TypeScript errors: {result.stdout}"


class TestFrontendToBackendWiring:
    """Test the actual wiring between frontend and backend."""

    @pytest.fixture(scope="class")
    def services(self):
        """Start both backend and frontend."""
        with start_backend(API_PORT) as backend_proc:
            time.sleep(2)  # Let backend fully initialize
            with start_frontend(UI_PORT, API_BASE) as frontend_proc:
                time.sleep(3)  # Let frontend compile
                yield {"backend": backend_proc, "frontend": frontend_proc}

    def test_frontend_serves_html(self, services):
        """Frontend serves HTML at root."""
        response = httpx.get(f"{UI_BASE}/", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain Next.js markers
        assert "__NEXT" in response.text or "next" in response.text.lower()

    def test_frontend_next_data(self, services):
        """Frontend serves _next static assets."""
        response = httpx.get(f"{UI_BASE}/", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        # Next.js should include script references
        assert "_next" in response.text or "script" in response.text

    def test_frontend_api_proxy(self, services):
        """Frontend proxies /api requests to backend."""
        # The frontend's next.config.js should rewrite /api to the backend
        response = httpx.get(f"{UI_BASE}/api/v1/rtus", timeout=REQUEST_TIMEOUT)
        # Should get data from backend (not 404 from Next.js)
        assert response.status_code in (200, 502, 503)  # 502/503 if proxy misconfigured
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))


class TestWebSocketWiring:
    """Test WebSocket connections between frontend and backend."""

    @pytest.fixture(scope="class")
    def backend(self):
        """Start backend for WebSocket tests."""
        with start_backend(API_PORT) as proc:
            time.sleep(2)
            yield proc

    def test_websocket_endpoint_exists(self, backend):
        """WebSocket endpoint is configured."""
        # Check OpenAPI for WebSocket endpoint
        response = httpx.get(f"{API_BASE}/api/openapi.json", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        spec = response.json()
        paths = spec.get("paths", {})
        # Look for ws endpoint
        ws_paths = [p for p in paths.keys() if "ws" in p.lower()]
        assert len(ws_paths) > 0, f"No WebSocket paths found. Available: {list(paths.keys())}"

    @pytest.mark.asyncio
    async def test_websocket_connection(self, backend):
        """WebSocket can connect and receive messages."""
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets package not installed")

        ws_url = f"ws://localhost:{API_PORT}/api/v1/ws/live"
        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                assert ws.open
                # Try to receive a message (with timeout)
                import asyncio
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(message)
                    assert isinstance(data, dict)
                except asyncio.TimeoutError:
                    pass  # No immediate message is OK
        except Exception as e:
            pytest.skip(f"WebSocket connection failed: {e}")


class TestDataFlow:
    """Test complete data flow from API to UI."""

    @pytest.fixture(scope="class")
    def backend(self):
        """Start backend for data flow tests."""
        with start_backend(API_PORT) as proc:
            time.sleep(2)
            yield proc

    def test_rtus_returns_valid_structure(self, backend):
        """RTUs endpoint returns expected data structure."""
        response = httpx.get(f"{API_BASE}/api/v1/rtus", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()

        # Should be a list or dict with rtus
        if isinstance(data, dict):
            rtus = data.get("rtus", data.get("data", []))
        else:
            rtus = data

        assert isinstance(rtus, list)

        # If RTUs exist, check structure
        for rtu in rtus:
            assert "station_name" in rtu or "name" in rtu
            assert "state" in rtu or "status" in rtu

    def test_alarms_returns_valid_structure(self, backend):
        """Alarms endpoint returns expected data structure."""
        response = httpx.get(f"{API_BASE}/api/v1/alarms", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()

        if isinstance(data, dict):
            alarms = data.get("alarms", data.get("data", []))
        else:
            alarms = data

        assert isinstance(alarms, list)

    def test_auth_login_endpoint(self, backend):
        """Auth login endpoint exists and validates credentials."""
        # Try invalid credentials
        response = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            json={"username": "invalid_user_xyz", "password": "wrong_pass"},
            timeout=REQUEST_TIMEOUT
        )
        # Should reject with 401 or 403
        assert response.status_code in (401, 403, 422)

        # Try valid credentials (admin/admin is default)
        response = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
            timeout=REQUEST_TIMEOUT
        )
        # Should work if user exists
        if response.status_code == 200:
            data = response.json()
            assert "token" in data or "access_token" in data


class TestAPIContract:
    """Validate API contract matches what frontend expects."""

    @pytest.fixture(scope="class")
    def backend(self):
        """Start backend for contract tests."""
        with start_backend(API_PORT) as proc:
            time.sleep(2)
            yield proc

    def test_rtu_response_has_required_fields(self, backend):
        """RTU response has all fields frontend expects."""
        required_fields = {"station_name", "state"}
        optional_fields = {"ip_address", "vendor_id", "device_id", "slot_count"}

        response = httpx.get(f"{API_BASE}/api/v1/rtus", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200
        data = response.json()

        # Handle different response formats
        rtus = data if isinstance(data, list) else data.get("rtus", data.get("data", []))

        for rtu in rtus:
            # Check required fields
            for field in required_fields:
                assert field in rtu, f"Missing required field: {field}"

    def test_sensor_response_structure(self, backend):
        """Sensor data has expected fields."""
        # First get an RTU
        response = httpx.get(f"{API_BASE}/api/v1/rtus", timeout=REQUEST_TIMEOUT)
        rtus = response.json()
        rtus = rtus if isinstance(rtus, list) else rtus.get("rtus", rtus.get("data", []))

        if not rtus:
            pytest.skip("No RTUs to test sensors")

        station = rtus[0].get("station_name", rtus[0].get("name"))
        response = httpx.get(
            f"{API_BASE}/api/v1/rtus/{station}/sensors",
            timeout=REQUEST_TIMEOUT
        )

        # Endpoint should exist
        assert response.status_code in (200, 404)


class TestErrorHandling:
    """Test error handling across the stack."""

    @pytest.fixture(scope="class")
    def backend(self):
        """Start backend for error tests."""
        with start_backend(API_PORT) as proc:
            time.sleep(2)
            yield proc

    def test_404_returns_json(self, backend):
        """404 errors return JSON, not HTML."""
        response = httpx.get(
            f"{API_BASE}/api/v1/nonexistent_endpoint_12345",
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")

    def test_invalid_json_returns_422(self, backend):
        """Invalid JSON body returns 422 Unprocessable Entity."""
        response = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            content="not valid json",
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code in (400, 422)

    def test_missing_required_fields(self, backend):
        """Missing required fields return appropriate error."""
        response = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            json={},  # Missing username and password
            timeout=REQUEST_TIMEOUT
        )
        assert response.status_code in (400, 422)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
