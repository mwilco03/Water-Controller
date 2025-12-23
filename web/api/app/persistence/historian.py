"""
Water Treatment Controller - Historian Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Historian tags and slot configuration operations.
"""

from typing import List, Optional, Dict, Any

from .base import get_db
from .audit import log_audit


# ============== Slot Configuration Operations ==============

def get_all_slot_configs() -> List[Dict[str, Any]]:
    """Get all slot configurations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs ORDER BY rtu_station, slot')
        return [dict(row) for row in cursor.fetchall()]


def get_slot_configs_by_rtu(rtu_station: str) -> List[Dict[str, Any]]:
    """Get slot configurations for a specific RTU"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs WHERE rtu_station = ? ORDER BY slot',
                       (rtu_station,))
        return [dict(row) for row in cursor.fetchall()]


def get_slot_config(rtu_station: str, slot: int) -> Optional[Dict[str, Any]]:
    """Get a specific slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs WHERE rtu_station = ? AND slot = ?',
                       (rtu_station, slot))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_slot_config(config: Dict[str, Any]) -> int:
    """Create or update a slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO slot_configs (rtu_station, slot, subslot, slot_type, name, unit,
                measurement_type, actuator_type, scale_min, scale_max,
                alarm_low, alarm_high, alarm_low_low, alarm_high_high,
                warning_low, warning_high, deadband, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, slot) DO UPDATE SET
                subslot = excluded.subslot,
                slot_type = excluded.slot_type,
                name = excluded.name,
                unit = excluded.unit,
                measurement_type = excluded.measurement_type,
                actuator_type = excluded.actuator_type,
                scale_min = excluded.scale_min,
                scale_max = excluded.scale_max,
                alarm_low = excluded.alarm_low,
                alarm_high = excluded.alarm_high,
                alarm_low_low = excluded.alarm_low_low,
                alarm_high_high = excluded.alarm_high_high,
                warning_low = excluded.warning_low,
                warning_high = excluded.warning_high,
                deadband = excluded.deadband,
                enabled = excluded.enabled
        ''', (config['rtu_station'], config['slot'], config.get('subslot', 1),
              config['slot_type'], config.get('name'), config.get('unit'),
              config.get('measurement_type'), config.get('actuator_type'),
              config.get('scale_min', 0), config.get('scale_max', 100),
              config.get('alarm_low'), config.get('alarm_high'),
              config.get('alarm_low_low'), config.get('alarm_high_high'),
              config.get('warning_low'), config.get('warning_high'),
              config.get('deadband', 0), config.get('enabled', True)))
        conn.commit()
        return cursor.lastrowid


def delete_slot_config(rtu_station: str, slot: int) -> bool:
    """Delete a slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM slot_configs WHERE rtu_station = ? AND slot = ?',
                       (rtu_station, slot))
        conn.commit()
        return cursor.rowcount > 0


# ============== Historian Tag Operations ==============

def get_historian_tags() -> List[Dict[str, Any]]:
    """Get all historian tags"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags ORDER BY tag_name')
        return [dict(row) for row in cursor.fetchall()]


def get_historian_tag(tag_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific historian tag by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags WHERE id = ?', (tag_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_historian_tag_by_name(tag_name: str) -> Optional[Dict[str, Any]]:
    """Get a historian tag by name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags WHERE tag_name = ?', (tag_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_historian_tag(tag: Dict[str, Any]) -> int:
    """Create or update a historian tag"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO historian_tags (rtu_station, slot, tag_name, unit,
                sample_rate_ms, deadband, compression)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, slot) DO UPDATE SET
                tag_name = excluded.tag_name,
                unit = excluded.unit,
                sample_rate_ms = excluded.sample_rate_ms,
                deadband = excluded.deadband,
                compression = excluded.compression
        ''', (tag['rtu_station'], tag['slot'], tag['tag_name'], tag.get('unit'),
              tag.get('sample_rate_ms', 1000), tag.get('deadband', 0.1),
              tag.get('compression', 'swinging_door')))
        conn.commit()
        log_audit('system', 'upsert', 'historian_tag', tag['tag_name'],
                  f"Upserted historian tag {tag['tag_name']}")
        return cursor.lastrowid


def delete_historian_tag(tag_id: int) -> bool:
    """Delete a historian tag"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM historian_tags WHERE id = ?', (tag_id,))
        conn.commit()
        log_audit('system', 'delete', 'historian_tag', str(tag_id),
                  f"Deleted historian tag {tag_id}")
        return cursor.rowcount > 0
