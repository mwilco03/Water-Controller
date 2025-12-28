"""
Water Treatment Controller - Users Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management and authentication operations.

SECURITY NOTES:
- Web authentication uses bcrypt (secure, slow hash)
- RTU sync uses DJB2 (for embedded system compatibility)
- Passwords are stored in bcrypt format, DJB2 computed on-demand for RTU sync
"""

import logging
import hashlib
import secrets
from typing import List, Optional, Dict, Any

from .base import get_db
from .audit import log_audit

logger = logging.getLogger(__name__)

# DJB2 hash constants (must match C implementation and RTU)
USER_SYNC_SALT = "NaCl4Life"

# Bcrypt settings for secure web authentication
BCRYPT_ROUNDS = 12  # ~250ms on modern hardware

# Try to import bcrypt, fall back to hashlib if not available
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt not installed - using PBKDF2 fallback for password hashing")


def _djb2_hash(s: str) -> int:
    """
    DJB2 hash algorithm by Dan Bernstein.
    SECURITY WARNING: This is NOT cryptographically secure.
    Used ONLY for RTU sync compatibility, never for web authentication.
    """
    hash_val = 5381
    for c in s:
        hash_val = ((hash_val << 5) + hash_val) + ord(c)
        hash_val &= 0xFFFFFFFF  # Keep as 32-bit
    return hash_val


def hash_password_for_rtu_sync(password: str) -> str:
    """
    Hash password using DJB2 for RTU synchronization ONLY.
    Format: "DJB2:<salt_hash>:<password_hash>"
    This matches the embedded RTU implementation.

    SECURITY WARNING: Do NOT use this for web authentication.
    """
    salted = USER_SYNC_SALT + password
    hash_val = _djb2_hash(salted)
    salt_hash = _djb2_hash(USER_SYNC_SALT)
    return f"DJB2:{salt_hash:08X}:{hash_val:08X}"


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt (or PBKDF2 fallback) for secure storage.
    Format: "BCRYPT:<hash>" or "PBKDF2:<salt>:<hash>"
    """
    if BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return f"BCRYPT:{hashed.decode('utf-8')}"
    else:
        # PBKDF2 fallback with SHA-256
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return f"PBKDF2:{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.
    Supports multiple hash formats for backwards compatibility.
    """
    if stored_hash.startswith("BCRYPT:"):
        if not BCRYPT_AVAILABLE:
            logger.error("bcrypt hash found but bcrypt not installed")
            return False
        hash_part = stored_hash[7:]  # Remove "BCRYPT:" prefix
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hash_part.encode('utf-8'))
        except Exception as e:
            logger.error(f"bcrypt verification failed: {e}")
            return False

    elif stored_hash.startswith("PBKDF2:"):
        parts = stored_hash.split(":")
        if len(parts) != 3:
            return False
        _, salt, expected_hash = parts
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return secrets.compare_digest(dk.hex(), expected_hash)

    elif stored_hash.startswith("DJB2:"):
        # Legacy DJB2 format - verify but recommend migration
        computed = hash_password_for_rtu_sync(password)
        if computed == stored_hash:
            logger.warning("User authenticated with legacy DJB2 hash - migration recommended")
            return True
        return False

    else:
        # Unknown format
        logger.warning(f"Unknown password hash format: {stored_hash[:10]}...")
        return False


def get_users(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get all users"""
    with get_db() as conn:
        cursor = conn.cursor()
        if include_inactive:
            cursor.execute('SELECT * FROM users ORDER BY username')
        else:
            cursor.execute('SELECT * FROM users WHERE active = 1 ORDER BY username')
        return [dict(row) for row in cursor.fetchall()]


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get a single user by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get a user by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user(user: Dict[str, Any]) -> int:
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


def update_user(user_id: int, user: Dict[str, Any]) -> bool:
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
        if 'password' in user and user['password']:
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


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
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


def get_users_for_sync() -> List[Dict[str, Any]]:
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
