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
    """

    def __init__(self):
        self._clients: dict[str, ModbusClient] = {}

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

        if not client.connect():
            raise CommunicationError(f"Failed to connect to device '{device_name}'")

        self._clients[device_name] = client
        return client

    def read_registers(
        self,
        device_name: str,
        register_type: str,
        start_addr: int,
        count: int = 1
    ) -> list[dict[str, Any]]:
        """
        Read registers from a downstream device.

        Returns list of {address, value} dicts.
        """
        device = self.get_device_by_name(device_name)
        client = self._get_client(device_name)

        values = client.read_registers(
            unit_id=device["slave_addr"],
            register_type=register_type,
            start_addr=start_addr,
            count=count
        )

        return [
            {"address": start_addr + i, "value": v}
            for i, v in enumerate(values)
        ]

    def write_register(
        self,
        device_name: str,
        register_type: str,
        addr: int,
        value: int
    ) -> bool:
        """Write a single register to a downstream device."""
        device = self.get_device_by_name(device_name)
        client = self._get_client(device_name)

        return client.write_register(
            unit_id=device["slave_addr"],
            register_type=register_type,
            addr=addr,
            value=value
        )

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
