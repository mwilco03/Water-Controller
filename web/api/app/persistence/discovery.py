"""
Water Treatment Controller - Discovery Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

DCP discovery cache operations using SQLAlchemy.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
"""

from datetime import UTC, datetime
from typing import Any

from ..models.discovery import DCPDiscoveryCache
from .base import get_db


def get_discovered_devices() -> list[dict[str, Any]]:
    """Get all devices in the discovery cache"""
    with get_db() as db:
        devices = db.query(DCPDiscoveryCache).order_by(
            DCPDiscoveryCache.last_seen.desc()
        ).all()
        return [d.to_dict() for d in devices]


def upsert_discovered_device(device: dict[str, Any]) -> int:
    """Insert or update a discovered device"""
    with get_db() as db:
        existing = db.query(DCPDiscoveryCache).filter(
            DCPDiscoveryCache.mac_address == device['mac_address']
        ).first()

        if existing:
            existing.ip_address = device.get('ip_address')
            existing.device_name = device.get('device_name')
            existing.vendor_name = device.get('vendor_name')
            existing.device_type = device.get('device_type')
            existing.profinet_device_id = device.get('profinet_device_id')
            existing.profinet_vendor_id = device.get('profinet_vendor_id')
            existing.last_seen = datetime.now(UTC)
            db.commit()
            return existing.id
        else:
            new_device = DCPDiscoveryCache(
                mac_address=device['mac_address'],
                ip_address=device.get('ip_address'),
                device_name=device.get('device_name'),
                vendor_name=device.get('vendor_name'),
                device_type=device.get('device_type'),
                profinet_device_id=device.get('profinet_device_id'),
                profinet_vendor_id=device.get('profinet_vendor_id'),
            )
            db.add(new_device)
            db.commit()
            db.refresh(new_device)
            return new_device.id


def mark_device_as_added(mac_address: str) -> bool:
    """Mark a discovered device as added to RTU configuration"""
    with get_db() as db:
        device = db.query(DCPDiscoveryCache).filter(
            DCPDiscoveryCache.mac_address == mac_address
        ).first()
        if not device:
            return False
        device.added_as_rtu = True
        db.commit()
        return True


def clear_discovery_cache() -> int:
    """Clear the discovery cache"""
    with get_db() as db:
        count = db.query(DCPDiscoveryCache).delete()
        db.commit()
        return count
