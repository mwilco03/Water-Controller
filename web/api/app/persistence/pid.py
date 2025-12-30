"""
Water Treatment Controller - PID Loop Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

PID control loop operations.
"""

from typing import Any

from .audit import log_audit
from .base import get_db


def get_pid_loops() -> list[dict[str, Any]]:
    """Get all PID control loops"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pid_loops ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def get_pid_loop(loop_id: int) -> dict[str, Any] | None:
    """Get a single PID loop by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pid_loops WHERE id = ?', (loop_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_pid_loop(loop: dict[str, Any]) -> int:
    """Create a new PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pid_loops (name, enabled, input_rtu, input_slot, output_rtu,
                output_slot, kp, ki, kd, setpoint, output_min, output_max, deadband,
                integral_limit, derivative_filter, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (loop['name'], loop.get('enabled', True), loop['input_rtu'],
              loop['input_slot'], loop['output_rtu'], loop['output_slot'],
              loop.get('kp', 1.0), loop.get('ki', 0.0), loop.get('kd', 0.0),
              loop.get('setpoint', 0), loop.get('output_min', 0),
              loop.get('output_max', 100), loop.get('deadband', 0),
              loop.get('integral_limit', 100), loop.get('derivative_filter', 0.1),
              loop.get('mode', 'AUTO')))
        conn.commit()
        log_audit('system', 'create', 'pid_loop', str(cursor.lastrowid),
                  f"Created PID loop {loop['name']}")
        return cursor.lastrowid


def update_pid_loop(loop_id: int, loop: dict[str, Any]) -> bool:
    """Update a PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops
            SET name = ?, enabled = ?, input_rtu = ?, input_slot = ?, output_rtu = ?,
                output_slot = ?, kp = ?, ki = ?, kd = ?, setpoint = ?, output_min = ?,
                output_max = ?, deadband = ?, integral_limit = ?, derivative_filter = ?,
                mode = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (loop['name'], loop.get('enabled', True), loop['input_rtu'],
              loop['input_slot'], loop['output_rtu'], loop['output_slot'],
              loop.get('kp', 1.0), loop.get('ki', 0.0), loop.get('kd', 0.0),
              loop.get('setpoint', 0), loop.get('output_min', 0),
              loop.get('output_max', 100), loop.get('deadband', 0),
              loop.get('integral_limit', 100), loop.get('derivative_filter', 0.1),
              loop.get('mode', 'AUTO'), loop_id))
        conn.commit()
        return cursor.rowcount > 0


def update_pid_setpoint(loop_id: int, setpoint: float) -> bool:
    """Update only the setpoint for a PID loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops SET setpoint = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (setpoint, loop_id))
        conn.commit()
        return cursor.rowcount > 0


def update_pid_mode(loop_id: int, mode: str) -> bool:
    """Update only the mode for a PID loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops SET mode = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (mode, loop_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_pid_loop(loop_id: int) -> bool:
    """Delete a PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pid_loops WHERE id = ?', (loop_id,))
        conn.commit()
        log_audit('system', 'delete', 'pid_loop', str(loop_id),
                  f"Deleted PID loop {loop_id}")
        return cursor.rowcount > 0
