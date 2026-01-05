#!/usr/bin/env python3
"""
Shared fixtures for integration tests.

This module provides common fixtures used across integration test modules.
"""

import os
import pytest
import subprocess
import tempfile
from pathlib import Path

# Configuration
API_BASE_URL = os.environ.get(
    "API_BASE_URL",
    f"http://localhost:{os.environ.get('WTC_API_PORT', '8000')}"
)
MODBUS_HOST = os.environ.get("MODBUS_HOST", "localhost")
MODBUS_PORT = int(os.environ.get("WTC_MODBUS_TCP_PORT", "1502"))


# =============================================================================
# Docker Compose Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def docker_compose():
    """Start docker compose for test session."""
    project_root = Path(__file__).parent.parent.parent
    compose_file = project_root / "docker" / "docker-compose.yml"

    if not compose_file.exists():
        pytest.skip("docker-compose.yml not found")

    # Check if Docker is available
    result = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        pytest.skip("Docker Compose not available")

    # Start containers
    start_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        cwd=project_root,
        capture_output=True,
        text=True
    )

    if start_result.returncode != 0:
        pytest.skip(f"Failed to start containers: {start_result.stderr}")

    # Wait for health
    import time
    time.sleep(10)  # Give containers time to start

    yield {
        "project_root": project_root,
        "compose_file": compose_file,
    }

    # Cleanup
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "down", "-v"],
        cwd=project_root,
        capture_output=True
    )


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def v1_db(temp_db_path):
    """Create a v1 schema database for migration testing."""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{temp_db_path}")

        # Create v1-style schema
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE rtus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_name VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45),
                    state VARCHAR(50) DEFAULT 'OFFLINE'
                )
            """))
            conn.execute(text("""
                CREATE TABLE sensors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rtu_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    FOREIGN KEY (rtu_id) REFERENCES rtus(id)
                )
            """))
            conn.commit()

        yield temp_db_path

    except ImportError:
        pytest.skip("SQLAlchemy not available")


# =============================================================================
# HTTP Client Fixtures
# =============================================================================

@pytest.fixture
def api_client():
    """Create HTTP client for API tests."""
    try:
        import httpx
        client = httpx.Client(base_url=API_BASE_URL, timeout=10.0)
        yield client
        client.close()
    except ImportError:
        pytest.skip("httpx not available")


@pytest.fixture
def authenticated_client():
    """Create authenticated HTTP client."""
    try:
        import httpx
        client = httpx.Client(base_url=API_BASE_URL, timeout=10.0)

        # Try to authenticate
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"}
        )

        if response.status_code == 200:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            if token:
                client.headers["Authorization"] = f"Bearer {token}"

        yield client
        client.close()

    except ImportError:
        pytest.skip("httpx not available")


# =============================================================================
# Modbus Fixtures
# =============================================================================

@pytest.fixture
def modbus_client():
    """Create Modbus client for read-only tests."""
    try:
        from pymodbus.client import ModbusTcpClient

        client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
        if not client.connect():
            pytest.skip(f"Cannot connect to Modbus at {MODBUS_HOST}:{MODBUS_PORT}")

        yield client
        client.close()

    except ImportError:
        pytest.skip("pymodbus not available")


# =============================================================================
# IPC Fixtures
# =============================================================================

@pytest.fixture
def ipc_shm_name():
    """Generate unique shared memory name for tests."""
    import uuid
    return f"/wtc_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ipc_sem_name():
    """Generate unique semaphore name for tests."""
    import uuid
    return f"/wtc_sem_{uuid.uuid4().hex[:8]}"


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_rtu():
    """Sample RTU configuration."""
    return {
        "station_name": "TestRTU001",
        "ip_address": "192.168.1.100",
        "mac_address": "00:11:22:33:44:55",
        "state": "OFFLINE",
    }


@pytest.fixture
def sample_sensor():
    """Sample sensor configuration."""
    return {
        "name": "pH_Sensor_1",
        "sensor_type": "pH",
        "unit": "pH",
        "slot": 1,
        "subslot": 1,
    }


@pytest.fixture
def sample_alarm():
    """Sample alarm data."""
    return {
        "alarm_id": "ALM001",
        "severity": "HIGH",
        "state": "ACTIVE",
        "message": "Test alarm",
        "source": "TestRTU001.pH_Sensor_1",
    }


# =============================================================================
# Environment Detection Fixtures
# =============================================================================

@pytest.fixture
def is_ci():
    """Check if running in CI environment."""
    return os.environ.get("CI", "").lower() in ("true", "1", "yes")


@pytest.fixture
def is_docker():
    """Check if running inside Docker."""
    return os.path.exists("/.dockerenv")


@pytest.fixture
def deployment_mode():
    """Detect deployment mode."""
    if os.path.exists("/.dockerenv"):
        return "docker"
    elif os.environ.get("DEPLOYMENT_MODE"):
        return os.environ["DEPLOYMENT_MODE"]
    else:
        return "baremetal"


# =============================================================================
# Pytest Hooks
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "bare_metal: tests for bare-metal deployment")
    config.addinivalue_line("markers", "docker: tests for Docker deployment")
    config.addinivalue_line("markers", "slow: slow-running tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
