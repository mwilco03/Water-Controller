"""
Water Treatment Controller - Integration Test Configuration
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Fixtures for integration testing with live PROFINET controller.
"""

import os
import sys

import pytest

# Add parent paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from fastapi.testclient import TestClient


def check_controller_running():
    """Check if the PROFINET controller is running."""
    try:
        from shm_client import get_client
        client = get_client()
        return client.is_connected() and client.is_controller_running()
    except Exception:
        return False


# Skip all integration tests if controller not running
pytestmark = pytest.mark.skipif(
    not check_controller_running(),
    reason="PROFINET controller not running"
)


@pytest.fixture(scope="session")
def integration_client():
    """Create test client for integration tests."""
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="session")
def shm_client():
    """Get shared memory client for direct controller access."""
    from shm_client import get_client
    return get_client()


@pytest.fixture
def discovered_rtus(shm_client):
    """Get list of discovered RTUs from controller."""
    return shm_client.get_rtus()


@pytest.fixture
def active_alarms(shm_client):
    """Get list of active alarms from controller."""
    return shm_client.get_alarms()


@pytest.fixture
def pid_loops(shm_client):
    """Get list of PID loops from controller."""
    return shm_client.get_pid_loops()
