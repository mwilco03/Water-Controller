"""
Water Treatment Controller - Historian Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Historian tag operations using SQLAlchemy.

Architecture Decision (2026-01): SlotConfig functions removed.
Slots are PROFINET frame positions, not database entities.
See CLAUDE.md "Slots Architecture Decision" for rationale.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
"""

from typing import Any

from ..models.historian import HistorianTag
from .audit import log_audit
from .base import get_db


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
