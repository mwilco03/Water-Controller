"""
Water Treatment Controller - Modbus Service
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

High-level Modbus client service for register read/write operations.
Wraps the persistence layer and provides IPC communication with the C gateway.
"""

import logging
import socket
import struct
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..core.exceptions import CommunicationError, NotFoundError, ValidationError
from ..persistence import modbus as modbus_persistence

logger = logging.getLogger(__name__)

# Modbus function codes
FC_READ_COILS = 0x01
FC_READ_DISCRETE_INPUTS = 0x02
FC_READ_HOLDING_REGISTERS = 0x03
FC_READ_INPUT_REGISTERS = 0x04
FC_WRITE_SINGLE_COIL = 0x05
FC_WRITE_SINGLE_REGISTER = 0x06
FC_WRITE_MULTIPLE_COILS = 0x0F
FC_WRITE_MULTIPLE_REGISTERS = 0x10

# Register type to function code mapping
READ_FC_MAP = {
    "coil": FC_READ_COILS,
    "discrete": FC_READ_DISCRETE_INPUTS,
    "holding": FC_READ_HOLDING_REGISTERS,
    "input": FC_READ_INPUT_REGISTERS,
}

WRITE_FC_MAP = {
    "coil": FC_WRITE_SINGLE_COIL,
    "holding": FC_WRITE_SINGLE_REGISTER,
}

# Data type definitions
DATA_TYPES = {
    "uint16": {"size": 1, "signed": False, "format": ">H"},
    "int16": {"size": 1, "signed": True, "format": ">h"},
    "uint32": {"size": 2, "signed": False, "format": ">I"},
    "int32": {"size": 2, "signed": True, "format": ">i"},
    "uint32_le": {"size": 2, "signed": False, "format": "<I", "swap": True},
    "int32_le": {"size": 2, "signed": True, "format": "<i", "swap": True},
    "float32": {"size": 2, "signed": False, "format": ">f"},
    "float32_le": {"size": 2, "signed": False, "format": "<f", "swap": True},
}


class RegisterQuality(Enum):
    """Quality status for register values."""
    GOOD = "good"              # Value read successfully
    BAD = "bad"                # Read failed, value stale
    UNCERTAIN = "uncertain"    # Read succeeded but device reports issues
    NOT_UPDATED = "not_updated"  # Never been read
    COMM_FAILURE = "comm_failure"  # Device unreachable


@dataclass
class RegisterStatus:
    """Status tracking for a single register or register group."""
    address: int
    register_type: str
    quality: RegisterQuality = RegisterQuality.NOT_UPDATED
    value: Any = None
    raw_value: int | None = None
    last_update: datetime | None = None
    last_good_value: Any = None
    last_good_time: datetime | None = None
    error_count: int = 0
    success_count: int = 0
    last_error: str | None = None
    latency_ms: float | None = None

    def update_success(self, value: Any, raw_value: int | None, latency_ms: float) -> None:
        """Update status after successful read."""
        self.quality = RegisterQuality.GOOD
        self.value = value
        self.raw_value = raw_value
        self.last_update = datetime.now(UTC)
        self.last_good_value = value
        self.last_good_time = self.last_update
        self.success_count += 1
        self.latency_ms = latency_ms
        self.last_error = None

    def update_failure(self, error: str) -> None:
        """Update status after failed read."""
        self.quality = RegisterQuality.BAD
        self.last_update = datetime.now(UTC)
        self.error_count += 1
        self.last_error = error
        self.latency_ms = None

    def update_comm_failure(self, error: str) -> None:
        """Update status for communication failure."""
        self.quality = RegisterQuality.COMM_FAILURE
        self.last_update = datetime.now(UTC)
        self.error_count += 1
        self.last_error = error
        self.latency_ms = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = self.success_count + self.error_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100.0

    @property
    def is_stale(self) -> bool:
        """Check if value is stale (not updated in 30 seconds)."""
        if self.last_update is None:
            return True
        age = (datetime.now(UTC) - self.last_update).total_seconds()
        return age > 30.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "address": self.address,
            "register_type": self.register_type,
            "quality": self.quality.value,
            "value": self.value,
            "raw_value": self.raw_value,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "last_good_value": self.last_good_value,
            "last_good_time": self.last_good_time.isoformat() if self.last_good_time else None,
            "error_count": self.error_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 1),
            "last_error": self.last_error,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms else None,
            "is_stale": self.is_stale,
        }


@dataclass
class DeviceQualityTracker:
    """Quality tracking for a Modbus device."""
    device_name: str
    registers: dict[str, RegisterStatus] = field(default_factory=dict)
    connection_attempts: int = 0
    connection_successes: int = 0
    last_connection_time: datetime | None = None
    last_communication_time: datetime | None = None
    total_read_count: int = 0
    total_write_count: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0
    _latency_samples: list[float] = field(default_factory=list)

    def _register_key(self, register_type: str, address: int) -> str:
        """Generate unique key for register lookup."""
        return f"{register_type}:{address}"

    def get_register_status(self, register_type: str, address: int) -> RegisterStatus:
        """Get or create register status tracker."""
        key = self._register_key(register_type, address)
        if key not in self.registers:
            self.registers[key] = RegisterStatus(
                address=address,
                register_type=register_type
            )
        return self.registers[key]

    def record_read_success(
        self,
        register_type: str,
        address: int,
        value: Any,
        raw_value: int | None,
        latency_ms: float
    ) -> None:
        """Record successful register read."""
        status = self.get_register_status(register_type, address)
        status.update_success(value, raw_value, latency_ms)
        self.total_read_count += 1
        self.last_communication_time = datetime.now(UTC)
        self._update_avg_latency(latency_ms)

    def record_read_failure(
        self,
        register_type: str,
        address: int,
        error: str,
        is_comm_failure: bool = False
    ) -> None:
        """Record failed register read."""
        status = self.get_register_status(register_type, address)
        if is_comm_failure:
            status.update_comm_failure(error)
        else:
            status.update_failure(error)
        self.total_errors += 1

    def record_write_success(self, latency_ms: float) -> None:
        """Record successful write operation."""
        self.total_write_count += 1
        self.last_communication_time = datetime.now(UTC)
        self._update_avg_latency(latency_ms)

    def record_connection_attempt(self, success: bool) -> None:
        """Record connection attempt."""
        self.connection_attempts += 1
        if success:
            self.connection_successes += 1
            self.last_connection_time = datetime.now(UTC)

    def _update_avg_latency(self, latency_ms: float) -> None:
        """Update rolling average latency (last 100 samples)."""
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 100:
            self._latency_samples.pop(0)
        self.avg_latency_ms = sum(self._latency_samples) / len(self._latency_samples)

    @property
    def connection_rate(self) -> float:
        """Calculate connection success rate."""
        if self.connection_attempts == 0:
            return 0.0
        return (self.connection_successes / self.connection_attempts) * 100.0

    @property
    def overall_quality(self) -> RegisterQuality:
        """Determine overall device quality based on recent operations."""
        if not self.registers:
            return RegisterQuality.NOT_UPDATED

        qualities = [r.quality for r in self.registers.values()]

        # If any register has comm failure, device has comm failure
        if RegisterQuality.COMM_FAILURE in qualities:
            return RegisterQuality.COMM_FAILURE

        # If all bad, device is bad
        if all(q == RegisterQuality.BAD for q in qualities):
            return RegisterQuality.BAD

        # If all good, device is good
        if all(q == RegisterQuality.GOOD for q in qualities):
            return RegisterQuality.GOOD

        # Mixed results = uncertain
        return RegisterQuality.UNCERTAIN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "device_name": self.device_name,
            "overall_quality": self.overall_quality.value,
            "connection_rate": round(self.connection_rate, 1),
            "connection_attempts": self.connection_attempts,
            "last_connection_time": self.last_connection_time.isoformat() if self.last_connection_time else None,
            "last_communication_time": self.last_communication_time.isoformat() if self.last_communication_time else None,
            "total_read_count": self.total_read_count,
            "total_write_count": self.total_write_count,
            "total_errors": self.total_errors,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "register_count": len(self.registers),
            "registers": {k: v.to_dict() for k, v in self.registers.items()},
        }

    def get_summary(self) -> dict[str, Any]:
        """Get summary without detailed register data."""
        good_count = sum(1 for r in self.registers.values() if r.quality == RegisterQuality.GOOD)
        bad_count = sum(1 for r in self.registers.values() if r.quality == RegisterQuality.BAD)
        stale_count = sum(1 for r in self.registers.values() if r.is_stale)

        return {
            "device_name": self.device_name,
            "overall_quality": self.overall_quality.value,
            "connection_rate": round(self.connection_rate, 1),
            "total_read_count": self.total_read_count,
            "total_write_count": self.total_write_count,
            "total_errors": self.total_errors,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "register_count": len(self.registers),
            "good_registers": good_count,
            "bad_registers": bad_count,
            "stale_registers": stale_count,
        }


class DataTypeConverter:
    """
    Converts between Modbus register values and typed data.

    Supports:
    - uint16/int16: Single 16-bit register
    - uint32/int32: Two 16-bit registers (big-endian)
    - uint32_le/int32_le: Two 16-bit registers (little-endian, word-swapped)
    - float32: IEEE 754 float (big-endian)
    - float32_le: IEEE 754 float (little-endian, word-swapped)
    """

    @staticmethod
    def registers_to_value(
        registers: list[int],
        data_type: str = "uint16"
    ) -> int | float:
        """
        Convert Modbus registers to typed value.

        Args:
            registers: List of 16-bit register values
            data_type: Data type name

        Returns:
            Converted value (int or float)
        """
        type_info = DATA_TYPES.get(data_type)
        if not type_info:
            raise ValidationError(f"Unknown data type: {data_type}")

        size = type_info["size"]
        if len(registers) < size:
            raise ValidationError(f"Not enough registers for {data_type}: need {size}, got {len(registers)}")

        # Pack registers into bytes
        if type_info.get("swap"):
            # Word-swapped (little-endian word order)
            raw_bytes = b""
            for reg in reversed(registers[:size]):
                raw_bytes += struct.pack(">H", reg)
        else:
            # Big-endian word order
            raw_bytes = b""
            for reg in registers[:size]:
                raw_bytes += struct.pack(">H", reg)

        # Unpack as typed value
        fmt = type_info["format"]
        value = struct.unpack(fmt, raw_bytes)[0]

        return value

    @staticmethod
    def value_to_registers(
        value: int | float,
        data_type: str = "uint16"
    ) -> list[int]:
        """
        Convert typed value to Modbus registers.

        Args:
            value: Value to convert
            data_type: Data type name

        Returns:
            List of 16-bit register values
        """
        type_info = DATA_TYPES.get(data_type)
        if not type_info:
            raise ValidationError(f"Unknown data type: {data_type}")

        size = type_info["size"]
        fmt = type_info["format"]

        # Pack value to bytes
        raw_bytes = struct.pack(fmt, value)

        # Unpack as 16-bit registers
        registers = []
        for i in range(size):
            reg_bytes = raw_bytes[i * 2:(i + 1) * 2]
            registers.append(struct.unpack(">H", reg_bytes)[0])

        # Word-swap if needed
        if type_info.get("swap"):
            registers.reverse()

        return registers

    @staticmethod
    def apply_scaling(
        raw_value: int | float,
        raw_min: float,
        raw_max: float,
        eng_min: float,
        eng_max: float
    ) -> float:
        """
        Apply linear scaling to convert raw value to engineering units.

        Args:
            raw_value: Raw register value
            raw_min: Minimum raw value
            raw_max: Maximum raw value
            eng_min: Minimum engineering value
            eng_max: Maximum engineering value

        Returns:
            Scaled engineering value
        """
        if raw_max == raw_min:
            return eng_min

        ratio = (raw_value - raw_min) / (raw_max - raw_min)
        return eng_min + ratio * (eng_max - eng_min)

    @staticmethod
    def reverse_scaling(
        eng_value: float,
        raw_min: float,
        raw_max: float,
        eng_min: float,
        eng_max: float
    ) -> float:
        """
        Reverse linear scaling to convert engineering units to raw value.

        Args:
            eng_value: Engineering value
            raw_min: Minimum raw value
            raw_max: Maximum raw value
            eng_min: Minimum engineering value
            eng_max: Maximum engineering value

        Returns:
            Raw register value
        """
        if eng_max == eng_min:
            return raw_min

        ratio = (eng_value - eng_min) / (eng_max - eng_min)
        return raw_min + ratio * (raw_max - raw_min)


class ModbusClient:
    """
    Modbus TCP client for communicating with downstream devices.

    This client is used to read/write registers from Modbus devices
    configured as downstream devices in the system.
    """

    def __init__(self, host: str, port: int = 502, timeout: float = 1.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._transaction_id = 0

    def connect(self) -> bool:
        """Establish TCP connection to Modbus device."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            logger.info(f"Connected to Modbus device at {self.host}:{self.port}")
            return True
        except socket.error as e:
            logger.error(f"Failed to connect to Modbus device: {e}")
            self._socket = None
            return False

    def disconnect(self):
        """Close TCP connection."""
        if self._socket:
            try:
                self._socket.close()
            except socket.error:
                pass
            self._socket = None

    def is_connected(self) -> bool:
        """Check if connected to device."""
        return self._socket is not None

    def _next_transaction_id(self) -> int:
        """Get next transaction ID (wraps at 65535)."""
        self._transaction_id = (self._transaction_id + 1) % 65536
        return self._transaction_id

    def _build_request(
        self,
        unit_id: int,
        function_code: int,
        start_addr: int,
        quantity: int
    ) -> bytes:
        """Build Modbus TCP request frame."""
        tid = self._next_transaction_id()
        # MBAP Header: transaction_id(2) + protocol_id(2) + length(2) + unit_id(1)
        # PDU: function_code(1) + start_addr(2) + quantity(2)
        pdu = struct.pack(">BHH", function_code, start_addr, quantity)
        mbap = struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit_id)
        return mbap + pdu

    def _build_write_request(
        self,
        unit_id: int,
        function_code: int,
        addr: int,
        value: int
    ) -> bytes:
        """Build Modbus TCP write request frame."""
        tid = self._next_transaction_id()
        pdu = struct.pack(">BHH", function_code, addr, value)
        mbap = struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit_id)
        return mbap + pdu

    def _send_receive(self, request: bytes) -> bytes:
        """Send request and receive response."""
        if not self._socket:
            raise CommunicationError("Not connected to Modbus device")

        try:
            self._socket.sendall(request)

            # Receive MBAP header (7 bytes)
            header = self._socket.recv(7)
            if len(header) < 7:
                raise CommunicationError("Incomplete Modbus header received")

            tid, protocol, length, unit_id = struct.unpack(">HHHB", header)

            # Receive PDU
            pdu = self._socket.recv(length - 1)
            if len(pdu) < length - 1:
                raise CommunicationError("Incomplete Modbus PDU received")

            # Check for exception response
            if pdu[0] & 0x80:
                exception_code = pdu[1] if len(pdu) > 1 else 0
                raise CommunicationError(f"Modbus exception: code {exception_code}")

            return pdu

        except socket.timeout:
            raise CommunicationError("Modbus request timeout")
        except socket.error as e:
            raise CommunicationError(f"Modbus communication error: {e}")

    def read_registers(
        self,
        unit_id: int,
        register_type: str,
        start_addr: int,
        count: int = 1
    ) -> list[int]:
        """
        Read registers from device.

        Args:
            unit_id: Modbus unit/slave ID
            register_type: 'holding', 'input', 'coil', or 'discrete'
            start_addr: Starting register address
            count: Number of registers to read

        Returns:
            List of register values
        """
        fc = READ_FC_MAP.get(register_type)
        if fc is None:
            raise ValidationError(f"Invalid register type: {register_type}")

        request = self._build_request(unit_id, fc, start_addr, count)
        response = self._send_receive(request)

        # Parse response based on register type
        if register_type in ("coil", "discrete"):
            # Bit values packed in bytes
            byte_count = response[1]
            values = []
            for i in range(count):
                byte_idx = i // 8
                bit_idx = i % 8
                if byte_idx + 2 < len(response):
                    values.append((response[byte_idx + 2] >> bit_idx) & 1)
            return values
        else:
            # Word values (2 bytes each)
            byte_count = response[1]
            values = []
            for i in range(count):
                offset = 2 + i * 2
                if offset + 1 < len(response):
                    values.append(struct.unpack(">H", response[offset:offset + 2])[0])
            return values

    def write_register(
        self,
        unit_id: int,
        register_type: str,
        addr: int,
        value: int
    ) -> bool:
        """
        Write single register to device.

        Args:
            unit_id: Modbus unit/slave ID
            register_type: 'holding' or 'coil'
            addr: Register address
            value: Value to write

        Returns:
            True if successful
        """
        fc = WRITE_FC_MAP.get(register_type)
        if fc is None:
            raise ValidationError(f"Cannot write to register type: {register_type}")

        # For coils, convert value to Modbus coil format
        if register_type == "coil":
            value = 0xFF00 if value else 0x0000

        request = self._build_write_request(unit_id, fc, addr, value)
        self._send_receive(request)
        return True


class ModbusService:
    """
    High-level Modbus service for managing devices and register operations.

    Provides:
    - Server configuration management
    - Downstream device management
    - Register mapping management
    - Read/write operations to downstream devices
    - Quality tracking for all registers
    """

    def __init__(self):
        self._clients: dict[str, ModbusClient] = {}
        self._quality_trackers: dict[str, DeviceQualityTracker] = {}

    # ============== Quality Tracking ==============

    def _get_quality_tracker(self, device_name: str) -> DeviceQualityTracker:
        """Get or create quality tracker for a device."""
        if device_name not in self._quality_trackers:
            self._quality_trackers[device_name] = DeviceQualityTracker(
                device_name=device_name
            )
        return self._quality_trackers[device_name]

    def get_device_quality(self, device_name: str) -> dict[str, Any]:
        """Get quality tracking data for a device."""
        tracker = self._get_quality_tracker(device_name)
        return tracker.to_dict()

    def get_device_quality_summary(self, device_name: str) -> dict[str, Any]:
        """Get quality summary for a device (without detailed register data)."""
        tracker = self._get_quality_tracker(device_name)
        return tracker.get_summary()

    def get_all_quality_summaries(self) -> list[dict[str, Any]]:
        """Get quality summaries for all tracked devices."""
        return [tracker.get_summary() for tracker in self._quality_trackers.values()]

    def get_register_quality(
        self,
        device_name: str,
        register_type: str,
        address: int
    ) -> dict[str, Any]:
        """Get quality status for a specific register."""
        tracker = self._get_quality_tracker(device_name)
        status = tracker.get_register_status(register_type, address)
        return status.to_dict()

    def reset_quality_tracking(self, device_name: str | None = None) -> None:
        """Reset quality tracking data for a device or all devices."""
        if device_name:
            if device_name in self._quality_trackers:
                self._quality_trackers[device_name] = DeviceQualityTracker(
                    device_name=device_name
                )
        else:
            self._quality_trackers.clear()

    # ============== Server Configuration ==============

    def get_server_config(self) -> dict[str, Any]:
        """Get Modbus server configuration."""
        config = modbus_persistence.get_modbus_server_config()
        if not config:
            # Return defaults
            return {
                "tcp_enabled": True,
                "tcp_port": 502,
                "tcp_bind_address": "0.0.0.0",
                "rtu_enabled": False,
            }
        return config

    def update_server_config(self, config: dict[str, Any]) -> bool:
        """Update Modbus server configuration."""
        return modbus_persistence.update_modbus_server_config(config)

    # ============== Downstream Devices ==============

    def get_devices(self) -> list[dict[str, Any]]:
        """Get all downstream Modbus devices."""
        return modbus_persistence.get_modbus_downstream_devices()

    def get_device(self, device_id: int) -> dict[str, Any]:
        """Get a specific downstream device by ID."""
        devices = modbus_persistence.get_modbus_downstream_devices()
        for device in devices:
            if device["id"] == device_id:
                return device
        raise NotFoundError(f"Modbus device not found: {device_id}")

    def get_device_by_name(self, name: str) -> dict[str, Any]:
        """Get a specific downstream device by name."""
        devices = modbus_persistence.get_modbus_downstream_devices()
        for device in devices:
            if device["name"] == name:
                return device
        raise NotFoundError(f"Modbus device not found: {name}")

    def create_device(self, device: dict[str, Any]) -> int:
        """Create a new downstream device."""
        # Validate required fields
        if not device.get("name"):
            raise ValidationError("Device name is required")
        if not device.get("transport") in ("tcp", "rtu"):
            raise ValidationError("Transport must be 'tcp' or 'rtu'")
        if device["transport"] == "tcp" and not device.get("tcp_host"):
            raise ValidationError("TCP host is required for TCP transport")
        if "slave_addr" not in device:
            raise ValidationError("Slave address is required")

        return modbus_persistence.create_modbus_downstream_device(device)

    def update_device(self, device_id: int, device: dict[str, Any]) -> bool:
        """Update a downstream device."""
        # Validate device exists
        self.get_device(device_id)

        # Invalidate cached client if exists
        devices = modbus_persistence.get_modbus_downstream_devices()
        for d in devices:
            if d["id"] == device_id and d["name"] in self._clients:
                self._clients[d["name"]].disconnect()
                del self._clients[d["name"]]

        return modbus_persistence.update_modbus_downstream_device(device_id, device)

    def delete_device(self, device_id: int) -> bool:
        """Delete a downstream device."""
        device = self.get_device(device_id)

        # Disconnect and remove cached client
        if device["name"] in self._clients:
            self._clients[device["name"]].disconnect()
            del self._clients[device["name"]]

        return modbus_persistence.delete_modbus_downstream_device(device_id)

    # ============== Register Mappings ==============

    def get_mappings(self) -> list[dict[str, Any]]:
        """Get all register mappings."""
        return modbus_persistence.get_modbus_register_mappings()

    def get_mapping(self, mapping_id: int) -> dict[str, Any]:
        """Get a specific register mapping by ID."""
        mappings = modbus_persistence.get_modbus_register_mappings()
        for mapping in mappings:
            if mapping["id"] == mapping_id:
                return mapping
        raise NotFoundError(f"Register mapping not found: {mapping_id}")

    def create_mapping(self, mapping: dict[str, Any]) -> int:
        """Create a new register mapping."""
        # Validate required fields
        required = ["modbus_addr", "register_type", "data_type", "source_type", "rtu_station", "slot"]
        for field in required:
            if field not in mapping:
                raise ValidationError(f"Field '{field}' is required")

        valid_types = ("holding", "input", "coil", "discrete")
        if mapping["register_type"] not in valid_types:
            raise ValidationError(f"register_type must be one of: {valid_types}")

        return modbus_persistence.create_modbus_register_mapping(mapping)

    def update_mapping(self, mapping_id: int, mapping: dict[str, Any]) -> bool:
        """Update a register mapping."""
        self.get_mapping(mapping_id)
        return modbus_persistence.update_modbus_register_mapping(mapping_id, mapping)

    def delete_mapping(self, mapping_id: int) -> bool:
        """Delete a register mapping."""
        self.get_mapping(mapping_id)
        return modbus_persistence.delete_modbus_register_mapping(mapping_id)

    # ============== Register Operations ==============

    def _get_client(self, device_name: str) -> ModbusClient:
        """Get or create Modbus client for a device."""
        tracker = self._get_quality_tracker(device_name)

        if device_name in self._clients:
            client = self._clients[device_name]
            if client.is_connected():
                return client

        device = self.get_device_by_name(device_name)

        if device["transport"] != "tcp":
            raise CommunicationError("Only TCP transport is currently supported")

        if not device.get("enabled", True):
            raise CommunicationError(f"Device '{device_name}' is disabled")

        client = ModbusClient(
            host=device["tcp_host"],
            port=device.get("tcp_port", 502),
            timeout=device.get("timeout_ms", 1000) / 1000.0
        )

        connected = client.connect()
        tracker.record_connection_attempt(connected)

        if not connected:
            raise CommunicationError(f"Failed to connect to device '{device_name}'")

        self._clients[device_name] = client
        return client

    def read_registers(
        self,
        device_name: str,
        register_type: str,
        start_addr: int,
        count: int = 1,
        track_quality: bool = True
    ) -> list[dict[str, Any]]:
        """
        Read registers from a downstream device.

        Returns list of {address, value, quality} dicts.
        """
        tracker = self._get_quality_tracker(device_name)
        device = self.get_device_by_name(device_name)

        try:
            client = self._get_client(device_name)
        except CommunicationError as e:
            if track_quality:
                for i in range(count):
                    tracker.record_read_failure(
                        register_type, start_addr + i,
                        str(e), is_comm_failure=True
                    )
            raise

        start_time = time.perf_counter()
        try:
            values = client.read_registers(
                unit_id=device["slave_addr"],
                register_type=register_type,
                start_addr=start_addr,
                count=count
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            result = []
            for i, v in enumerate(values):
                addr = start_addr + i
                if track_quality:
                    tracker.record_read_success(
                        register_type, addr, v, v, latency_ms
                    )
                result.append({
                    "address": addr,
                    "value": v,
                    "quality": RegisterQuality.GOOD.value,
                })
            return result

        except CommunicationError as e:
            if track_quality:
                for i in range(count):
                    tracker.record_read_failure(
                        register_type, start_addr + i,
                        str(e), is_comm_failure=True
                    )
            raise

    def read_typed_value(
        self,
        device_name: str,
        register_type: str,
        start_addr: int,
        data_type: str = "uint16",
        scaling: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """
        Read a typed value from registers with optional scaling.

        Args:
            device_name: Device name
            register_type: Register type (holding, input)
            start_addr: Starting register address
            data_type: Data type (uint16, int16, uint32, int32, float32, etc.)
            scaling: Optional scaling dict with raw_min, raw_max, eng_min, eng_max

        Returns:
            Dict with address, raw_value, value, data_type, and optional scaled_value
        """
        type_info = DATA_TYPES.get(data_type)
        if not type_info:
            raise ValidationError(f"Unknown data type: {data_type}")

        count = type_info["size"]

        # Read raw registers
        registers = self.read_registers(device_name, register_type, start_addr, count)
        raw_values = [r["value"] for r in registers]

        # Convert to typed value
        value = DataTypeConverter.registers_to_value(raw_values, data_type)

        result = {
            "address": start_addr,
            "data_type": data_type,
            "raw_registers": raw_values,
            "value": value,
        }

        # Apply scaling if provided
        if scaling:
            scaled = DataTypeConverter.apply_scaling(
                value,
                scaling.get("raw_min", 0),
                scaling.get("raw_max", 65535),
                scaling.get("eng_min", 0),
                scaling.get("eng_max", 100)
            )
            result["scaled_value"] = scaled

        return result

    def write_typed_value(
        self,
        device_name: str,
        register_type: str,
        addr: int,
        value: int | float,
        data_type: str = "uint16"
    ) -> bool:
        """
        Write a typed value to registers.

        Args:
            device_name: Device name
            register_type: Register type (holding)
            addr: Starting register address
            value: Value to write
            data_type: Data type (uint16, int16, uint32, int32, float32, etc.)

        Returns:
            True if successful
        """
        type_info = DATA_TYPES.get(data_type)
        if not type_info:
            raise ValidationError(f"Unknown data type: {data_type}")

        # Convert value to registers
        registers = DataTypeConverter.value_to_registers(value, data_type)

        device = self.get_device_by_name(device_name)
        client = self._get_client(device_name)

        # Write registers (multiple if needed)
        if len(registers) == 1:
            return client.write_register(
                unit_id=device["slave_addr"],
                register_type=register_type,
                addr=addr,
                value=registers[0]
            )
        else:
            # For multi-register writes, write each register
            # Writes registers individually; batch FC 0x10 deferred until profiled
            for i, reg_value in enumerate(registers):
                client.write_register(
                    unit_id=device["slave_addr"],
                    register_type=register_type,
                    addr=addr + i,
                    value=reg_value
                )
            return True

    def write_register(
        self,
        device_name: str,
        register_type: str,
        addr: int,
        value: int
    ) -> bool:
        """Write a single register to a downstream device."""
        tracker = self._get_quality_tracker(device_name)
        device = self.get_device_by_name(device_name)

        try:
            client = self._get_client(device_name)
        except CommunicationError:
            tracker.total_errors += 1
            raise

        start_time = time.perf_counter()
        try:
            result = client.write_register(
                unit_id=device["slave_addr"],
                register_type=register_type,
                addr=addr,
                value=value
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            tracker.record_write_success(latency_ms)
            return result
        except CommunicationError:
            tracker.total_errors += 1
            raise

    def get_gateway_status(self) -> dict[str, Any]:
        """
        Get Modbus gateway status.

        Returns status of server and all downstream devices.
        """
        config = self.get_server_config()
        devices = self.get_devices()

        device_status = []
        for device in devices:
            status = {
                "name": device["name"],
                "enabled": device.get("enabled", True),
                "connected": device["name"] in self._clients and self._clients[device["name"]].is_connected(),
                "transport": device["transport"],
            }
            if device["transport"] == "tcp":
                status["host"] = device.get("tcp_host")
                status["port"] = device.get("tcp_port", 502)
            device_status.append(status)

        return {
            "server": {
                "tcp_enabled": config.get("tcp_enabled", True),
                "tcp_port": config.get("tcp_port", 502),
                "rtu_enabled": config.get("rtu_enabled", False),
            },
            "devices": device_status,
            "mapping_count": len(self.get_mappings()),
        }


# Global service instance
_modbus_service: ModbusService | None = None


def get_modbus_service() -> ModbusService:
    """Get or create the Modbus service."""
    global _modbus_service
    if _modbus_service is None:
        _modbus_service = ModbusService()
    return _modbus_service
