"""
Water Treatment Controller - Modbus Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Modbus server config, downstream devices, and register mappings.
"""

from typing import List, Optional, Dict, Any

from .base import get_db
from .audit import log_audit


# ============== Modbus Server Config ==============

def get_modbus_server_config() -> Dict[str, Any]:
    """Get Modbus server configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_server_config WHERE id = 1')
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_modbus_server_config(config: Dict[str, Any]) -> bool:
    """Update Modbus server configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_server_config
            SET tcp_enabled = ?, tcp_port = ?, tcp_bind_address = ?, rtu_enabled = ?,
                rtu_device = ?, rtu_baud_rate = ?, rtu_parity = ?, rtu_data_bits = ?,
                rtu_stop_bits = ?, rtu_slave_addr = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (config.get('tcp_enabled', True), config.get('tcp_port', 502),
              config.get('tcp_bind_address', '0.0.0.0'),
              config.get('rtu_enabled', False), config.get('rtu_device', '/dev/ttyUSB0'),
              config.get('rtu_baud_rate', 9600), config.get('rtu_parity', 'N'),
              config.get('rtu_data_bits', 8), config.get('rtu_stop_bits', 1),
              config.get('rtu_slave_addr', 1)))
        conn.commit()
        return True


# ============== Modbus Downstream Devices ==============

def get_modbus_downstream_devices() -> List[Dict[str, Any]]:
    """Get all downstream Modbus devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_downstream_devices ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def create_modbus_downstream_device(device: Dict[str, Any]) -> int:
    """Create a new downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO modbus_downstream_devices (name, transport, tcp_host, tcp_port,
                rtu_device, rtu_baud_rate, slave_addr, poll_interval_ms, timeout_ms,
                enabled, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (device['name'], device['transport'], device.get('tcp_host'),
              device.get('tcp_port', 502), device.get('rtu_device'),
              device.get('rtu_baud_rate', 9600), device['slave_addr'],
              device.get('poll_interval_ms', 1000), device.get('timeout_ms', 1000),
              device.get('enabled', True), device.get('description', '')))
        conn.commit()
        log_audit('system', 'create', 'modbus_device', device['name'],
                  f"Created Modbus device {device['name']}")
        return cursor.lastrowid


def update_modbus_downstream_device(device_id: int, device: Dict[str, Any]) -> bool:
    """Update a downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_downstream_devices
            SET name = ?, transport = ?, tcp_host = ?, tcp_port = ?, rtu_device = ?,
                rtu_baud_rate = ?, slave_addr = ?, poll_interval_ms = ?, timeout_ms = ?,
                enabled = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (device['name'], device['transport'], device.get('tcp_host'),
              device.get('tcp_port', 502), device.get('rtu_device'),
              device.get('rtu_baud_rate', 9600), device['slave_addr'],
              device.get('poll_interval_ms', 1000), device.get('timeout_ms', 1000),
              device.get('enabled', True), device.get('description', ''), device_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_modbus_downstream_device(device_id: int) -> bool:
    """Delete a downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM modbus_downstream_devices WHERE id = ?', (device_id,))
        conn.commit()
        return cursor.rowcount > 0


# ============== Modbus Register Mappings ==============

def get_modbus_register_mappings() -> List[Dict[str, Any]]:
    """Get all Modbus register mappings"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_register_mappings ORDER BY modbus_addr')
        return [dict(row) for row in cursor.fetchall()]


def create_modbus_register_mapping(mapping: Dict[str, Any]) -> int:
    """Create a new Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO modbus_register_mappings (modbus_addr, register_type, data_type,
                source_type, rtu_station, slot, description, scaling_enabled,
                scale_raw_min, scale_raw_max, scale_eng_min, scale_eng_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (mapping['modbus_addr'], mapping['register_type'], mapping['data_type'],
              mapping['source_type'], mapping['rtu_station'], mapping['slot'],
              mapping.get('description', ''), mapping.get('scaling_enabled', False),
              mapping.get('scale_raw_min', 0), mapping.get('scale_raw_max', 65535),
              mapping.get('scale_eng_min', 0), mapping.get('scale_eng_max', 100)))
        conn.commit()
        return cursor.lastrowid


def update_modbus_register_mapping(mapping_id: int, mapping: Dict[str, Any]) -> bool:
    """Update a Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_register_mappings
            SET modbus_addr = ?, register_type = ?, data_type = ?, source_type = ?,
                rtu_station = ?, slot = ?, description = ?, scaling_enabled = ?,
                scale_raw_min = ?, scale_raw_max = ?, scale_eng_min = ?, scale_eng_max = ?
            WHERE id = ?
        ''', (mapping['modbus_addr'], mapping['register_type'], mapping['data_type'],
              mapping['source_type'], mapping['rtu_station'], mapping['slot'],
              mapping.get('description', ''), mapping.get('scaling_enabled', False),
              mapping.get('scale_raw_min', 0), mapping.get('scale_raw_max', 65535),
              mapping.get('scale_eng_min', 0), mapping.get('scale_eng_max', 100),
              mapping_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_modbus_register_mapping(mapping_id: int) -> bool:
    """Delete a Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM modbus_register_mappings WHERE id = ?', (mapping_id,))
        conn.commit()
        return cursor.rowcount > 0
