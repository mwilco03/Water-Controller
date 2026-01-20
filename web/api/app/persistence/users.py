"""
Water Treatment Controller - Users Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management and authentication operations using SQLAlchemy.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ..core.password_policy import (
    DEFAULT_POLICY,
    calculate_lockout_time,
    calculate_password_expiry,
    is_account_locked,
    is_password_expired,
)
from ..models.user import User
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
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.warning(
            f"Unknown password hash format: {stored_hash[:10]}... "
            "Authentication cannot proceed. "
            "Reset user password via admin interface."
        )
        return False


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
        now = datetime.now(UTC)
        new_user = User(
            username=user['username'],
            password_hash=password_hash,
            role=user.get('role', 'viewer'),
            active=user.get('active', True),
            sync_to_rtus=user.get('sync_to_rtus', True),
            password_changed_at=now,
            password_expires_at=user.get('password_expires_at') or calculate_password_expiry(),
            failed_login_attempts=0,
            locked_until=None,
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
            existing.password_changed_at = datetime.now(UTC)
            existing.password_expires_at = user.get('password_expires_at') or calculate_password_expiry()
            # Reset failed attempts on password change
            existing.failed_login_attempts = 0
            existing.locked_until = None

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
    """
    Authenticate user with username and password.

    Returns user dict on success, None on failure.
    Handles account lockout and failed login tracking.
    """
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None

        if not user.active:
            logger.warning(f"Login attempt for inactive user: {username}")
            return None

        # Check if account is locked
        if is_account_locked(user.locked_until):
            logger.warning(f"Login attempt for locked account: {username}")
            return None

        if not verify_password(password, user.password_hash):
            # Increment failed login attempts
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

            # Lock account if too many failed attempts
            if user.failed_login_attempts >= DEFAULT_POLICY.max_failed_attempts:
                user.locked_until = calculate_lockout_time()
                logger.warning(
                    f"Account locked due to {user.failed_login_attempts} failed attempts: {username}"
                )

            db.commit()
            return None

        # Check if password is expired
        if is_password_expired(user.password_changed_at):
            logger.warning(f"Login attempt with expired password: {username}")
            # Still allow login but set a flag for the frontend to prompt password change
            # This is a soft expiry - user can still authenticate but should change password

        # Successful login - reset failed attempts and update last login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(UTC)
        db.commit()

        return user.to_dict()


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


def unlock_user(user_id: int) -> bool:
    """Unlock a user account and reset failed login attempts."""
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        logger.info(f"User account unlocked: {user.username}")
        return True


def check_password_status(user_id: int) -> dict[str, Any]:
    """
    Check password status for a user.

    Returns dict with:
        - expired: bool - whether password has expired
        - days_until_expiry: int | None - days until expiry (None if never expires)
        - locked: bool - whether account is locked
        - failed_attempts: int - number of failed login attempts
    """
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}

        from datetime import timedelta

        days_until_expiry = None
        if user.password_expires_at:
            delta = user.password_expires_at - datetime.now(UTC)
            days_until_expiry = max(0, delta.days)

        return {
            "expired": is_password_expired(user.password_changed_at),
            "days_until_expiry": days_until_expiry,
            "locked": is_account_locked(user.locked_until),
            "failed_attempts": user.failed_login_attempts or 0,
        }
