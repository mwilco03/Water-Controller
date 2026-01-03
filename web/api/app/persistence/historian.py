"""
Water Treatment Controller - Historian Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Historian tags and slot configuration operations using SQLAlchemy.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
"""

from datetime import UTC, datetime
from typing import Any

from ..models.historian import HistorianTag, SlotConfig
from .audit import log_audit
from .base import get_db


# ============== Slot Configuration Operations ==============

def get_all_slot_configs() -> list[dict[str, Any]]:
    """Get all slot configurations"""
    with get_db() as db:
        slots = db.query(SlotConfig).order_by(
            SlotConfig.rtu_station, SlotConfig.slot
        ).all()
        return [s.to_dict() for s in slots]


def get_slot_configs_by_rtu(rtu_station: str) -> list[dict[str, Any]]:
    """Get slot configurations for a specific RTU"""
    with get_db() as db:
        slots = db.query(SlotConfig).filter(
            SlotConfig.rtu_station == rtu_station
        ).order_by(SlotConfig.slot).all()
        return [s.to_dict() for s in slots]


def get_slot_config(rtu_station: str, slot: int) -> dict[str, Any] | None:
    """Get a specific slot configuration"""
    with get_db() as db:
        config = db.query(SlotConfig).filter(
            SlotConfig.rtu_station == rtu_station,
            SlotConfig.slot == slot
        ).first()
        return config.to_dict() if config else None


def upsert_slot_config(config: dict[str, Any]) -> int:
    """Create or update a slot configuration"""
    with get_db() as db:
        existing = db.query(SlotConfig).filter(
            SlotConfig.rtu_station == config['rtu_station'],
            SlotConfig.slot == config['slot']
        ).first()

        if existing:
            existing.subslot = config.get('subslot', 1)
            existing.slot_type = config['slot_type']
            existing.name = config.get('name')
            existing.unit = config.get('unit')
            existing.measurement_type = config.get('measurement_type')
            existing.actuator_type = config.get('actuator_type')
            existing.scale_min = config.get('scale_min', 0)
            existing.scale_max = config.get('scale_max', 100)
            existing.alarm_low = config.get('alarm_low')
            existing.alarm_high = config.get('alarm_high')
            existing.alarm_low_low = config.get('alarm_low_low')
            existing.alarm_high_high = config.get('alarm_high_high')
            existing.warning_low = config.get('warning_low')
            existing.warning_high = config.get('warning_high')
            existing.deadband = config.get('deadband', 0)
            existing.enabled = config.get('enabled', True)
            db.commit()
            return existing.id
        else:
            new_config = SlotConfig(
                rtu_station=config['rtu_station'],
                slot=config['slot'],
                subslot=config.get('subslot', 1),
                slot_type=config['slot_type'],
                name=config.get('name'),
                unit=config.get('unit'),
                measurement_type=config.get('measurement_type'),
                actuator_type=config.get('actuator_type'),
                scale_min=config.get('scale_min', 0),
                scale_max=config.get('scale_max', 100),
                alarm_low=config.get('alarm_low'),
                alarm_high=config.get('alarm_high'),
                alarm_low_low=config.get('alarm_low_low'),
                alarm_high_high=config.get('alarm_high_high'),
                warning_low=config.get('warning_low'),
                warning_high=config.get('warning_high'),
                deadband=config.get('deadband', 0),
                enabled=config.get('enabled', True),
            )
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            return new_config.id


def delete_slot_config(rtu_station: str, slot: int) -> bool:
    """Delete a slot configuration"""
    with get_db() as db:
        config = db.query(SlotConfig).filter(
            SlotConfig.rtu_station == rtu_station,
            SlotConfig.slot == slot
        ).first()
        if not config:
            return False
        db.delete(config)
        db.commit()
        return True


# ============== Historian Tag Operations ==============

def get_historian_tags() -> list[dict[str, Any]]:
    """Get all historian tags"""
    with get_db() as db:
        tags = db.query(HistorianTag).order_by(HistorianTag.tag_name).all()
        return [t.to_dict() for t in tags]


def get_historian_tag(tag_id: int) -> dict[str, Any] | None:
    """Get a specific historian tag by ID"""
    with get_db() as db:
        tag = db.query(HistorianTag).filter(HistorianTag.id == tag_id).first()
        return tag.to_dict() if tag else None


def get_historian_tag_by_name(tag_name: str) -> dict[str, Any] | None:
    """Get a historian tag by name"""
    with get_db() as db:
        tag = db.query(HistorianTag).filter(HistorianTag.tag_name == tag_name).first()
        return tag.to_dict() if tag else None


def upsert_historian_tag(tag: dict[str, Any]) -> int:
    """Create or update a historian tag"""
    with get_db() as db:
        existing = db.query(HistorianTag).filter(
            HistorianTag.rtu_station == tag['rtu_station'],
            HistorianTag.slot == tag['slot']
        ).first()

        if existing:
            existing.tag_name = tag['tag_name']
            existing.unit = tag.get('unit')
            existing.sample_rate_ms = tag.get('sample_rate_ms', 1000)
            existing.deadband = tag.get('deadband', 0.1)
            existing.compression = tag.get('compression', 'swinging_door')
            db.commit()
            log_audit('system', 'upsert', 'historian_tag', tag['tag_name'],
                      f"Upserted historian tag {tag['tag_name']}")
            return existing.id
        else:
            new_tag = HistorianTag(
                rtu_station=tag['rtu_station'],
                slot=tag['slot'],
                tag_name=tag['tag_name'],
                unit=tag.get('unit'),
                sample_rate_ms=tag.get('sample_rate_ms', 1000),
                deadband=tag.get('deadband', 0.1),
                compression=tag.get('compression', 'swinging_door'),
            )
            db.add(new_tag)
            db.commit()
            db.refresh(new_tag)
            log_audit('system', 'upsert', 'historian_tag', tag['tag_name'],
                      f"Upserted historian tag {tag['tag_name']}")
            return new_tag.id


def delete_historian_tag(tag_id: int) -> bool:
    """Delete a historian tag"""
    with get_db() as db:
        tag = db.query(HistorianTag).filter(HistorianTag.id == tag_id).first()
        if not tag:
            return False
        tag_name = tag.tag_name
        db.delete(tag)
        db.commit()
        log_audit('system', 'delete', 'historian_tag', str(tag_id),
                  f"Deleted historian tag {tag_name}")
        return True
