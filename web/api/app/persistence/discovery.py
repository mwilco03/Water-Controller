"""
Water Treatment Controller - Discovery Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

DCP discovery cache operations.
"""

from typing import Any

from .base import get_db


def get_discovered_devices() -> list[dict[str, Any]]:
    """Get all devices in the discovery cache"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM dcp_discovery_cache ORDER BY last_seen DESC')
        return [dict(row) for row in cursor.fetchall()]


def upsert_discovered_device(device: dict[str, Any]) -> int:
    """Insert or update a discovered device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO dcp_discovery_cache (mac_address, ip_address, device_name,
                vendor_name, device_type, profinet_device_id, profinet_vendor_id,
                last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(mac_address) DO UPDATE SET
                ip_address = excluded.ip_address,
                device_name = excluded.device_name,
                vendor_name = excluded.vendor_name,
                device_type = excluded.device_type,
                profinet_device_id = excluded.profinet_device_id,
                profinet_vendor_id = excluded.profinet_vendor_id,
                last_seen = CURRENT_TIMESTAMP
        ''', (device['mac_address'], device.get('ip_address'), device.get('device_name'),
              device.get('vendor_name'), device.get('device_type'),
              device.get('profinet_device_id'), device.get('profinet_vendor_id')))
        conn.commit()
        return cursor.lastrowid


def mark_device_as_added(mac_address: str) -> bool:
    """Mark a discovered device as added to RTU configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE dcp_discovery_cache SET added_as_rtu = 1 WHERE mac_address = ?
        ''', (mac_address,))
        conn.commit()
        return cursor.rowcount > 0


def clear_discovery_cache() -> int:
    """Clear the discovery cache"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM dcp_discovery_cache')
        conn.commit()
        return cursor.rowcount
