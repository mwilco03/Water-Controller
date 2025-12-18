"""
Water Treatment Controller - Shared Memory Client
Provides Python access to controller data via shared memory
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import mmap
import struct
import ctypes
from ctypes import c_uint32, c_uint64, c_int, c_float, c_bool, c_uint8, c_uint16, c_char
from typing import Optional, List, Dict, Any
import posix_ipc
import logging

logger = logging.getLogger(__name__)

# Shared memory constants
SHM_NAME = "/wtc_shared_memory"
SHM_KEY = 0x57544301
SHM_VERSION = 1
MAX_SHM_RTUS = 64
MAX_SHM_ALARMS = 256
MAX_SHM_SENSORS = 32
MAX_SHM_ACTUATORS = 32

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

# Sensor status codes
SENSOR_STATUS_GOOD = 0
SENSOR_STATUS_BAD = 1
SENSOR_STATUS_UNCERTAIN = 2

SENSOR_STATUS_NAMES = {
    SENSOR_STATUS_GOOD: "good",
    SENSOR_STATUS_BAD: "bad",
    SENSOR_STATUS_UNCERTAIN: "uncertain",
}


class ShmSensor(ctypes.Structure):
    _fields_ = [
        ("slot", c_int),
        ("value", c_float),
        ("status", c_int),
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


class ShmCommandUnion(ctypes.Union):
    _fields_ = [
        ("actuator_cmd", ShmActuatorCmd),
        ("setpoint_cmd", ShmSetpointCmd),
        ("mode_cmd", ShmModeCmd),
        ("ack_cmd", ShmAckCmd),
        ("reset_cmd", ShmResetCmd),
    ]


class ShmCommand(ctypes.Structure):
    _fields_ = [
        ("sequence", c_uint32),
        ("command_type", c_int),
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
        """Connect to shared memory"""
        try:
            self.shm = posix_ipc.SharedMemory(SHM_NAME)
            self.mm = mmap.mmap(self.shm.fd, ctypes.sizeof(WtcSharedMemory))

            # Verify magic number
            magic = struct.unpack_from('I', self.mm, 0)[0]
            if magic != SHM_KEY:
                logger.error(f"Invalid shared memory magic: {hex(magic)}")
                self.disconnect()
                return False

            logger.info("Connected to WTC shared memory")
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

    def get_status(self) -> Dict[str, Any]:
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

    def get_rtus(self) -> List[Dict[str, Any]]:
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

    def get_alarms(self) -> List[Dict[str, Any]]:
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

    def get_pid_loops(self) -> List[Dict[str, Any]]:
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
        """Send command to controller"""
        if not self.mm:
            return False

        self._command_seq += 1

        # Build command based on type
        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        struct.pack_into('II', cmd_data, 0, self._command_seq, cmd_type)

        if cmd_type == SHM_CMD_ACTUATOR:
            station = kwargs['station'].encode('utf-8')[:63]
            struct.pack_into('64sibb', cmd_data, 8, station, kwargs['slot'],
                           kwargs['command'], kwargs.get('pwm_duty', 0))
        elif cmd_type == SHM_CMD_SETPOINT:
            struct.pack_into('if', cmd_data, 8, kwargs['loop_id'], kwargs['setpoint'])
        elif cmd_type == SHM_CMD_PID_MODE:
            struct.pack_into('ii', cmd_data, 8, kwargs['loop_id'], kwargs['mode'])
        elif cmd_type == SHM_CMD_ACK_ALARM:
            user = kwargs['user'].encode('utf-8')[:63]
            struct.pack_into('i64s', cmd_data, 8, kwargs['alarm_id'], user)
        elif cmd_type == SHM_CMD_RESET_INTERLOCK:
            struct.pack_into('i', cmd_data, 8, kwargs['interlock_id'])

        # Write command to shared memory
        cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
        self.mm.seek(cmd_offset)
        self.mm.write(bytes(cmd_data))

        # Update sequence
        seq_offset = cmd_offset + ctypes.sizeof(ShmCommand)
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

    def get_rtu(self, station_name: str) -> Optional[Dict[str, Any]]:
        """Get a single RTU by station name"""
        rtus = self.get_rtus()
        for rtu in rtus:
            if rtu["station_name"] == station_name:
                return rtu
        return None

    def get_sensors(self, station_name: str) -> List[Dict[str, Any]]:
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
            sensors.append({
                "slot": sensor["slot"],
                "value": sensor["value"],
                "status": SENSOR_STATUS_NAMES.get(sensor["status"], "unknown"),
                "status_code": sensor["status"],
                "timestamp_ms": sensor["timestamp_ms"],
                "quality": "good" if sensor["status"] == SENSOR_STATUS_GOOD else "bad",
            })
        return sensors

    def get_actuators(self, station_name: str) -> List[Dict[str, Any]]:
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

    def get_sensor_value(self, station_name: str, slot: int) -> Optional[Dict[str, Any]]:
        """Get a specific sensor value by station and slot"""
        sensors = self.get_sensors(station_name)
        for sensor in sensors:
            if sensor["slot"] == slot:
                return sensor
        return None

    def get_actuator_state(self, station_name: str, slot: int) -> Optional[Dict[str, Any]]:
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
        """Internal helper for RTU management commands"""
        self._command_seq += 1

        cmd_data = bytearray(256)  # Fixed command buffer
        struct.pack_into('II', cmd_data, 0, self._command_seq, cmd_type)

        # Pack station name (64 bytes)
        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}s', cmd_data, 8, station_bytes)

        # Pack additional data for ADD_RTU
        if cmd_type == SHM_CMD_ADD_RTU:
            ip_bytes = ip_address.encode('utf-8')[:15]
            struct.pack_into(f'{len(ip_bytes)}s', cmd_data, 72, ip_bytes)
            struct.pack_into('HHI', cmd_data, 88, vendor_id, device_id, slot_count)

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

    def dcp_discover(self, timeout_ms: int = 3000) -> List[Dict[str, Any]]:
        """
        Send DCP Identify All request to discover PROFINET devices.
        Returns list of discovered devices with station_name, ip_address, mac_address.

        Note: This sends the command to the C controller which performs the actual
        DCP multicast. Results are returned via shared memory discovery buffer.
        """
        if not self.mm:
            logger.warning("Cannot perform DCP discovery: shared memory not connected")
            return []

        logger.info(f"Initiating DCP discovery (timeout: {timeout_ms}ms)")
        self._command_seq += 1

        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        struct.pack_into('III', cmd_data, 0, self._command_seq, SHM_CMD_DCP_DISCOVER, timeout_ms)

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data))

            # In production, we would wait for response in discovery buffer
            # For now, return empty list - controller will populate discovery results
            logger.info("DCP discovery command sent, awaiting controller response")
            return []
        except Exception as e:
            logger.error(f"Failed to send DCP discover command: {e}")
            return []

    def discover_i2c(self, station_name: str, bus: int = 1) -> List[Dict[str, Any]]:
        """
        Request I2C bus scan from RTU.
        RTU will probe standard addresses and report found devices.
        """
        if not self.mm:
            logger.warning("Cannot discover I2C: shared memory not connected")
            return []

        logger.info(f"Requesting I2C discovery on {station_name} bus {bus}")
        self._command_seq += 1

        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        struct.pack_into('II', cmd_data, 0, self._command_seq, SHM_CMD_I2C_DISCOVER)
        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}si', cmd_data, 8, station_bytes, bus)

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data))
            logger.info("I2C discovery command sent")
            return []
        except Exception as e:
            logger.error(f"Failed to send I2C discover command: {e}")
            return []

    def discover_onewire(self, station_name: str) -> List[Dict[str, Any]]:
        """
        Request 1-Wire bus scan from RTU.
        RTU will enumerate all 1-Wire devices and report their ROM IDs.
        """
        if not self.mm:
            logger.warning("Cannot discover 1-Wire: shared memory not connected")
            return []

        logger.info(f"Requesting 1-Wire discovery on {station_name}")
        self._command_seq += 1

        cmd_data = bytearray(ctypes.sizeof(ShmCommand))
        struct.pack_into('II', cmd_data, 0, self._command_seq, SHM_CMD_ONEWIRE_DISCOVER)
        station_bytes = station_name.encode('utf-8')[:63]
        struct.pack_into(f'{len(station_bytes)}s', cmd_data, 8, station_bytes)

        try:
            cmd_offset = ctypes.sizeof(WtcSharedMemory) - ctypes.sizeof(ShmCommand) - 8
            self.mm.seek(cmd_offset)
            self.mm.write(bytes(cmd_data))
            logger.info("1-Wire discovery command sent")
            return []
        except Exception as e:
            logger.error(f"Failed to send 1-Wire discover command: {e}")
            return []

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


# Global client instance
_client: Optional[WtcShmClient] = None


def get_client() -> WtcShmClient:
    """Get or create shared memory client"""
    global _client
    if _client is None:
        _client = WtcShmClient()
        _client.connect()
    elif not _client.is_connected():
        _client.connect()
    return _client
