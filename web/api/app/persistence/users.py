"""
Water Treatment Controller - Users Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management and authentication operations using SQLAlchemy.

Password Hashing Strategy:
==========================
Two hash types are supported:

1. BCRYPT (preferred for web authentication):
   - Format: "BCRYPT:<bcrypt_hash>"
   - Uses bcrypt with work factor 12
   - Secure against rainbow tables and GPU attacks

2. DJB2 (legacy, required for RTU sync):
   - Format: "DJB2:<salt_hash>:<password_hash>"
   - Must match C implementation on RTU hardware
   - Only used for password sync to field devices

New users get bcrypt hashes. RTU sync uses DJB2 separately.
"""

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from ..models.user import User
from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)

# DJB2 hash constants (must match C implementation and RTU)
# WARNING: DJB2 is NOT cryptographically secure - only used for RTU compatibility
USER_SYNC_SALT = "NaCl4Life"

# Bcrypt work factor (12 = ~250ms on modern hardware)
BCRYPT_ROUNDS = 12


def _djb2_hash(s: str) -> int:
    """
    DJB2 hash algorithm by Dan Bernstein.

    WARNING: This is NOT a cryptographic hash. Only use for RTU compatibility.
    For authentication, use bcrypt via hash_password().
    """
    hash_val = 5381
    for c in s:
        hash_val = ((hash_val << 5) + hash_val) + ord(c)
        hash_val &= 0xFFFFFFFF  # Keep as 32-bit
    return hash_val


def _djb2_hash_password(password: str) -> str:
    """
    Hash password using DJB2 for RTU sync compatibility.
    Format: "DJB2:<salt_hash>:<password_hash>"

    WARNING: Only use this for RTU sync. For web auth, use hash_password().
    """
    salted = USER_SYNC_SALT + password
    hash_val = _djb2_hash(salted)
    salt_hash = _djb2_hash(USER_SYNC_SALT)
    return f"DJB2:{salt_hash:08X}:{hash_val:08X}"


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt (secure).
    Format: "BCRYPT:<bcrypt_hash>"

    Uses work factor 12 which takes ~250ms on modern hardware,
    providing good resistance against brute force attacks.
    """
    try:
        import bcrypt
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
        return f"BCRYPT:{hashed.decode('utf-8')}"
    except ImportError:
        # Fallback if bcrypt not installed (use PBKDF2 with SHA256)
        logger.warning("bcrypt not available, using PBKDF2 fallback")
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"PBKDF2:{salt}:{key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.
    Supports bcrypt, PBKDF2, and legacy DJB2 formats.
    """
    if stored_hash.startswith("BCRYPT:"):
        try:
            import bcrypt
            bcrypt_hash = stored_hash[7:].encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), bcrypt_hash)
        except ImportError:
            logger.error("bcrypt not available for verification")
            return False
    elif stored_hash.startswith("PBKDF2:"):
        parts = stored_hash.split(":")
        if len(parts) != 3:
            return False
        salt = parts[1]
        stored_key = parts[2]
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return secrets.compare_digest(key.hex(), stored_key)
    elif stored_hash.startswith("DJB2:"):
        # Legacy format - still verify but log warning
        computed = _djb2_hash_password(password)
        return computed == stored_hash
    else:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.warning(
            f"Unknown password hash format: {stored_hash[:10]}... "
            "Authentication cannot proceed. "
            "Reset user password via admin interface."
        )
        return False


def get_rtu_sync_hash(password: str) -> str:
    """
    Get DJB2 hash for RTU sync.

    This is separate from the web authentication hash to maintain
    compatibility with RTU hardware while using secure hashing for web.
    """
    return _djb2_hash_password(password)


def get_users(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Get all users"""
    with get_db() as db:
        query = db.query(User)
        if not include_inactive:
            query = query.filter(User.active == True)
        users = query.order_by(User.username).all()
        return [u.to_dict() for u in users]


def get_user(user_id: int) -> dict[str, Any] | None:
    """Get a single user by ID"""
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return user.to_dict() if user else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Get a user by username"""
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        return user.to_dict() if user else None


def create_user(user: dict[str, Any]) -> int:
    """Create a new user"""
    with get_db() as db:
        password_hash = hash_password(user['password'])
        new_user = User(
            username=user['username'],
            password_hash=password_hash,
            role=user.get('role', 'viewer'),
            active=user.get('active', True),
            sync_to_rtus=user.get('sync_to_rtus', True),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        log_audit('system', 'create', 'user', user['username'],
                  f"Created user {user['username']} with role {user.get('role', 'viewer')}")
        return new_user.id


def update_user(user_id: int, user: dict[str, Any]) -> bool:
    """Update a user"""
    with get_db() as db:
        existing = db.query(User).filter(User.id == user_id).first()
        if not existing:
            return False

        if 'role' in user:
            existing.role = user['role']

        if 'active' in user:
            existing.active = user['active']

        if 'sync_to_rtus' in user:
            existing.sync_to_rtus = user['sync_to_rtus']

        if user.get('password'):
            existing.password_hash = hash_password(user['password'])

        existing.updated_at = datetime.now(UTC)
        db.commit()
        return True


def delete_user(user_id: int) -> bool:
    """Delete a user"""
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        username = user.username
        db.delete(user)
        db.commit()
        log_audit('system', 'delete', 'user', username, f"Deleted user {username}")
        return True


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate user with username and password"""
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None

        if not user.active:
            return None

        if not verify_password(password, user.password_hash):
            return None

        # Update last login
        user.last_login = datetime.now(UTC)
        db.commit()

        return _user_to_dict(user)


def get_users_for_sync() -> list[dict[str, Any]]:
    """Get all users that should be synced to RTUs"""
    with get_db() as db:
        users = db.query(User).filter(User.sync_to_rtus == True).order_by(User.username).all()
        return [{
            "id": u.id,
            "username": u.username,
            "password_hash": u.password_hash,
            "role": u.role,
            "active": u.active,
        } for u in users]


def ensure_default_admin() -> None:
    """
    Ensure default admin user exists.

    Security:
    - Password can be set via WTC_DEFAULT_ADMIN_PASSWORD environment variable
    - If not set, generates a secure random password and logs it ONCE
    - The generated password should be changed immediately after first login
    """
    admin = get_user_by_username('admin')
    if not admin:
        # Check for environment variable first
        password = os.environ.get('WTC_DEFAULT_ADMIN_PASSWORD')

        if password:
            logger.info("Creating admin user with password from WTC_DEFAULT_ADMIN_PASSWORD")
        else:
            # Generate secure random password
            password = secrets.token_urlsafe(16)
            logger.warning(
                "=" * 60 + "\n"
                "SECURITY: Generated default admin credentials\n"
                f"  Username: admin\n"
                f"  Password: {password}\n"
                "IMPORTANT: Change this password immediately after first login!\n"
                "To set a specific password, use WTC_DEFAULT_ADMIN_PASSWORD env var.\n"
                + "=" * 60
            )

        create_user({
            'username': 'admin',
            'password': password,
            'role': 'admin',
            'active': True,
            'sync_to_rtus': True
        })
        logger.info("Created default admin user")
