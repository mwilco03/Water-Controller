"""
Water Treatment Controller - Users Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management and authentication operations.
"""

import logging
from typing import Any

from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)

# DJB2 hash constants (must match C implementation and RTU)
USER_SYNC_SALT = "NaCl4Life"


def _djb2_hash(s: str) -> int:
    """
    DJB2 hash algorithm by Dan Bernstein.
    """
    hash_val = 5381
    for c in s:
        hash_val = ((hash_val << 5) + hash_val) + ord(c)
        hash_val &= 0xFFFFFFFF  # Keep as 32-bit
    return hash_val


def hash_password(password: str) -> str:
    """
    Hash password using DJB2.
    Format: "DJB2:<salt_hash>:<password_hash>"
    """
    salted = USER_SYNC_SALT + password
    hash_val = _djb2_hash(salted)
    salt_hash = _djb2_hash(USER_SYNC_SALT)
    return f"DJB2:{salt_hash:08X}:{hash_val:08X}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.
    """
    if stored_hash.startswith("DJB2:"):
        computed = hash_password(password)
        return computed == stored_hash
    else:
        # Unknown format
        logger.warning(f"Unknown password hash format: {stored_hash[:10]}...")
        return False


def get_users(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Get all users"""
    with get_db() as conn:
        cursor = conn.cursor()
        if include_inactive:
            cursor.execute('SELECT * FROM users ORDER BY username')
        else:
            cursor.execute('SELECT * FROM users WHERE active = 1 ORDER BY username')
        return [dict(row) for row in cursor.fetchall()]


def get_user(user_id: int) -> dict[str, Any] | None:
    """Get a single user by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Get a user by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user(user: dict[str, Any]) -> int:
    """Create a new user"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Hash the password
        password_hash = hash_password(user['password'])
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, active, sync_to_rtus)
            VALUES (?, ?, ?, ?, ?)
        ''', (user['username'], password_hash, user.get('role', 'viewer'),
              user.get('active', True), user.get('sync_to_rtus', True)))
        conn.commit()
        log_audit('system', 'create', 'user', user['username'],
                  f"Created user {user['username']} with role {user.get('role', 'viewer')}")
        return cursor.lastrowid


def update_user(user_id: int, user: dict[str, Any]) -> bool:
    """Update a user"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Build update fields
        fields = []
        values = []

        if 'role' in user:
            fields.append('role = ?')
            values.append(user['role'])

        if 'active' in user:
            fields.append('active = ?')
            values.append(1 if user['active'] else 0)

        if 'sync_to_rtus' in user:
            fields.append('sync_to_rtus = ?')
            values.append(1 if user['sync_to_rtus'] else 0)

        # Handle password change
        if user.get('password'):
            fields.append('password_hash = ?')
            values.append(hash_password(user['password']))

        if not fields:
            return False

        fields.append('updated_at = CURRENT_TIMESTAMP')
        values.append(user_id)

        cursor.execute(f'''
            UPDATE users SET {', '.join(fields)} WHERE id = ?
        ''', tuple(values))
        conn.commit()
        return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """Delete a user"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get username for audit log
        cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        username = row['username'] if row else 'unknown'

        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        if cursor.rowcount > 0:
            log_audit('system', 'delete', 'user', username, f"Deleted user {username}")
            return True
        return False


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate user with username and password"""
    user = get_user_by_username(username)
    if not user:
        return None

    if not user.get('active', False):
        return None

    if not verify_password(password, user['password_hash']):
        return None

    # Update last login
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
        ''', (user['id'],))
        conn.commit()

    return user


def get_users_for_sync() -> list[dict[str, Any]]:
    """Get all users that should be synced to RTUs"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, role, active
            FROM users
            WHERE sync_to_rtus = 1
            ORDER BY username
        ''')
        return [dict(row) for row in cursor.fetchall()]


def ensure_default_admin():
    """Ensure default admin user exists"""
    admin = get_user_by_username('admin')
    if not admin:
        create_user({
            'username': 'admin',
            'password': 'H2OhYeah!',
            'role': 'admin',
            'active': True,
            'sync_to_rtus': True
        })
        logger.info("Created default admin user (username: admin)")
