"""
Water Treatment Controller - PID Loop Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

PID control loop operations using SQLAlchemy.

Note: Uses DictSerializableMixin.to_dict() from models/base.py for serialization.
"""

from datetime import UTC, datetime
from typing import Any

from ..models.pid import PidLoop
from .audit import log_audit
from .base import get_db


def get_pid_loops() -> list[dict[str, Any]]:
    """Get all PID control loops"""
    with get_db() as db:
        loops = db.query(PidLoop).order_by(PidLoop.id).all()
        return [loop.to_dict() for loop in loops]


def get_pid_loop(loop_id: int) -> dict[str, Any] | None:
    """Get a single PID loop by ID"""
    with get_db() as db:
        loop = db.query(PidLoop).filter(PidLoop.id == loop_id).first()
        return loop.to_dict() if loop else None


def create_pid_loop(loop: dict[str, Any]) -> int:
    """Create a new PID control loop"""
    with get_db() as db:
        new_loop = PidLoop(
            name=loop['name'],
            enabled=loop.get('enabled', True),
            input_rtu=loop['input_rtu'],
            input_slot=loop['input_slot'],
            output_rtu=loop['output_rtu'],
            output_slot=loop['output_slot'],
            kp=loop.get('kp', 1.0),
            ki=loop.get('ki', 0.0),
            kd=loop.get('kd', 0.0),
            setpoint=loop.get('setpoint', 0),
            output_min=loop.get('output_min', 0),
            output_max=loop.get('output_max', 100),
            deadband=loop.get('deadband', 0),
            integral_limit=loop.get('integral_limit', 100),
            derivative_filter=loop.get('derivative_filter', 0.1),
            mode=loop.get('mode', 'AUTO'),
        )
        db.add(new_loop)
        db.commit()
        db.refresh(new_loop)
        log_audit('system', 'create', 'pid_loop', str(new_loop.id),
                  f"Created PID loop {loop['name']}")
        return new_loop.id


def update_pid_loop(loop_id: int, loop: dict[str, Any]) -> bool:
    """Update a PID control loop"""
    with get_db() as db:
        existing = db.query(PidLoop).filter(PidLoop.id == loop_id).first()
        if not existing:
            return False

        existing.name = loop['name']
        existing.enabled = loop.get('enabled', True)
        existing.input_rtu = loop['input_rtu']
        existing.input_slot = loop['input_slot']
        existing.output_rtu = loop['output_rtu']
        existing.output_slot = loop['output_slot']
        existing.kp = loop.get('kp', 1.0)
        existing.ki = loop.get('ki', 0.0)
        existing.kd = loop.get('kd', 0.0)
        existing.setpoint = loop.get('setpoint', 0)
        existing.output_min = loop.get('output_min', 0)
        existing.output_max = loop.get('output_max', 100)
        existing.deadband = loop.get('deadband', 0)
        existing.integral_limit = loop.get('integral_limit', 100)
        existing.derivative_filter = loop.get('derivative_filter', 0.1)
        existing.mode = loop.get('mode', 'AUTO')
        existing.updated_at = datetime.now(UTC)

        db.commit()
        return True


def update_pid_setpoint(loop_id: int, setpoint: float) -> bool:
    """Update only the setpoint for a PID loop"""
    with get_db() as db:
        loop = db.query(PidLoop).filter(PidLoop.id == loop_id).first()
        if not loop:
            return False
        loop.setpoint = setpoint
        loop.updated_at = datetime.now(UTC)
        db.commit()
        return True


def update_pid_mode(loop_id: int, mode: str) -> bool:
    """Update only the mode for a PID loop"""
    with get_db() as db:
        loop = db.query(PidLoop).filter(PidLoop.id == loop_id).first()
        if not loop:
            return False
        loop.mode = mode
        loop.updated_at = datetime.now(UTC)
        db.commit()
        return True


def delete_pid_loop(loop_id: int) -> bool:
    """Delete a PID control loop"""
    with get_db() as db:
        loop = db.query(PidLoop).filter(PidLoop.id == loop_id).first()
        if not loop:
            return False
        db.delete(loop)
        db.commit()
        log_audit('system', 'delete', 'pid_loop', str(loop_id),
                  f"Deleted PID loop {loop_id}")
        return True
