"""
Water Treatment Controller - Shared Memory Client
Provides Python access to controller data via shared memory
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Includes correlation ID support for distributed tracing.
"""

import ctypes
import logging
import mmap
import struct
from ctypes import c_bool, c_char, c_float, c_int, c_uint8, c_uint16, c_uint32, c_uint64
from typing import Any

import posix_ipc

# Import correlation ID support (if available)
try:
    from app.core.logging import get_correlation_id
except ImportError:
    def get_correlation_id():
        return None

# Import paths for configurable SHM name
try:
    from app.core.paths import paths as _paths
    _get_shm_name = lambda: _paths.shm_name
except ImportError:
    import os
    _get_shm_name = lambda: os.environ.get("WTC_SHM_NAME", "/wtc_shared_memory")

logger = logging.getLogger(__name__)


def _log_with_correlation(level: int, msg: str, *args, **kwargs):
    """Log with correlation ID if available."""
    cid = get_correlation_id()
    extra = kwargs.get('extra', {})
    if cid:
        extra['correlation_id'] = cid
    kwargs['extra'] = extra
    logger.log(level, msg, *args, **kwargs)

# Shared memory constants - configurable via WTC_SHM_NAME env var
SHM_NAME = _get_shm_name()
SHM_KEY = 0x57544301
SHM_VERSION = 3  # Must match C definition - v3 adds correlation_id to commands
CORRELATION_ID_LEN = 37  # UUID format + null terminator
MAX_SHM_RTUS = 64
MAX_SHM_ALARMS = 256
MAX_SHM_SENSORS = 32
MAX_SHM_ACTUATORS = 32

# Protocol version for compatibility checking
PROTOCOL_VERSION_MAJOR = 1
PROTOCOL_VERSION_MINOR = 0
PROTOCOL_VERSION = (PROTOCOL_VERSION_MAJOR << 8) | PROTOCOL_VERSION_MINOR

# Capability flags - must match C definitions
CAP_AUTHORITY_HANDOFF = (1 << 0)
CAP_STATE_RECONCILE = (1 << 1)
CAP_5BYTE_SENSOR = (1 << 2)
CAP_ALARM_ISA18 = (1 << 3)

# All capabilities supported by this version
CAPABILITIES_CURRENT = (CAP_AUTHORITY_HANDOFF | CAP_STATE_RECONCILE |
                        CAP_5BYTE_SENSOR | CAP_ALARM_ISA18)

# Command types
SHM_CMD_NONE = 0
SHM_CMD_ACTUATOR = 1
SHM_CMD_SETPOINT = 2
SHM_CMD_PID_MODE = 3
SHM_CMD_ACK_ALARM = 4
SHM_CMD_RESET_INTERLOCK = 5
SHM_CMD_ADD_RTU = 6
SHM_CMD_REMOVE_RTU = 7
SHM_CMD_CONNECT_RTU = 8
SHM_CMD_DISCONNECT_RTU = 9
SHM_CMD_DCP_DISCOVER = 10
SHM_CMD_I2C_DISCOVER = 11
SHM_CMD_ONEWIRE_DISCOVER = 12
SHM_CMD_CONFIGURE_SLOT = 13
SHM_CMD_USER_SYNC = 14
SHM_CMD_USER_SYNC_ALL = 15

# Connection states
CONN_STATE_IDLE = 0
CONN_STATE_CONNECTING = 1
CONN_STATE_CONNECTED = 2
CONN_STATE_RUNNING = 3
CONN_STATE_ERROR = 4
CONN_STATE_OFFLINE = 5

# Connection state names (programmatic generation)
CONNECTION_STATE_NAMES = {
    CONN_STATE_IDLE: "IDLE",
    CONN_STATE_CONNECTING: "CONNECTING",
    CONN_STATE_CONNECTED: "CONNECTED",
    CONN_STATE_RUNNING: "RUNNING",
    CONN_STATE_ERROR: "ERROR",
    CONN_STATE_OFFLINE: "OFFLINE",
}

# Sensor status codes (IOPS)
SENSOR_STATUS_GOOD = 0
SENSOR_STATUS_BAD = 1
SENSOR_STATUS_UNCERTAIN = 2

SENSOR_STATUS_NAMES = {
    SENSOR_STATUS_GOOD: "good",
    SENSOR_STATUS_BAD: "bad",
    SENSOR_STATUS_UNCERTAIN: "uncertain",
}

# Data quality codes (OPC UA compatible - 5-byte sensor format)
QUALITY_GOOD = 0x00
QUALITY_UNCERTAIN = 0x40
QUALITY_BAD = 0x80
QUALITY_NOT_CONNECTED = 0xC0

QUALITY_NAMES = {
    QUALITY_GOOD: "good",
    QUALITY_UNCERTAIN: "uncertain",
    QUALITY_BAD: "bad",
    QUALITY_NOT_CONNECTED: "not_connected",
}


class ShmSensor(ctypes.Structure):
    """Sensor data - 5-byte format with quality"""
    _fields_ = [
        ("slot", c_int),
        ("value", c_float),
        ("status", c_int),            # IOPS status
        ("quality", c_uint8),         # Data quality (OPC UA compatible)
        ("timestamp_ms", c_uint64),
    ]


class ShmActuator(ctypes.Structure):
    _fields_ = [
        ("slot", c_int),
        ("command", c_uint8),
        ("pwm_duty", c_uint8),
        ("forced", c_bool),
    ]


class ShmRtu(ctypes.Structure):
    _fields_ = [
        ("station_name", c_char * 64),
        ("ip_address", c_char * 16),
        ("vendor_id", c_uint16),
        ("device_id", c_uint16),
        ("connection_state", c_int),
        ("slot_count", c_int),
        ("sensors", ShmSensor * MAX_SHM_SENSORS),
        ("sensor_count", c_int),
        ("actuators", ShmActuator * MAX_SHM_ACTUATORS),
        ("actuator_count", c_int),
        ("packet_loss_percent", c_float),
        ("total_cycles", c_uint64),
    ]


class ShmAlarm(ctypes.Structure):
    _fields_ = [
        ("alarm_id", c_int),
        ("rule_id", c_int),
        ("rtu_station", c_char * 64),
        ("slot", c_int),
        ("severity", c_int),
        ("state", c_int),
        ("message", c_char * 256),
        ("value", c_float),
        ("threshold", c_float),
        ("raise_time_ms", c_uint64),
        ("ack_time_ms", c_uint64),
        ("ack_user", c_char * 64),
    ]


class ShmPidLoop(ctypes.Structure):
    _fields_ = [
        ("loop_id", c_int),
        ("name", c_char * 64),
        ("enabled", c_bool),
        ("input_rtu", c_char * 64),
        ("input_slot", c_int),
        ("output_rtu", c_char * 64),
        ("output_slot", c_int),
        ("kp", c_float),
        ("ki", c_float),
        ("kd", c_float),
        ("setpoint", c_float),
        ("pv", c_float),
        ("cv", c_float),
        ("mode", c_int),
    ]


class ShmActuatorCmd(ctypes.Structure):
    _fields_ = [
        ("rtu_station", c_char * 64),
        ("slot", c_int),
        ("command", c_uint8),
        ("pwm_duty", c_uint8),
    ]


class ShmSetpointCmd(ctypes.Structure):
    _fields_ = [
        ("loop_id", c_int),
        ("setpoint", c_float),
    ]


class ShmModeCmd(ctypes.Structure):
    _fields_ = [
        ("loop_id", c_int),
        ("mode", c_int),
    ]


class ShmAckCmd(ctypes.Structure):
    _fields_ = [
        ("alarm_id", c_int),
        ("user", c_char * 64),
    ]


class ShmResetCmd(ctypes.Structure):
    _fields_ = [
        ("interlock_id", c_int),
    ]


class ShmAddRtuCmd(ctypes.Structure):
    """Add RTU command - must match C struct add_rtu_cmd"""
    _fields_ = [
        ("station_name", c_char * 64),
        ("ip_address", c_char * 16),
        ("vendor_id", c_uint16),
        ("device_id", c_uint16),
    ]


class ShmRemoveRtuCmd(ctypes.Structure):
    """Remove RTU command"""
    _fields_ = [
        ("station_name", c_char * 64),
    ]


class ShmConnectRtuCmd(ctypes.Structure):
    """Connect RTU command"""
    _fields_ = [
        ("station_name", c_char * 64),
    ]


class ShmDisconnectRtuCmd(ctypes.Structure):
    """Disconnect RTU command"""
    _fields_ = [
        ("station_name", c_char * 64),
    ]


class ShmDcpDiscoverCmd(ctypes.Structure):
    """DCP discover command"""
    _fields_ = [
        ("network_interface", c_char * 32),
        ("timeout_ms", c_uint32),
    ]


class ShmCommandUnion(ctypes.Union):
    _fields_ = [
        ("actuator_cmd", ShmActuatorCmd),
        ("setpoint_cmd", ShmSetpointCmd),
        ("mode_cmd", ShmModeCmd),
        ("ack_cmd", ShmAckCmd),
        ("reset_cmd", ShmResetCmd),
        ("add_rtu_cmd", ShmAddRtuCmd),
        ("remove_rtu_cmd", ShmRemoveRtuCmd),
        ("connect_rtu_cmd", ShmConnectRtuCmd),
        ("disconnect_rtu_cmd", ShmDisconnectRtuCmd),
        ("dcp_discover_cmd", ShmDcpDiscoverCmd),
    ]


class ShmCommand(ctypes.Structure):
    _fields_ = [
        ("sequence", c_uint32),
        ("command_type", c_int),
        ("correlation_id", c_char * CORRELATION_ID_LEN),  # For distributed tracing
        ("cmd", ShmCommandUnion),
    ]


class WtcSharedMemory(ctypes.Structure):
    _fields_ = [
        ("magic", c_uint32),
        ("version", c_uint32),
        ("last_update_ms", c_uint64),
        ("controller_running", c_bool),
        ("total_rtus", c_int),
        ("connected_rtus", c_int),
        ("active_alarms", c_int),
        ("unack_alarms", c_int),
        ("rtus", ShmRtu * MAX_SHM_RTUS),
        ("rtu_count", c_int),
        ("alarms", ShmAlarm * MAX_SHM_ALARMS),
        ("alarm_count", c_int),
        ("pid_loops", ShmPidLoop * 64),
        ("pid_loop_count", c_int),
        ("command", ShmCommand),
        ("command_sequence", c_uint32),
        ("command_ack", c_uint32),
        # Note: pthread_mutex_t is platform-specific, skip in Python
    ]


class WtcShmClient:
    """Client for accessing Water Treatment Controller shared memory"""

    def __init__(self):
        self.shm = None
        self.mm = None
        self._command_seq = 0

    def connect(self) -> bool:
        """Connect to shared memory with version validation"""
        try:
            self.shm = posix_ipc.SharedMemory(SHM_NAME)
            self.mm = mmap.mmap(self.shm.fd, ctypes.sizeof(WtcSharedMemory))

            # Verify magic number
            magic = struct.unpack_from('I', self.mm, 0)[0]
            if magic != SHM_KEY:
                logger.error(f"Invalid shared memory magic: {hex(magic)}")
                self.disconnect()
                return False

            # Verify version compatibility
            version = struct.unpack_from('I', self.mm, 4)[0]
            if version != SHM_VERSION:
                logger.error(
                    f"Shared memory version mismatch: expected {SHM_VERSION}, got {version}. "
                    f"Controller and API must be upgraded together."
                )
                self.disconnect()
                return False

            logger.info(f"Connected to WTC shared memory (version {version})")
            return True

        except posix_ipc.ExistentialError:
            logger.warning("Shared memory not available (controller not running)")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to shared memory: {e}")
            return False

    def disconnect(self):
        """Disconnect from shared memory"""
        if self.mm:
            self.mm.close()
            self.mm = None
        if self.shm:
            self.shm.close_fd()
            self.shm = None

    def is_connected(self) -> bool:
        """Check if connected"""
        return self.mm is not None

    def is_controller_running(self) -> bool:
        """Check if controller is running"""
        if not self.mm:
            return False
        return struct.unpack_from('?', self.mm, 16)[0]  # controller_running offset

    def get_status(self) -> dict[str, Any]:
        """Get system status"""
        if not self.mm:
            return {"connected": False}

        data = WtcSharedMemory.from_buffer_copy(self.mm)
        return {
            "connected": True,
            "controller_running": data.controller_running,
            "last_update_ms": data.last_update_ms,
            "total_rtus": data.total_rtus,
            "connected_rtus": data.connected_rtus,
            "active_alarms": data.active_alarms,
            "unack_alarms": data.unack_alarms,
        }

    def get_rtus(self) -> list[dict[str, Any]]:
        """Get list of RTU devices"""
        if not self.mm:
            return []

        data = WtcSharedMemory.from_buffer_copy(self.mm)
        rtus = []

        for i in range(data.rtu_count):
            rtu = data.rtus[i]
            sensors = []
            for j in range(rtu.sensor_count):
                s = rtu.sensors[j]
                sensors.append({
                    "slot": s.slot,
                    "value": s.value,
                    "status": s.status,
                    "quality": s.quality,  # OPC UA quality from 5-byte format
                    "timestamp_ms": s.timestamp_ms,
                })

            actuators = []
            for j in range(rtu.actuator_count):
                a = rtu.actuators[j]
                actuators.append({
                    "slot": a.slot,
                    "command": a.command,
                    "pwm_duty": a.pwm_duty,
                    "forced": a.forced,
                })

            rtus.append({
                "station_name": rtu.station_name.decode('utf-8').rstrip('\x00'),
                "ip_address": rtu.ip_address.decode('utf-8').rstrip('\x00'),
                "vendor_id": rtu.vendor_id,
                "device_id": rtu.device_id,
                "connection_state": rtu.connection_state,
                "slot_count": rtu.slot_count,
                "sensors": sensors,
                "actuators": actuators,
                "packet_loss_percent": rtu.packet_loss_percent,
                "total_cycles": rtu.total_cycles,
            })

        return rtus

    def get_alarms(self) -> list[dict[str, Any]]:
        """Get list of active alarms"""
        if not self.mm:
            return []

        data = WtcSharedMemory.from_buffer_copy(self.mm)
        alarms = []

        for i in range(data.alarm_count):
            alarm = data.alarms[i]
            alarms.append({
                "alarm_id": alarm.alarm_id,
                "rule_id": alarm.rule_id,
                "rtu_station": alarm.rtu_station.decode('utf-8').rstrip('\x00'),
                "slot": alarm.slot,
                "severity": alarm.severity,
                "state": alarm.state,
                "message": alarm.message.decode('utf-8').rstrip('\x00'),
                "value": alarm.value,
                "threshold": alarm.threshold,
                "raise_time_ms": alarm.raise_time_ms,
                "ack_time_ms": alarm.ack_time_ms,
                "ack_user": alarm.ack_user.decode('utf-8').rstrip('\x00'),
            })

        return alarms

    def get_pid_loops(self) -> list[dict[str, Any]]:
        """Get list of PID loops"""
        if not self.mm:
            return []

        data = WtcSharedMemory.from_buffer_copy(self.mm)
        loops = []

        for i in range(data.pid_loop_count):
            loop = data.pid_loops[i]
            loops.append({
                "loop_id": loop.loop_id,
                "name": loop.name.decode('utf-8').rstrip('\x00'),
                "enabled": loop.enabled,
                "input_rtu": loop.input_rtu.decode('utf-8').rstrip('\x00'),
                "input_slot": loop.input_slot,
                "output_rtu": loop.output_rtu.decode('utf-8').rstrip('\x00'),
                "output_slot": loop.output_slot,
                "kp": loop.kp,
                "ki": loop.ki,
                "kd": loop.kd,
                "setpoint": loop.setpoint,
                "pv": loop.pv,
                "cv": loop.cv,
                "mode": loop.mode,
            })

        return loops

    def _send_command(self, cmd_type: int, **kwargs) -> bool:
        """Send command to controller with correlation ID for tracing"""
        if not self.mm:
            return False

        self._command_seq += 1

        # Get correlation ID from context (if available)
        correlation_id = get_correlation_id() or ""

        # Build command based on type
        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        # Pack: sequence (4), command_type (4), correlation_id (37)
        struct.pack_into('II', cmd_data, 0, self._command_seq, cmd_type)
        # Pack correlation ID at offset 8
        cid_bytes = correlation_id.encode('utf-8')[:CORRELATION_ID_LEN-1]
        struct.pack_into(f'{len(cid_bytes)}s', cmd_data, 8, cid_bytes)

        # Command data starts after correlation_id (offset 8 + 37 = 45)
        data_offset = 8 + CORRELATION_ID_LEN

        if cmd_type == SHM_CMD_ACTUATOR:
            station = kwargs['station'].encode('utf-8')[:63]
            struct.pack_into('64sibb', cmd_data, data_offset, station, kwargs['slot'],
                           kwargs['command'], kwargs.get('pwm_duty', 0))
        elif cmd_type == SHM_CMD_SETPOINT:
            struct.pack_into('if', cmd_data, data_offset, kwargs['loop_id'], kwargs['setpoint'])
        elif cmd_type == SHM_CMD_PID_MODE:
            struct.pack_into('ii', cmd_data, data_offset, kwargs['loop_id'], kwargs['mode'])
        elif cmd_type == SHM_CMD_ACK_ALARM:
            user = kwargs['user'].encode('utf-8')[:63]
            struct.pack_into('i64s', cmd_data, data_offset, kwargs['alarm_id'], user)
        elif cmd_type == SHM_CMD_RESET_INTERLOCK:
            struct.pack_into('i', cmd_data, data_offset, kwargs['interlock_id'])

        # Write command to shared memory
        shm_cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
        self.mm.seek(shm_cmd_offset)
        self.mm.write(bytes(cmd_data))

        # Update sequence
        seq_offset = shm_cmd_offset + ctypes.sizeof(ShmCommand)
        struct.pack_into('I', self.mm, seq_offset, self._command_seq)

        return True

    def command_actuator(self, station: str, slot: int, command: int,
                         pwm_duty: int = 0) -> bool:
        """Send actuator command"""
        return self._send_command(SHM_CMD_ACTUATOR, station=station, slot=slot,
                                  command=command, pwm_duty=pwm_duty)

    def set_setpoint(self, loop_id: int, setpoint: float) -> bool:
        """Set PID loop setpoint"""
        return self._send_command(SHM_CMD_SETPOINT, loop_id=loop_id, setpoint=setpoint)

    def set_pid_mode(self, loop_id: int, mode: int) -> bool:
        """Set PID loop mode"""
        return self._send_command(SHM_CMD_PID_MODE, loop_id=loop_id, mode=mode)

    def acknowledge_alarm(self, alarm_id: int, user: str) -> bool:
        """Acknowledge alarm"""
        return self._send_command(SHM_CMD_ACK_ALARM, alarm_id=alarm_id, user=user)

    def reset_interlock(self, interlock_id: int) -> bool:
        """Reset interlock"""
        return self._send_command(SHM_CMD_RESET_INTERLOCK, interlock_id=interlock_id)

    # ============== RTU-specific accessor methods ==============

    def get_rtu(self, station_name: str) -> dict[str, Any] | None:
        """Get a single RTU by station name"""
        rtus = self.get_rtus()
        for rtu in rtus:
            if rtu["station_name"] == station_name:
                return rtu
        return None

    def get_sensors(self, station_name: str) -> list[dict[str, Any]]:
        """
        Get sensors for a specific RTU.
        Returns list of sensor data with slot, value, status, timestamp.
        """
        rtu = self.get_rtu(station_name)
        if not rtu:
            logger.warning(f"RTU not found in shared memory: {station_name}")
            return []

        sensors = []
        for sensor in rtu.get("sensors", []):
            quality_code = sensor.get("quality", QUALITY_GOOD)
            sensors.append({
                "slot": sensor["slot"],
                "value": sensor["value"],
                "status": SENSOR_STATUS_NAMES.get(sensor["status"], "unknown"),
                "status_code": sensor["status"],
                "quality": QUALITY_NAMES.get(quality_code, "unknown"),
                "quality_code": quality_code,
                "timestamp_ms": sensor["timestamp_ms"],
            })
        return sensors

    def get_actuators(self, station_name: str) -> list[dict[str, Any]]:
        """
        Get actuators for a specific RTU.
        Returns list of actuator states with slot, command, pwm_duty, forced.
        """
        rtu = self.get_rtu(station_name)
        if not rtu:
            logger.warning(f"RTU not found in shared memory: {station_name}")
            return []

        actuators = []
        command_names = {0: "OFF", 1: "ON", 2: "PWM"}
        for actuator in rtu.get("actuators", []):
            actuators.append({
                "slot": actuator["slot"],
                "command": command_names.get(actuator["command"], "UNKNOWN"),
                "command_code": actuator["command"],
                "pwm_duty": actuator["pwm_duty"],
                "forced": actuator["forced"],
            })
        return actuators

    def get_sensor_value(self, station_name: str, slot: int) -> dict[str, Any] | None:
        """Get a specific sensor value by station and slot"""
        sensors = self.get_sensors(station_name)
        for sensor in sensors:
            if sensor["slot"] == slot:
                return sensor
        return None

    def get_actuator_state(self, station_name: str, slot: int) -> dict[str, Any] | None:
        """Get a specific actuator state by station and slot"""
        actuators = self.get_actuators(station_name)
        for actuator in actuators:
            if actuator["slot"] == slot:
                return actuator
        return None

    # ============== RTU Management IPC Commands ==============

    def add_rtu(self, station_name: str, ip_address: str,
                vendor_id: int = 0x0493, device_id: int = 0x0001,
                slot_count: int = 16) -> bool:
        """
        Send IPC command to add RTU to PROFINET controller.
        The controller will initiate DCP identification and AR setup.
        """
        if not self.mm:
            logger.warning("Cannot add RTU: shared memory not connected")
            return False

        logger.info(f"Sending ADD_RTU command: {station_name} at {ip_address}")
        return self._send_rtu_command(SHM_CMD_ADD_RTU, station_name, ip_address,
                                       vendor_id, device_id, slot_count)

    def remove_rtu(self, station_name: str) -> bool:
        """
        Send IPC command to remove RTU from PROFINET controller.
        The controller will close the AR and release resources.
        """
        if not self.mm:
            logger.warning("Cannot remove RTU: shared memory not connected")
            return False

        logger.info(f"Sending REMOVE_RTU command: {station_name}")
        return self._send_rtu_command(SHM_CMD_REMOVE_RTU, station_name)

    def connect_rtu(self, station_name: str) -> bool:
        """
        Send IPC command to connect to RTU via PROFINET.
        Initiates the Application Relationship (AR) setup.
        """
        if not self.mm:
            logger.warning("Cannot connect RTU: shared memory not connected")
            return False

        logger.info(f"Sending CONNECT_RTU command: {station_name}")
        return self._send_rtu_command(SHM_CMD_CONNECT_RTU, station_name)

    def disconnect_rtu(self, station_name: str) -> bool:
        """
        Send IPC command to disconnect RTU.
        Gracefully closes the PROFINET AR.
        """
        if not self.mm:
            logger.warning("Cannot disconnect RTU: shared memory not connected")
            return False

        logger.info(f"Sending DISCONNECT_RTU command: {station_name}")
        return self._send_rtu_command(SHM_CMD_DISCONNECT_RTU, station_name)

    def _send_rtu_command(self, cmd_type: int, station_name: str,
                          ip_address: str = "", vendor_id: int = 0,
                          device_id: int = 0, slot_count: int = 0) -> bool:
        """Internal helper for RTU management commands.

        Uses same structure layout as _send_command:
        - sequence (4 bytes) at offset 0
        - command_type (4 bytes) at offset 4
        - correlation_id (37 bytes) at offset 8
        - command data union starts at offset 45 (8 + CORRELATION_ID_LEN)
        """
        self._command_seq += 1

        # Get correlation ID from context (if available)
        correlation_id = get_correlation_id() or ""

        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        # Pack: sequence (4), command_type (4)
        struct.pack_into('II', cmd_data, 0, self._command_seq, cmd_type)
        # Pack correlation ID at offset 8
        cid_bytes = correlation_id.encode('utf-8')[:CORRELATION_ID_LEN-1]
        struct.pack_into(f'{len(cid_bytes)}s', cmd_data, 8, cid_bytes)

        # Command data union starts after correlation_id (offset 8 + 37 = 45)
        data_offset = 8 + CORRELATION_ID_LEN

        # Pack station name (64 bytes) - all RTU commands have station_name first
        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}s', cmd_data, data_offset, station_bytes)

        # Pack additional data for ADD_RTU
        # add_rtu_cmd layout: station_name[64], ip_address[16], vendor_id(u16), device_id(u16)
        if cmd_type == SHM_CMD_ADD_RTU:
            ip_bytes = ip_address.encode('utf-8')[:15]
            struct.pack_into(f'{len(ip_bytes)}s', cmd_data, data_offset + 64, ip_bytes)
            struct.pack_into('HH', cmd_data, data_offset + 64 + 16, vendor_id, device_id)

        # Write to shared memory command buffer
        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data[:ctypes.sizeof(ShmCommand)]))

            seq_offset = cmd_offset + ctypes.sizeof(ShmCommand)
            struct.pack_into('I', self.mm, seq_offset, self._command_seq)
            return True
        except Exception as e:
            logger.error(f"Failed to send RTU command: {e}")
            return False

    # ============== Discovery IPC Commands ==============

    def dcp_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """
        Discover PROFINET devices on the network using DCP Identify All.

        When the C controller is running, this sends a command via shared memory
        and the controller performs the actual DCP multicast discovery.

        Returns list of discovered devices:
        [
            {
                "mac_address": "00:1A:2B:3C:4D:5E",
                "ip_address": "192.168.1.50",
                "device_name": "water-treat-rtu-01",
                "vendor_name": "Water-Treat",
                "device_type": "RTU",
                "profinet_vendor_id": 0x1171,
                "profinet_device_id": 0x0001
            },
            ...
        ]
        """
        import time

        if not self.mm:
            logger.warning("Shared memory not connected - cannot perform DCP discovery via controller")
            return []

        logger.info(f"Initiating DCP discovery (timeout: {timeout_ms}ms)")
        self._command_seq += 1

        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        struct.pack_into('III', cmd_data, 0, self._command_seq, SHM_CMD_DCP_DISCOVER, timeout_ms)

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data))
            logger.info("DCP discovery command sent to controller")

            # Poll for discovery results in shared memory
            # The controller writes discovered devices to a discovery buffer
            # For now, we wait the full timeout and then read results
            time.sleep(timeout_ms / 1000.0)

            # Read discovery results from shared memory
            # Discovery buffer is located after the main status/RTU data
            devices = self._read_discovery_results()
            logger.info(f"DCP discovery complete, found {len(devices)} devices")
            return devices

        except Exception as e:
            logger.error(f"DCP discovery failed: {e}")
            return []

    def _read_discovery_results(self) -> list[dict[str, Any]]:
        """
        Read discovered devices from the shared memory discovery buffer.
        The C controller populates this buffer after DCP discovery.
        """
        if not self.mm:
            return []

        devices = []
        try:
            # Discovery results are stored after RTU array in shared memory
            # Format: count (uint32), then array of discovery_entry structs
            # Each entry: mac[6], ip[4], name[64], vendor[32], device_type[16], vendor_id, device_id
            discovery_offset = 0x8000  # Discovery buffer offset (32KB into SHM)

            self.mm.seek(discovery_offset)
            count_data = self.mm.read(4)
            if not count_data or len(count_data) < 4:
                return []

            count = struct.unpack('I', count_data)[0]
            if count == 0 or count > 256:  # Sanity check
                return []

            # Read each discovered device
            for _i in range(count):
                entry_data = self.mm.read(128)  # Each entry is 128 bytes
                if len(entry_data) < 128:
                    break

                mac_bytes = entry_data[0:6]
                ip_bytes = entry_data[6:10]
                name = entry_data[10:74].rstrip(b'\x00').decode('utf-8', errors='ignore')
                vendor = entry_data[74:106].rstrip(b'\x00').decode('utf-8', errors='ignore')
                dev_type = entry_data[106:122].rstrip(b'\x00').decode('utf-8', errors='ignore')
                vendor_id, device_id = struct.unpack('HH', entry_data[122:126])

                mac_str = ':'.join(f'{b:02X}' for b in mac_bytes)
                ip_str = '.'.join(str(b) for b in ip_bytes)

                if mac_str != '00:00:00:00:00:00':
                    devices.append({
                        "mac_address": mac_str,
                        "ip_address": ip_str if ip_str != '0.0.0.0' else None,
                        "device_name": name or f"profinet-{mac_str[-8:].replace(':', '')}",
                        "vendor_name": vendor or "Unknown",
                        "device_type": dev_type or "PROFINET Device",
                        "profinet_vendor_id": vendor_id,
                        "profinet_device_id": device_id
                    })

        except Exception as e:
            logger.error(f"Failed to read discovery results: {e}")

        return devices

    # NOTE: I2C and 1-Wire discovery belong in the Water-Treat RTU codebase.
    # The controller discovers RTUs; RTUs discover their own hardware.
    # See: https://github.com/mwilco03/Water-Treat

    def configure_slot(self, station_name: str, slot: int, slot_type: str,
                       name: str = "", unit: str = "",
                       scale_min: float = 0, scale_max: float = 100) -> bool:
        """
        Send slot configuration to RTU.
        Configures sensor/actuator type, scaling, and metadata.
        """
        if not self.mm:
            logger.warning("Cannot configure slot: shared memory not connected")
            return False

        logger.info(f"Configuring slot {slot} on {station_name} as {slot_type}")
        self._command_seq += 1

        cmd_data = bytearray(256)
        struct.pack_into('II', cmd_data, 0, self._command_seq, SHM_CMD_CONFIGURE_SLOT)

        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}s', cmd_data, 8, station_bytes)
        struct.pack_into('i', cmd_data, 72, slot)

        type_bytes = slot_type.encode('utf-8')[:15]
        struct.pack_into(f'{len(type_bytes)}s', cmd_data, 76, type_bytes)

        name_bytes = name.encode('utf-8')[:31]
        struct.pack_into(f'{len(name_bytes)}s', cmd_data, 92, name_bytes)

        unit_bytes = unit.encode('utf-8')[:7]
        struct.pack_into(f'{len(unit_bytes)}sff', cmd_data, 124, unit_bytes, scale_min, scale_max)

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data[:ctypes.sizeof(ShmCommand)]))
            return True
        except Exception as e:
            logger.error(f"Failed to send slot config command: {e}")
            return False

    # ============== User Sync Methods ==============

    def sync_users_to_rtu(self, station_name: str, users: list[dict[str, Any]]) -> bool:
        """
        Send user sync command to a specific RTU.

        Users will be synced via PROFINET acyclic write to the RTU.
        The RTU stores these users for local TUI authentication.

        Args:
            station_name: Target RTU station name
            users: List of user dicts with username, password_hash, role, active

        Returns:
            True if command was sent successfully
        """
        if not self.mm:
            logger.warning("Cannot sync users: shared memory not connected")
            return False

        if not users:
            logger.info(f"No users to sync to {station_name}")
            return True

        logger.info(f"Syncing {len(users)} users to RTU {station_name}")
        self._command_seq += 1

        # Build command data
        # Format: seq(4) + cmd_type(4) + station_name(64) + user_count(4) + users...
        cmd_data = bytearray(4096)  # Large buffer for user data
        struct.pack_into('II', cmd_data, 0, self._command_seq, SHM_CMD_USER_SYNC)

        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}s', cmd_data, 8, station_bytes)

        user_count = min(len(users), 32)  # Max 32 users per sync
        struct.pack_into('I', cmd_data, 72, user_count)

        # Pack user records: username(32) + password_hash(64) + role(1) + flags(1)
        offset = 76
        for i in range(user_count):
            user = users[i]
            username = user.get('username', '')[:31].encode('utf-8')
            password_hash = user.get('password_hash', '')[:63].encode('utf-8')
            role = {'viewer': 0, 'operator': 1, 'engineer': 2, 'admin': 3}.get(user.get('role', 'viewer'), 0)
            active = 1 if user.get('active', True) else 0
            flags = active | 0x02  # Bit 1 = synced_from_controller

            struct.pack_into('32s64sBB', cmd_data, offset,
                            username.ljust(32, b'\x00'),
                            password_hash.ljust(64, b'\x00'),
                            role, flags)
            offset += 98

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data[:512]))  # Command struct is limited
            logger.debug(f"User sync command sent for {station_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to send user sync command: {e}")
            return False

    def sync_users_to_all_rtus(self, users: list[dict[str, Any]]) -> int:
        """
        Send user sync command to all connected RTUs.

        Args:
            users: List of user dicts with username, password_hash, role, active

        Returns:
            Number of RTUs that received the sync command
        """
        if not self.mm:
            logger.warning("Cannot sync users: shared memory not connected")
            return 0

        if not users:
            logger.info("No users to sync")
            return 0

        # Get list of connected RTUs
        rtus = self.get_rtus()
        if not rtus:
            logger.info("No RTUs available for user sync")
            return 0

        success_count = 0
        for rtu in rtus:
            if rtu.get('connection_state') == CONN_STATE_RUNNING:
                if self.sync_users_to_rtu(rtu['station_name'], users):
                    success_count += 1

        logger.info(f"User sync sent to {success_count}/{len(rtus)} RTUs")
        return success_count


# ============== Circuit Breaker for Resilience ==============


class CircuitBreaker:
    """
    Circuit breaker pattern for shared memory access.

    Prevents cascade failures when the controller core becomes
    unresponsive by temporarily blocking requests after repeated failures.

    States:
    - CLOSED: Normal operation, requests go through
    - OPEN: Blocking requests, waiting for reset timeout
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 30,
                 success_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold

        self._state = "CLOSED"
        self._failures = 0
        self._successes = 0
        self._last_failure_time: float | None = None

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        if self._state == "OPEN":
            # Check if reset timeout has elapsed
            import time
            if self._last_failure_time and \
               (time.time() - self._last_failure_time) > self.reset_timeout:
                self._state = "HALF_OPEN"
                self._successes = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return False
            return True
        return False

    def record_success(self):
        """Record a successful operation."""
        if self._state == "HALF_OPEN":
            self._successes += 1
            if self._successes >= self.success_threshold:
                self._state = "CLOSED"
                self._failures = 0
                logger.info("Circuit breaker CLOSED - service recovered")
        elif self._state == "CLOSED":
            # Reset failure count on success
            self._failures = 0

    def record_failure(self):
        """Record a failed operation."""
        import time
        self._failures += 1
        self._last_failure_time = time.time()

        if self._state == "HALF_OPEN":
            # Any failure in half-open state reopens the circuit
            self._state = "OPEN"
            logger.warning("Circuit breaker OPEN - service still failing")
        elif self._state == "CLOSED" and self._failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self._failures} failures")


class WtcShmClientWithCircuitBreaker:
    """
    Wrapper around WtcShmClient that adds circuit breaker protection.

    Use this client in production to prevent cascade failures when
    the controller core becomes unresponsive.
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 30):
        self._client = WtcShmClient()
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout
        )

    def connect(self) -> bool:
        """Connect to shared memory with circuit breaker protection."""
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker OPEN - skipping connection attempt")
            return False

        try:
            result = self._client.connect()
            if result:
                self._circuit_breaker.record_success()
            else:
                self._circuit_breaker.record_failure()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from shared memory."""
        self._client.disconnect()

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._client.is_connected()

    def get_status(self) -> dict[str, Any]:
        """Get system status with circuit breaker protection."""
        if self._circuit_breaker.is_open:
            return {"connected": False, "circuit_breaker": "OPEN"}

        try:
            result = self._client.get_status()
            self._circuit_breaker.record_success()
            result["circuit_breaker"] = self._circuit_breaker.state
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            return {"connected": False, "error": str(e), "circuit_breaker": self._circuit_breaker.state}

    def get_rtus(self) -> list[dict[str, Any]]:
        """Get RTUs with circuit breaker protection."""
        if self._circuit_breaker.is_open:
            return []

        try:
            result = self._client.get_rtus()
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"get_rtus failed: {e}")
            return []

    @property
    def circuit_breaker_state(self) -> str:
        """Get current circuit breaker state."""
        return self._circuit_breaker.state

    # Delegate other methods to the wrapped client
    def __getattr__(self, name):
        """Delegate unknown attributes to wrapped client."""
        return getattr(self._client, name)


# Global client instance
_client: WtcShmClient | None = None


def get_client() -> WtcShmClient:
    """Get or create shared memory client"""
    global _client
    if _client is None:
        _client = WtcShmClient()
        _client.connect()
    elif not _client.is_connected():
        _client.connect()
    return _client


def get_resilient_client(failure_threshold: int = 5,
                         reset_timeout: int = 30) -> WtcShmClientWithCircuitBreaker:
    """
    Get a shared memory client with circuit breaker protection.

    Use this in production for resilience against controller failures.
    """
    client = WtcShmClientWithCircuitBreaker(
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout
    )
    client.connect()
    return client
