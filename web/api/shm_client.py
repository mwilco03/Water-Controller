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
