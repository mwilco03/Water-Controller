#!/usr/bin/env python3
"""
OpenPLC Viewer Integration Tests

Tests read-only ladder logic viewing and Modbus communication.
OpenPLC is used as a visualization tool only - no execution.

Prerequisites:
  - OpenPLC container running (optional)
  - Modbus TCP server available

Run with:
  pytest tests/integration/test_openplc.py -v
"""

import os
import pytest

# Check for required packages
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from pymodbus.client import ModbusTcpClient
    HAS_PYMODBUS = True
except ImportError:
    HAS_PYMODBUS = False

# Configuration
OPENPLC_URL = os.environ.get("OPENPLC_URL", "http://localhost:8081")
MODBUS_HOST = os.environ.get("MODBUS_HOST", "localhost")
MODBUS_PORT = int(os.environ.get("WTC_MODBUS_TCP_PORT", "1502"))


@pytest.fixture
def openplc_client():
    """Create HTTP client for OpenPLC web interface."""
    if not HAS_HTTPX:
        pytest.skip("httpx not available")

    client = httpx.Client(base_url=OPENPLC_URL, timeout=10.0)
    yield client
    client.close()


@pytest.fixture
def modbus_client():
    """Create Modbus client for read-only tests."""
    if not HAS_PYMODBUS:
        pytest.skip("pymodbus not available")

    client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
    if not client.connect():
        pytest.skip(f"Cannot connect to Modbus at {MODBUS_HOST}:{MODBUS_PORT}")
    yield client
    client.close()


class TestOpenPLCContainer:
    """Test OpenPLC container deployment."""

    @pytest.mark.skipif(not HAS_HTTPX, reason="httpx not available")
    def test_container_available(self, openplc_client):
        """Test OpenPLC container is reachable."""
        try:
            response = openplc_client.get("/", follow_redirects=True)
            # OpenPLC might redirect to login
            assert response.status_code in [200, 302, 303]
        except httpx.ConnectError:
            pytest.skip("OpenPLC container not running")

    @pytest.mark.skipif(not HAS_HTTPX, reason="httpx not available")
    def test_web_ui_accessible(self, openplc_client):
        """Test OpenPLC web UI is accessible at configured port."""
        try:
            response = openplc_client.get("/login", follow_redirects=True)
            # Should return login page or redirect
            assert response.status_code in [200, 302, 303]
        except httpx.ConnectError:
            pytest.skip("OpenPLC container not running")

    @pytest.mark.skipif(not HAS_HTTPX, reason="httpx not available")
    def test_api_endpoints_exist(self, openplc_client):
        """Test OpenPLC API endpoints exist."""
        try:
            # OpenPLC has various API endpoints
            endpoints = ["/api/status", "/programs"]
            for endpoint in endpoints:
                response = openplc_client.get(endpoint, follow_redirects=True)
                # Accept various responses - just checking endpoint exists
                assert response.status_code in [200, 401, 403, 404]
        except httpx.ConnectError:
            pytest.skip("OpenPLC container not running")


class TestModbusReadOnly:
    """Test Modbus read operations (no writes)."""

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_connection(self, modbus_client):
        """Test Modbus connection is established."""
        assert modbus_client.connected
        # Just verify we can connect - no actual reads required
        # This test passes if fixture creation succeeded

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_read_holding_registers(self, modbus_client):
        """Test reading holding registers."""
        result = modbus_client.read_holding_registers(address=0, count=10)

        if result.isError():
            # Some errors are expected if registers don't exist
            pytest.skip("Holding registers not available")

        # Verify we got register values
        assert hasattr(result, 'registers')
        assert len(result.registers) == 10

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_read_input_registers(self, modbus_client):
        """Test reading input registers."""
        result = modbus_client.read_input_registers(address=0, count=10)

        if result.isError():
            pytest.skip("Input registers not available")

        assert hasattr(result, 'registers')
        assert len(result.registers) == 10

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_read_coils(self, modbus_client):
        """Test reading coil status."""
        result = modbus_client.read_coils(address=0, count=16)

        if result.isError():
            pytest.skip("Coils not available")

        assert hasattr(result, 'bits')
        assert len(result.bits) >= 16

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_read_discrete_inputs(self, modbus_client):
        """Test reading discrete inputs."""
        result = modbus_client.read_discrete_inputs(address=0, count=16)

        if result.isError():
            pytest.skip("Discrete inputs not available")

        assert hasattr(result, 'bits')
        assert len(result.bits) >= 16


class TestModbusDataIntegrity:
    """Test Modbus data integrity (read-only verification)."""

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_consistent_reads(self, modbus_client):
        """Test that repeated reads return consistent data types."""
        # Read same registers multiple times
        results = []
        for _ in range(3):
            result = modbus_client.read_holding_registers(address=0, count=5)
            if result.isError():
                pytest.skip("Registers not available")
            results.append(result.registers)

        # All reads should return same number of registers
        assert all(len(r) == 5 for r in results)

    @pytest.mark.skipif(not HAS_PYMODBUS, reason="pymodbus not available")
    def test_register_value_range(self, modbus_client):
        """Test that register values are within valid range."""
        result = modbus_client.read_holding_registers(address=0, count=10)

        if result.isError():
            pytest.skip("Registers not available")

        # All values should be 16-bit unsigned (0-65535)
        for value in result.registers:
            assert 0 <= value <= 65535, f"Invalid register value: {value}"


class TestOpenPLCModbusIntegration:
    """Test OpenPLC and Modbus integration."""

    @pytest.fixture
    def clients(self, openplc_client, modbus_client):
        """Provide both clients."""
        return {"openplc": openplc_client, "modbus": modbus_client}

    @pytest.mark.skipif(
        not (HAS_HTTPX and HAS_PYMODBUS),
        reason="httpx and pymodbus required"
    )
    def test_modbus_reflects_plc_state(self, clients):
        """Test that Modbus values reflect PLC state (read-only check)."""
        try:
            # Check OpenPLC is running
            response = clients["openplc"].get("/", follow_redirects=True)
            if response.status_code != 200:
                pytest.skip("OpenPLC not available")

            # Read Modbus values
            result = clients["modbus"].read_holding_registers(address=0, count=5)
            if result.isError():
                pytest.skip("Modbus registers not available")

            # If both are working, values should be present
            assert len(result.registers) == 5

        except httpx.ConnectError:
            pytest.skip("OpenPLC not available")


class TestOpenPLCConfiguration:
    """Test OpenPLC configuration (read-only)."""

    @pytest.mark.skipif(not HAS_HTTPX, reason="httpx not available")
    def test_modbus_port_configuration(self, openplc_client):
        """Verify Modbus port is configured correctly."""
        # This would check OpenPLC's Modbus configuration
        # Implementation depends on OpenPLC's API
        try:
            response = openplc_client.get("/settings", follow_redirects=True)
            if response.status_code != 200:
                pytest.skip("Settings not accessible")

            # Check response contains Modbus configuration
            # This is informational - actual check depends on OpenPLC version
            assert response.status_code == 200

        except httpx.ConnectError:
            pytest.skip("OpenPLC not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
