"""
Water Treatment Controller - Users Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management and authentication operations using SQLAlchemy.
"""

import logging
from datetime import UTC, datetime
from typing import Any

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


def _user_to_dict(user: User) -> dict[str, Any]:
    """Convert User model to dictionary."""
    return {
        "id": user.id,
        "username": user.username,
        "password_hash": user.password_hash,
        "role": user.role,
        "active": user.active,
        "sync_to_rtus": user.sync_to_rtus,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def get_users(include_inactive: bool = False) -> list[dict[str, Any]]:
    """Get all users"""
    with get_db() as db:
        query = db.query(User)
        if not include_inactive:
            query = query.filter(User.active == True)
        users = query.order_by(User.username).all()
        return [_user_to_dict(u) for u in users]


def get_user(user_id: int) -> dict[str, Any] | None:
    """Get a single user by ID"""
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return _user_to_dict(user) if user else None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Get a user by username"""
    with get_db() as db:
        user = db.query(User).filter(User.username == username).first()
        return _user_to_dict(user) if user else None


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
