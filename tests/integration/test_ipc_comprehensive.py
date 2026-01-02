#!/usr/bin/env python3
"""
Comprehensive IPC Integration Tests

Tests the shared memory client, circuit breaker, and controller communication.
Covers:
- WtcShmClient methods and data structure parsing
- WtcShmClientWithCircuitBreaker resilience patterns
- CircuitBreaker state transitions
- Command serialization and sending
- Data quality and sensor status handling

Run with:
  pytest tests/integration/test_ipc_comprehensive.py -v
"""

import ctypes
import mmap
import os
import struct
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Try to import the shared memory client
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../web/api'))
    from shm_client import (
        WtcShmClient,
        WtcShmClientWithCircuitBreaker,
        CircuitBreaker,
        WtcSharedMemory,
        ShmRtu,
        ShmSensor,
        ShmActuator,
        ShmAlarm,
        ShmPidLoop,
        ShmCommand,
        SHM_KEY,
        SHM_VERSION,
        SHM_CMD_ACTUATOR,
        SHM_CMD_SETPOINT,
        SHM_CMD_PID_MODE,
        SHM_CMD_ACK_ALARM,
        SHM_CMD_RESET_INTERLOCK,
        SHM_CMD_ADD_RTU,
        SHM_CMD_REMOVE_RTU,
        SHM_CMD_CONNECT_RTU,
        SHM_CMD_DISCONNECT_RTU,
        CONN_STATE_IDLE,
        CONN_STATE_CONNECTING,
        CONN_STATE_CONNECTED,
        CONN_STATE_RUNNING,
        CONN_STATE_ERROR,
        CONNECTION_STATE_NAMES,
        SENSOR_STATUS_GOOD,
        SENSOR_STATUS_BAD,
        SENSOR_STATUS_UNCERTAIN,
        QUALITY_GOOD,
        QUALITY_BAD,
        QUALITY_UNCERTAIN,
        QUALITY_NOT_CONNECTED,
        MAX_SHM_RTUS,
        MAX_SHM_SENSORS,
        MAX_SHM_ACTUATORS,
    )
    HAS_SHM_CLIENT = True
except ImportError as e:
    HAS_SHM_CLIENT = False
    WtcShmClient = None
    print(f"Could not import shm_client: {e}")

# Try to import posix_ipc
try:
    import posix_ipc
    HAS_POSIX_IPC = True
except ImportError:
    HAS_POSIX_IPC = False
    posix_ipc = None


# ============== Test Fixtures ==============


@pytest.fixture
def mock_shared_memory():
    """Create a mock shared memory buffer with valid structure."""
    # Create a buffer large enough for WtcSharedMemory
    size = ctypes.sizeof(WtcSharedMemory) if HAS_SHM_CLIENT else 65536
    buffer = bytearray(size)

    if HAS_SHM_CLIENT:
        # Initialize header
        struct.pack_into('I', buffer, 0, SHM_KEY)  # magic
        struct.pack_into('I', buffer, 4, SHM_VERSION)  # version
        struct.pack_into('Q', buffer, 8, int(time.time() * 1000))  # last_update_ms
        struct.pack_into('?', buffer, 16, True)  # controller_running
        struct.pack_into('i', buffer, 17, 2)  # total_rtus
        struct.pack_into('i', buffer, 21, 1)  # connected_rtus
        struct.pack_into('i', buffer, 25, 3)  # active_alarms
        struct.pack_into('i', buffer, 29, 1)  # unack_alarms

    return buffer


@pytest.fixture
def populated_shared_memory(mock_shared_memory):
    """Create shared memory with populated RTU, sensor, and alarm data."""
    buffer = mock_shared_memory

    if not HAS_SHM_CLIENT:
        return buffer

    # Create a WtcSharedMemory structure and populate it
    shm = WtcSharedMemory.from_buffer(buffer)
    shm.magic = SHM_KEY
    shm.version = SHM_VERSION
    shm.last_update_ms = int(time.time() * 1000)
    shm.controller_running = True
    shm.total_rtus = 2
    shm.connected_rtus = 1
    shm.active_alarms = 1
    shm.unack_alarms = 1
    shm.rtu_count = 2
    shm.alarm_count = 1
    shm.pid_loop_count = 1

    # Populate first RTU
    rtu1 = shm.rtus[0]
    rtu1.station_name = b"water-rtu-01"
    rtu1.ip_address = b"192.168.1.50"
    rtu1.vendor_id = 0x1171
    rtu1.device_id = 0x0001
    rtu1.connection_state = CONN_STATE_RUNNING
    rtu1.slot_count = 16
    rtu1.sensor_count = 2
    rtu1.actuator_count = 1
    rtu1.packet_loss_percent = 0.5
    rtu1.total_cycles = 10000

    # Sensors for RTU1
    rtu1.sensors[0].slot = 1
    rtu1.sensors[0].value = 25.5
    rtu1.sensors[0].status = SENSOR_STATUS_GOOD
    rtu1.sensors[0].quality = QUALITY_GOOD
    rtu1.sensors[0].timestamp_ms = int(time.time() * 1000)

    rtu1.sensors[1].slot = 2
    rtu1.sensors[1].value = 7.2
    rtu1.sensors[1].status = SENSOR_STATUS_GOOD
    rtu1.sensors[1].quality = QUALITY_GOOD
    rtu1.sensors[1].timestamp_ms = int(time.time() * 1000)

    # Actuator for RTU1
    rtu1.actuators[0].slot = 1
    rtu1.actuators[0].command = 1  # ON
    rtu1.actuators[0].pwm_duty = 100
    rtu1.actuators[0].forced = False

    # Populate second RTU (disconnected)
    rtu2 = shm.rtus[1]
    rtu2.station_name = b"water-rtu-02"
    rtu2.ip_address = b"192.168.1.51"
    rtu2.connection_state = CONN_STATE_ERROR
    rtu2.sensor_count = 0
    rtu2.actuator_count = 0

    # Populate alarm
    alarm = shm.alarms[0]
    alarm.alarm_id = 1
    alarm.rule_id = 101
    alarm.rtu_station = b"water-rtu-01"
    alarm.slot = 1
    alarm.severity = 2  # Warning
    alarm.state = 1  # Active
    alarm.message = b"Temperature high"
    alarm.value = 85.5
    alarm.threshold = 80.0
    alarm.raise_time_ms = int(time.time() * 1000) - 60000

    # Populate PID loop
    pid = shm.pid_loops[0]
    pid.loop_id = 1
    pid.name = b"temp-control-1"
    pid.enabled = True
    pid.input_rtu = b"water-rtu-01"
    pid.input_slot = 1
    pid.output_rtu = b"water-rtu-01"
    pid.output_slot = 1
    pid.kp = 1.0
    pid.ki = 0.1
    pid.kd = 0.05
    pid.setpoint = 25.0
    pid.pv = 25.5
    pid.cv = 50.0
    pid.mode = 1  # Auto

    return buffer


@pytest.fixture
def circuit_breaker():
    """Create a circuit breaker with short timeouts for testing."""
    return CircuitBreaker(
        failure_threshold=3,
        reset_timeout=1,  # 1 second for faster tests
        success_threshold=2
    )


# ============== Circuit Breaker Tests ==============


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestCircuitBreaker:
    """Test CircuitBreaker state machine."""

    def test_initial_state_is_closed(self, circuit_breaker):
        """Circuit breaker starts in CLOSED state."""
        assert circuit_breaker.state == "CLOSED"
        assert not circuit_breaker.is_open

    def test_stays_closed_on_success(self, circuit_breaker):
        """Successful operations keep circuit CLOSED."""
        for _ in range(10):
            circuit_breaker.record_success()

        assert circuit_breaker.state == "CLOSED"
        assert circuit_breaker._failures == 0

    def test_opens_after_threshold_failures(self, circuit_breaker):
        """Circuit opens after failure_threshold failures."""
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "OPEN"
        assert circuit_breaker.is_open

    def test_stays_closed_below_threshold(self, circuit_breaker):
        """Circuit stays closed if failures below threshold."""
        for _ in range(circuit_breaker.failure_threshold - 1):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "CLOSED"
        assert not circuit_breaker.is_open

    def test_success_resets_failure_count(self, circuit_breaker):
        """Success resets the failure counter."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        circuit_breaker.record_success()

        assert circuit_breaker._failures == 0

    def test_transitions_to_half_open_after_timeout(self, circuit_breaker):
        """Circuit transitions to HALF_OPEN after reset_timeout."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == "OPEN"

        # Wait for timeout
        time.sleep(circuit_breaker.reset_timeout + 0.1)

        # Check is_open triggers transition
        assert not circuit_breaker.is_open
        assert circuit_breaker.state == "HALF_OPEN"

    def test_half_open_closes_after_successes(self, circuit_breaker):
        """HALF_OPEN transitions to CLOSED after success_threshold successes."""
        # Get to HALF_OPEN state
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        time.sleep(circuit_breaker.reset_timeout + 0.1)
        _ = circuit_breaker.is_open  # Trigger transition

        assert circuit_breaker.state == "HALF_OPEN"

        # Record enough successes
        for _ in range(circuit_breaker.success_threshold):
            circuit_breaker.record_success()

        assert circuit_breaker.state == "CLOSED"

    def test_half_open_reopens_on_failure(self, circuit_breaker):
        """HALF_OPEN transitions back to OPEN on any failure."""
        # Get to HALF_OPEN state
        for _ in range(circuit_breaker.failure_threshold):
            circuit_breaker.record_failure()
        time.sleep(circuit_breaker.reset_timeout + 0.1)
        _ = circuit_breaker.is_open  # Trigger transition

        assert circuit_breaker.state == "HALF_OPEN"

        # Single failure reopens
        circuit_breaker.record_failure()

        assert circuit_breaker.state == "OPEN"


# ============== WtcShmClient Tests ==============


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientStructures:
    """Test data structure parsing and serialization."""

    def test_wtc_shared_memory_size(self):
        """Verify structure sizes are reasonable."""
        size = ctypes.sizeof(WtcSharedMemory)
        assert size > 1000  # Should be substantial
        assert size < 10 * 1024 * 1024  # But less than 10MB

    def test_shm_sensor_size(self):
        """Verify sensor structure size."""
        size = ctypes.sizeof(ShmSensor)
        assert size >= 20  # slot + value + status + quality + timestamp

    def test_shm_rtu_size(self):
        """Verify RTU structure size."""
        size = ctypes.sizeof(ShmRtu)
        assert size > 100  # Should include sensors/actuators

    def test_connection_state_names(self):
        """Verify connection state name mapping."""
        assert CONNECTION_STATE_NAMES[CONN_STATE_IDLE] == "IDLE"
        assert CONNECTION_STATE_NAMES[CONN_STATE_RUNNING] == "RUNNING"
        assert CONNECTION_STATE_NAMES[CONN_STATE_ERROR] == "ERROR"


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientParsing:
    """Test WtcShmClient data parsing methods."""

    def test_get_status_disconnected(self):
        """get_status returns disconnected when not connected."""
        client = WtcShmClient()
        status = client.get_status()

        assert status["connected"] == False

    def test_get_rtus_disconnected(self):
        """get_rtus returns empty list when not connected."""
        client = WtcShmClient()
        rtus = client.get_rtus()

        assert rtus == []

    def test_get_alarms_disconnected(self):
        """get_alarms returns empty list when not connected."""
        client = WtcShmClient()
        alarms = client.get_alarms()

        assert alarms == []

    def test_is_connected_false_initially(self):
        """Client starts disconnected."""
        client = WtcShmClient()
        assert not client.is_connected()

    def test_is_controller_running_false_when_disconnected(self):
        """Controller running returns false when disconnected."""
        client = WtcShmClient()
        assert not client.is_controller_running()

    def test_parse_populated_shm(self, populated_shared_memory):
        """Parse RTUs from populated shared memory."""
        client = WtcShmClient()
        # Mock the mmap
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        rtus = client.get_rtus()

        assert len(rtus) == 2
        assert rtus[0]["station_name"] == "water-rtu-01"
        assert rtus[0]["ip_address"] == "192.168.1.50"
        assert rtus[0]["connection_state"] == CONN_STATE_RUNNING
        assert len(rtus[0]["sensors"]) == 2
        assert len(rtus[0]["actuators"]) == 1

        # Check sensor data
        assert rtus[0]["sensors"][0]["slot"] == 1
        assert rtus[0]["sensors"][0]["value"] == pytest.approx(25.5, rel=0.01)
        assert rtus[0]["sensors"][0]["status"] == SENSOR_STATUS_GOOD

        client.mm.close()

    def test_parse_alarms(self, populated_shared_memory):
        """Parse alarms from populated shared memory."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        alarms = client.get_alarms()

        assert len(alarms) == 1
        assert alarms[0]["alarm_id"] == 1
        assert alarms[0]["rtu_station"] == "water-rtu-01"
        assert alarms[0]["message"] == "Temperature high"
        assert alarms[0]["value"] == pytest.approx(85.5, rel=0.01)
        assert alarms[0]["threshold"] == pytest.approx(80.0, rel=0.01)

        client.mm.close()

    def test_parse_pid_loops(self, populated_shared_memory):
        """Parse PID loops from populated shared memory."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        loops = client.get_pid_loops()

        assert len(loops) == 1
        assert loops[0]["loop_id"] == 1
        assert loops[0]["name"] == "temp-control-1"
        assert loops[0]["enabled"] == True
        assert loops[0]["kp"] == pytest.approx(1.0, rel=0.01)
        assert loops[0]["setpoint"] == pytest.approx(25.0, rel=0.01)

        client.mm.close()

    def test_get_status_with_data(self, populated_shared_memory):
        """Get system status from populated shared memory."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        status = client.get_status()

        assert status["connected"] == True
        assert status["controller_running"] == True
        assert status["total_rtus"] == 2
        assert status["connected_rtus"] == 1
        assert status["active_alarms"] == 1

        client.mm.close()


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientRtuAccessors:
    """Test RTU-specific accessor methods."""

    def test_get_rtu_by_name(self, populated_shared_memory):
        """Get specific RTU by station name."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        rtu = client.get_rtu("water-rtu-01")

        assert rtu is not None
        assert rtu["station_name"] == "water-rtu-01"
        assert rtu["connection_state"] == CONN_STATE_RUNNING

        client.mm.close()

    def test_get_rtu_not_found(self, populated_shared_memory):
        """get_rtu returns None for unknown station."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        rtu = client.get_rtu("nonexistent-rtu")

        assert rtu is None

        client.mm.close()

    def test_get_sensors(self, populated_shared_memory):
        """Get sensors for specific RTU."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        sensors = client.get_sensors("water-rtu-01")

        assert len(sensors) == 2
        assert sensors[0]["slot"] == 1
        assert sensors[0]["value"] == pytest.approx(25.5, rel=0.01)
        assert sensors[0]["status"] == "good"
        assert sensors[0]["quality"] == "good"

        client.mm.close()

    def test_get_actuators(self, populated_shared_memory):
        """Get actuators for specific RTU."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        actuators = client.get_actuators("water-rtu-01")

        assert len(actuators) == 1
        assert actuators[0]["slot"] == 1
        assert actuators[0]["command"] == "ON"
        assert actuators[0]["pwm_duty"] == 100

        client.mm.close()

    def test_get_sensor_value(self, populated_shared_memory):
        """Get specific sensor value by slot."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        sensor = client.get_sensor_value("water-rtu-01", 1)

        assert sensor is not None
        assert sensor["slot"] == 1
        assert sensor["value"] == pytest.approx(25.5, rel=0.01)

        # Test non-existent slot
        sensor = client.get_sensor_value("water-rtu-01", 99)
        assert sensor is None

        client.mm.close()

    def test_get_actuator_state(self, populated_shared_memory):
        """Get specific actuator state by slot."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        actuator = client.get_actuator_state("water-rtu-01", 1)

        assert actuator is not None
        assert actuator["slot"] == 1
        assert actuator["command"] == "ON"

        # Test non-existent slot
        actuator = client.get_actuator_state("water-rtu-01", 99)
        assert actuator is None

        client.mm.close()


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientCommands:
    """Test command sending methods."""

    def test_command_actuator_disconnected(self):
        """command_actuator returns False when disconnected."""
        client = WtcShmClient()

        result = client.command_actuator("water-rtu-01", 1, 1)

        assert result == False

    def test_set_setpoint_disconnected(self):
        """set_setpoint returns False when disconnected."""
        client = WtcShmClient()

        result = client.set_setpoint(1, 25.0)

        assert result == False

    def test_acknowledge_alarm_disconnected(self):
        """acknowledge_alarm returns False when disconnected."""
        client = WtcShmClient()

        result = client.acknowledge_alarm(1, "testuser")

        assert result == False

    def test_command_sequence_increments(self, populated_shared_memory):
        """Command sequence number increments with each command."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        initial_seq = client._command_seq

        client.command_actuator("water-rtu-01", 1, 1)
        assert client._command_seq == initial_seq + 1

        client.set_setpoint(1, 25.0)
        assert client._command_seq == initial_seq + 2

        client.mm.close()


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientRtuManagement:
    """Test RTU management IPC commands."""

    def test_add_rtu_disconnected(self):
        """add_rtu returns False when disconnected."""
        client = WtcShmClient()

        result = client.add_rtu("new-rtu", "192.168.1.100")

        assert result == False

    def test_remove_rtu_disconnected(self):
        """remove_rtu returns False when disconnected."""
        client = WtcShmClient()

        result = client.remove_rtu("water-rtu-01")

        assert result == False

    def test_connect_rtu_disconnected(self):
        """connect_rtu returns False when disconnected."""
        client = WtcShmClient()

        result = client.connect_rtu("water-rtu-01")

        assert result == False

    def test_disconnect_rtu_disconnected(self):
        """disconnect_rtu returns False when disconnected."""
        client = WtcShmClient()

        result = client.disconnect_rtu("water-rtu-01")

        assert result == False


# ============== WtcShmClientWithCircuitBreaker Tests ==============


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientWithCircuitBreaker:
    """Test circuit breaker wrapper client."""

    def test_initial_state(self):
        """Client starts with closed circuit breaker."""
        with patch.object(WtcShmClient, 'connect', return_value=False):
            client = WtcShmClientWithCircuitBreaker(
                failure_threshold=3,
                reset_timeout=1
            )

        assert client.circuit_breaker_state == "CLOSED"

    def test_get_status_with_circuit_breaker_state(self):
        """Status includes circuit breaker state."""
        client = WtcShmClientWithCircuitBreaker()
        # Without connecting, status shows disconnected
        status = client.get_status()

        assert "circuit_breaker" in status or status["connected"] == False

    def test_get_rtus_empty_when_open(self):
        """get_rtus returns empty when circuit is open."""
        client = WtcShmClientWithCircuitBreaker(failure_threshold=2)

        # Force circuit open
        client._circuit_breaker._state = "OPEN"
        client._circuit_breaker._last_failure_time = time.time()

        rtus = client.get_rtus()

        assert rtus == []

    def test_connect_records_failure(self):
        """Failed connections are recorded by circuit breaker."""
        with patch.object(WtcShmClient, 'connect', return_value=False):
            client = WtcShmClientWithCircuitBreaker(failure_threshold=3)

            # Multiple failed connections
            for _ in range(3):
                client.connect()

            assert client.circuit_breaker_state == "OPEN"

    def test_connect_records_success(self):
        """Successful connections are recorded by circuit breaker."""
        with patch.object(WtcShmClient, 'connect', return_value=True):
            client = WtcShmClientWithCircuitBreaker(failure_threshold=3)

            # Record some failures first
            client._circuit_breaker._failures = 2

            # Successful connection resets
            client.connect()

            assert client._circuit_breaker._failures == 0

    def test_skips_connection_when_open(self):
        """Connection attempts are skipped when circuit is open."""
        with patch.object(WtcShmClient, 'connect') as mock_connect:
            client = WtcShmClientWithCircuitBreaker(failure_threshold=2)

            # Force circuit open
            client._circuit_breaker._state = "OPEN"
            client._circuit_breaker._last_failure_time = time.time()

            result = client.connect()

            assert result == False
            mock_connect.assert_not_called()

    def test_delegation_to_wrapped_client(self):
        """Unknown attributes are delegated to wrapped client."""
        client = WtcShmClientWithCircuitBreaker()

        # Access wrapped client method
        assert hasattr(client, 'disconnect')
        assert hasattr(client, 'get_alarms')
        assert hasattr(client, 'get_pid_loops')


# ============== Connection Tests ==============


@pytest.mark.skipif(not HAS_POSIX_IPC, reason="posix_ipc not available")
@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestWtcShmClientConnection:
    """Test actual shared memory connection (requires POSIX IPC)."""

    def test_connect_nonexistent_shm(self):
        """Connection fails gracefully for non-existent shared memory."""
        # Use a unique name that won't exist
        with patch('shm_client.SHM_NAME', '/wtc_test_nonexistent_12345'):
            client = WtcShmClient()
            result = client.connect()

            assert result == False
            assert not client.is_connected()

    def test_connect_invalid_magic(self):
        """Connection fails when magic number is invalid."""
        test_shm_name = "/wtc_test_invalid_magic"

        try:
            # Create shared memory with invalid magic
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                size=ctypes.sizeof(WtcSharedMemory)
            )

            mm = mmap.mmap(shm.fd, shm.size)
            # Write invalid magic
            struct.pack_into('I', mm, 0, 0xDEADBEEF)
            mm.close()
            shm.close_fd()

            with patch('shm_client.SHM_NAME', test_shm_name):
                client = WtcShmClient()
                result = client.connect()

                assert result == False
                assert not client.is_connected()

            # Cleanup
            shm = posix_ipc.SharedMemory(test_shm_name)
            shm.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")

    def test_connect_version_mismatch(self):
        """Connection fails when version doesn't match."""
        test_shm_name = "/wtc_test_version_mismatch"

        try:
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                size=ctypes.sizeof(WtcSharedMemory)
            )

            mm = mmap.mmap(shm.fd, shm.size)
            # Write valid magic but wrong version
            struct.pack_into('I', mm, 0, SHM_KEY)
            struct.pack_into('I', mm, 4, SHM_VERSION + 99)
            mm.close()
            shm.close_fd()

            with patch('shm_client.SHM_NAME', test_shm_name):
                client = WtcShmClient()
                result = client.connect()

                assert result == False
                assert not client.is_connected()

            # Cleanup
            shm = posix_ipc.SharedMemory(test_shm_name)
            shm.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")

    def test_connect_and_disconnect(self):
        """Test successful connection and disconnection."""
        test_shm_name = "/wtc_test_connect_disconnect"

        try:
            shm = posix_ipc.SharedMemory(
                test_shm_name,
                flags=posix_ipc.O_CREAT | posix_ipc.O_RDWR,
                size=ctypes.sizeof(WtcSharedMemory)
            )

            mm = mmap.mmap(shm.fd, shm.size)
            # Write valid header
            struct.pack_into('I', mm, 0, SHM_KEY)
            struct.pack_into('I', mm, 4, SHM_VERSION)
            mm.close()
            shm.close_fd()

            with patch('shm_client.SHM_NAME', test_shm_name):
                client = WtcShmClient()
                result = client.connect()

                assert result == True
                assert client.is_connected()

                client.disconnect()

                assert not client.is_connected()

            # Cleanup
            shm = posix_ipc.SharedMemory(test_shm_name)
            shm.unlink()

        except PermissionError:
            pytest.skip("Insufficient permissions for shared memory")


# ============== Data Quality Tests ==============


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestDataQuality:
    """Test data quality code handling."""

    def test_quality_codes_defined(self):
        """Verify all quality codes are defined."""
        assert QUALITY_GOOD == 0x00
        assert QUALITY_UNCERTAIN == 0x40
        assert QUALITY_BAD == 0x80
        assert QUALITY_NOT_CONNECTED == 0xC0

    def test_sensor_status_codes_defined(self):
        """Verify sensor status codes are defined."""
        assert SENSOR_STATUS_GOOD == 0
        assert SENSOR_STATUS_BAD == 1
        assert SENSOR_STATUS_UNCERTAIN == 2

    def test_quality_in_sensor_data(self, populated_shared_memory):
        """Sensor data includes quality information."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        sensors = client.get_sensors("water-rtu-01")

        assert len(sensors) > 0
        assert "quality" in sensors[0]
        assert "quality_code" in sensors[0]
        assert sensors[0]["quality"] == "good"
        assert sensors[0]["quality_code"] == QUALITY_GOOD

        client.mm.close()


# ============== User Sync Tests ==============


@pytest.mark.skipif(not HAS_SHM_CLIENT, reason="shm_client not available")
class TestUserSync:
    """Test user synchronization commands."""

    def test_sync_users_to_rtu_disconnected(self):
        """sync_users_to_rtu returns False when disconnected."""
        client = WtcShmClient()

        users = [{"username": "test", "password_hash": "abc123", "role": "operator"}]
        result = client.sync_users_to_rtu("water-rtu-01", users)

        assert result == False

    def test_sync_users_empty_list(self, populated_shared_memory):
        """sync_users_to_rtu returns True for empty user list."""
        client = WtcShmClient()
        client.mm = mmap.mmap(-1, len(populated_shared_memory))
        client.mm.write(populated_shared_memory)
        client.mm.seek(0)

        result = client.sync_users_to_rtu("water-rtu-01", [])

        assert result == True

        client.mm.close()

    def test_sync_users_to_all_rtus_disconnected(self):
        """sync_users_to_all_rtus returns 0 when disconnected."""
        client = WtcShmClient()

        users = [{"username": "test", "password_hash": "abc123", "role": "operator"}]
        count = client.sync_users_to_all_rtus(users)

        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
