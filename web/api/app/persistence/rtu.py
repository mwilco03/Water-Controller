"""
Water Treatment Controller - RTU Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU device, sensor, and control operations.
"""

from typing import Any

from .audit import log_audit
from .base import get_db

# ============== RTU Device Operations ==============

def get_rtu_devices() -> list[dict[str, Any]]:
    """Get all RTU devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rtu_devices ORDER BY station_name')
        return [dict(row) for row in cursor.fetchall()]


def get_rtu_device(station_name: str) -> dict[str, Any] | None:
    """Get a single RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rtu_devices WHERE station_name = ?', (station_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_rtu_device(device: dict[str, Any]) -> int:
    """Create a new RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rtu_devices (station_name, ip_address, vendor_id, device_id, slot_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (device['station_name'], device['ip_address'], device.get('vendor_id', 1171),
              device.get('device_id', 1), device.get('slot_count', 16)))
        conn.commit()
        log_audit('system', 'create', 'rtu_device', device['station_name'],
                  f"Created RTU {device['station_name']}")
        return cursor.lastrowid


def update_rtu_device(station_name: str, device: dict[str, Any]) -> bool:
    """Update an RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE rtu_devices
            SET ip_address = ?, vendor_id = ?, device_id = ?, slot_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE station_name = ?
        ''', (device['ip_address'], device.get('vendor_id', 1171),
              device.get('device_id', 1), device.get('slot_count', 16), station_name))
        conn.commit()
        return cursor.rowcount > 0


def delete_rtu_device(station_name: str) -> bool:
    """Delete an RTU device and all related configurations"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Delete related records
        cursor.execute('DELETE FROM slot_configs WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM alarm_rules WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM historian_tags WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM modbus_register_mappings WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM rtu_sensors WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM rtu_controls WHERE rtu_station = ?', (station_name,))
        # Delete the RTU
        cursor.execute('DELETE FROM rtu_devices WHERE station_name = ?', (station_name,))
        conn.commit()
        log_audit('system', 'delete', 'rtu_device', station_name,
                  f"Deleted RTU {station_name} with cascade")
        return cursor.rowcount > 0


# ============== RTU Sensors Operations ==============

def get_rtu_sensors(rtu_station: str) -> list[dict[str, Any]]:
    """Get all sensors for an RTU"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM rtu_sensors WHERE rtu_station = ? ORDER BY sensor_id
        ''', (rtu_station,))
        return [dict(row) for row in cursor.fetchall()]


def upsert_rtu_sensor(sensor: dict[str, Any]) -> int:
    """Insert or update an RTU sensor"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rtu_sensors (rtu_station, sensor_id, sensor_type, name, unit,
                register_address, data_type, scale_min, scale_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, sensor_id) DO UPDATE SET
                sensor_type = excluded.sensor_type,
                name = excluded.name,
                unit = excluded.unit,
                register_address = excluded.register_address,
                data_type = excluded.data_type,
                scale_min = excluded.scale_min,
                scale_max = excluded.scale_max
        ''', (sensor['rtu_station'], sensor['sensor_id'], sensor['sensor_type'],
              sensor['name'], sensor.get('unit'), sensor.get('register_address'),
              sensor.get('data_type', 'FLOAT32'), sensor.get('scale_min', 0),
              sensor.get('scale_max', 100)))
        conn.commit()
        return cursor.lastrowid


def update_sensor_value(rtu_station: str, sensor_id: str, value: float, quality: int = 0) -> bool:
    """Update the last value for a sensor"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE rtu_sensors SET last_value = ?, last_quality = ?, last_update = CURRENT_TIMESTAMP
            WHERE rtu_station = ? AND sensor_id = ?
        ''', (value, quality, rtu_station, sensor_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_rtu_sensor(rtu_station: str, sensor_id: str) -> bool:
    """Delete an RTU sensor"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM rtu_sensors WHERE rtu_station = ? AND sensor_id = ?',
                       (rtu_station, sensor_id))
        conn.commit()
        return cursor.rowcount > 0


def clear_rtu_sensors(rtu_station: str) -> int:
    """Clear all sensors for an RTU (before inventory refresh)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM rtu_sensors WHERE rtu_station = ?', (rtu_station,))
        conn.commit()
        return cursor.rowcount


# ============== RTU Controls Operations ==============

def get_rtu_controls(rtu_station: str) -> list[dict[str, Any]]:
    """Get all controls for an RTU"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM rtu_controls WHERE rtu_station = ? ORDER BY control_id
        ''', (rtu_station,))
        return [dict(row) for row in cursor.fetchall()]


def upsert_rtu_control(control: dict[str, Any]) -> int:
    """Insert or update an RTU control"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rtu_controls (rtu_station, control_id, control_type, name, command_type,
                register_address, feedback_register, range_min, range_max, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, control_id) DO UPDATE SET
                control_type = excluded.control_type,
                name = excluded.name,
                command_type = excluded.command_type,
                register_address = excluded.register_address,
                feedback_register = excluded.feedback_register,
                range_min = excluded.range_min,
                range_max = excluded.range_max,
                unit = excluded.unit
        ''', (control['rtu_station'], control['control_id'], control['control_type'],
              control['name'], control.get('command_type', 'on_off'),
              control.get('register_address'), control.get('feedback_register'),
              control.get('range_min'), control.get('range_max'), control.get('unit')))
        conn.commit()
        return cursor.lastrowid


def update_control_state(rtu_station: str, control_id: str, state: str) -> bool:
    """Update the last state for a control"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE rtu_controls SET last_state = ?, last_update = CURRENT_TIMESTAMP
            WHERE rtu_station = ? AND control_id = ?
        ''', (state, rtu_station, control_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_rtu_control(rtu_station: str, control_id: str) -> bool:
    """Delete an RTU control"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM rtu_controls WHERE rtu_station = ? AND control_id = ?',
                       (rtu_station, control_id))
        conn.commit()
        return cursor.rowcount > 0


def clear_rtu_controls(rtu_station: str) -> int:
    """Clear all controls for an RTU (before inventory refresh)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM rtu_controls WHERE rtu_station = ?', (rtu_station,))
        conn.commit()
        return cursor.rowcount


def get_rtu_inventory(rtu_station: str) -> dict[str, Any] | None:
    """Get complete inventory for an RTU (sensors + controls)"""
    device = get_rtu_device(rtu_station)
    if not device:
        return None

    return {
        "rtu_station": rtu_station,
        "device": device,
        "sensors": get_rtu_sensors(rtu_station),
        "controls": get_rtu_controls(rtu_station)
    }
