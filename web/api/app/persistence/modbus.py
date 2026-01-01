"""
Water Treatment Controller - Modbus Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Modbus server config, downstream devices, and register mappings using SQLAlchemy.
"""

from datetime import UTC, datetime
from typing import Any

from ..models.config import (
    ModbusDownstreamDevice,
    ModbusRegisterMapping,
    ModbusServerConfig,
)
from .audit import log_audit
from .base import get_db


def _config_to_dict(config: ModbusServerConfig) -> dict[str, Any]:
    """Convert ModbusServerConfig to dictionary."""
    return {
        "id": config.id,
        "tcp_enabled": config.tcp_enabled,
        "tcp_port": config.tcp_port,
        "tcp_bind_address": config.tcp_bind_address,
        "rtu_enabled": config.rtu_enabled,
        "rtu_device": config.rtu_device,
        "rtu_baud_rate": config.rtu_baud_rate,
        "rtu_parity": config.rtu_parity,
        "rtu_data_bits": config.rtu_data_bits,
        "rtu_stop_bits": config.rtu_stop_bits,
        "rtu_slave_addr": config.rtu_slave_addr,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def _device_to_dict(device: ModbusDownstreamDevice) -> dict[str, Any]:
    """Convert ModbusDownstreamDevice to dictionary."""
    return {
        "id": device.id,
        "name": device.name,
        "transport": device.transport,
        "tcp_host": device.tcp_host,
        "tcp_port": device.tcp_port,
        "rtu_device": device.rtu_device,
        "rtu_baud_rate": device.rtu_baud_rate,
        "slave_addr": device.slave_addr,
        "poll_interval_ms": device.poll_interval_ms,
        "timeout_ms": device.timeout_ms,
        "enabled": device.enabled,
        "description": device.description,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
    }


def _mapping_to_dict(mapping: ModbusRegisterMapping) -> dict[str, Any]:
    """Convert ModbusRegisterMapping to dictionary."""
    return {
        "id": mapping.id,
        "modbus_addr": mapping.modbus_addr,
        "register_type": mapping.register_type,
        "data_type": mapping.data_type,
        "source_type": mapping.source_type,
        "rtu_station": mapping.rtu_station,
        "slot": mapping.slot,
        "description": mapping.description,
        "scaling_enabled": mapping.scaling_enabled,
        "scale_raw_min": mapping.scale_raw_min,
        "scale_raw_max": mapping.scale_raw_max,
        "scale_eng_min": mapping.scale_eng_min,
        "scale_eng_max": mapping.scale_eng_max,
        "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
    }


# ============== Modbus Server Config ==============

def get_modbus_server_config() -> dict[str, Any]:
    """Get Modbus server configuration"""
    with get_db() as db:
        config = db.query(ModbusServerConfig).filter(ModbusServerConfig.id == 1).first()
        return _config_to_dict(config) if config else {}


def update_modbus_server_config(config: dict[str, Any]) -> bool:
    """Update Modbus server configuration"""
    with get_db() as db:
        existing = db.query(ModbusServerConfig).filter(ModbusServerConfig.id == 1).first()
        if not existing:
            existing = ModbusServerConfig(id=1)
            db.add(existing)

        existing.tcp_enabled = config.get('tcp_enabled', True)
        existing.tcp_port = config.get('tcp_port', 502)
        existing.tcp_bind_address = config.get('tcp_bind_address', '0.0.0.0')
        existing.rtu_enabled = config.get('rtu_enabled', False)
        existing.rtu_device = config.get('rtu_device', '/dev/ttyUSB0')
        existing.rtu_baud_rate = config.get('rtu_baud_rate', 9600)
        existing.rtu_parity = config.get('rtu_parity', 'N')
        existing.rtu_data_bits = config.get('rtu_data_bits', 8)
        existing.rtu_stop_bits = config.get('rtu_stop_bits', 1)
        existing.rtu_slave_addr = config.get('rtu_slave_addr', 1)
        existing.updated_at = datetime.now(UTC)

        db.commit()
        return True


# ============== Modbus Downstream Devices ==============

def get_modbus_downstream_devices() -> list[dict[str, Any]]:
    """Get all downstream Modbus devices"""
    with get_db() as db:
        devices = db.query(ModbusDownstreamDevice).order_by(ModbusDownstreamDevice.id).all()
        return [_device_to_dict(d) for d in devices]


def create_modbus_downstream_device(device: dict[str, Any]) -> int:
    """Create a new downstream Modbus device"""
    with get_db() as db:
        new_device = ModbusDownstreamDevice(
            name=device['name'],
            transport=device['transport'],
            tcp_host=device.get('tcp_host'),
            tcp_port=device.get('tcp_port', 502),
            rtu_device=device.get('rtu_device'),
            rtu_baud_rate=device.get('rtu_baud_rate', 9600),
            slave_addr=device['slave_addr'],
            poll_interval_ms=device.get('poll_interval_ms', 1000),
            timeout_ms=device.get('timeout_ms', 1000),
            enabled=device.get('enabled', True),
            description=device.get('description', ''),
        )
        db.add(new_device)
        db.commit()
        db.refresh(new_device)
        log_audit('system', 'create', 'modbus_device', device['name'],
                  f"Created Modbus device {device['name']}")
        return new_device.id


def update_modbus_downstream_device(device_id: int, device: dict[str, Any]) -> bool:
    """Update a downstream Modbus device"""
    with get_db() as db:
        existing = db.query(ModbusDownstreamDevice).filter(
            ModbusDownstreamDevice.id == device_id
        ).first()
        if not existing:
            return False

        existing.name = device['name']
        existing.transport = device['transport']
        existing.tcp_host = device.get('tcp_host')
        existing.tcp_port = device.get('tcp_port', 502)
        existing.rtu_device = device.get('rtu_device')
        existing.rtu_baud_rate = device.get('rtu_baud_rate', 9600)
        existing.slave_addr = device['slave_addr']
        existing.poll_interval_ms = device.get('poll_interval_ms', 1000)
        existing.timeout_ms = device.get('timeout_ms', 1000)
        existing.enabled = device.get('enabled', True)
        existing.description = device.get('description', '')
        existing.updated_at = datetime.now(UTC)

        db.commit()
        return True


def delete_modbus_downstream_device(device_id: int) -> bool:
    """Delete a downstream Modbus device"""
    with get_db() as db:
        device = db.query(ModbusDownstreamDevice).filter(
            ModbusDownstreamDevice.id == device_id
        ).first()
        if not device:
            return False
        db.delete(device)
        db.commit()
        return True


# ============== Modbus Register Mappings ==============

def get_modbus_register_mappings() -> list[dict[str, Any]]:
    """Get all Modbus register mappings"""
    with get_db() as db:
        mappings = db.query(ModbusRegisterMapping).order_by(
            ModbusRegisterMapping.modbus_addr
        ).all()
        return [_mapping_to_dict(m) for m in mappings]


def create_modbus_register_mapping(mapping: dict[str, Any]) -> int:
    """Create a new Modbus register mapping"""
    with get_db() as db:
        new_mapping = ModbusRegisterMapping(
            modbus_addr=mapping['modbus_addr'],
            register_type=mapping['register_type'],
            data_type=mapping['data_type'],
            source_type=mapping['source_type'],
            rtu_station=mapping['rtu_station'],
            slot=mapping['slot'],
            description=mapping.get('description', ''),
            scaling_enabled=mapping.get('scaling_enabled', False),
            scale_raw_min=mapping.get('scale_raw_min', 0),
            scale_raw_max=mapping.get('scale_raw_max', 65535),
            scale_eng_min=mapping.get('scale_eng_min', 0),
            scale_eng_max=mapping.get('scale_eng_max', 100),
        )
        db.add(new_mapping)
        db.commit()
        db.refresh(new_mapping)
        return new_mapping.id


def update_modbus_register_mapping(mapping_id: int, mapping: dict[str, Any]) -> bool:
    """Update a Modbus register mapping"""
    with get_db() as db:
        existing = db.query(ModbusRegisterMapping).filter(
            ModbusRegisterMapping.id == mapping_id
        ).first()
        if not existing:
            return False

        existing.modbus_addr = mapping['modbus_addr']
        existing.register_type = mapping['register_type']
        existing.data_type = mapping['data_type']
        existing.source_type = mapping['source_type']
        existing.rtu_station = mapping['rtu_station']
        existing.slot = mapping['slot']
        existing.description = mapping.get('description', '')
        existing.scaling_enabled = mapping.get('scaling_enabled', False)
        existing.scale_raw_min = mapping.get('scale_raw_min', 0)
        existing.scale_raw_max = mapping.get('scale_raw_max', 65535)
        existing.scale_eng_min = mapping.get('scale_eng_min', 0)
        existing.scale_eng_max = mapping.get('scale_eng_max', 100)

        db.commit()
        return True


def delete_modbus_register_mapping(mapping_id: int) -> bool:
    """Delete a Modbus register mapping"""
    with get_db() as db:
        mapping = db.query(ModbusRegisterMapping).filter(
            ModbusRegisterMapping.id == mapping_id
        ).first()
        if not mapping:
            return False
        db.delete(mapping)
        db.commit()
        return True
