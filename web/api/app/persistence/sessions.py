"""
Water Treatment Controller - Sessions Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User session management operations using SQLAlchemy.

Note: Uses custom serialization for groups field (JSON stored as string).
The base mixin's to_dict() is extended here for proper groups handling.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..models.user import UserSession
from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)


def create_session(token: str, username: str, role: str, groups: list[str],
                   expires_at: datetime, ip_address: str | None = None,
                   user_agent: str | None = None) -> bool:
    """Create a new user session"""
    with get_db() as db:
        try:
            session = UserSession(
                token=token,
                username=username,
                role=role,
                groups=json.dumps(groups),
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.add(session)
            db.commit()
            log_audit(username, 'login', 'session', token[:8],
                      f"User {username} logged in", ip_address)
            return True
        except IntegrityError as e:
            # Duplicate token (extremely unlikely with UUIDs)
            logger.error(
                f"Session token collision: {e}. "
                "Could not create unique session. "
                "Have user retry login."
            )
            db.rollback()
            return False
        except SQLAlchemyError as e:
            # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
            logger.error(
                f"Session creation failed: {e}. "
                "User login not persisted. "
                "Check database connectivity and have user retry login."
            )
            db.rollback()
            return False


def _session_to_dict(session: UserSession) -> dict[str, Any]:
    """Convert UserSession model to dictionary."""
    result = {
        "token": session.token,
        "username": session.username,
        "role": session.role,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "ip_address": session.ip_address,
        "user_agent": session.user_agent,
    }
    # Parse groups from JSON
    if session.groups:
        try:
            result['groups'] = json.loads(session.groups)
        except json.JSONDecodeError:
            result['groups'] = []
    else:
        result['groups'] = []
    return result


def get_session(token: str) -> dict[str, Any] | None:
    """Get session by token"""
    with get_db() as db:
        session = db.query(UserSession).filter(
            UserSession.token == token,
            UserSession.expires_at > datetime.now(UTC)
        ).first()
        if session:
            return _session_to_dict(session)
        return None


def update_session_activity(token: str) -> bool:
    """Update session last activity time"""
    with get_db() as db:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if session:
            session.last_activity = datetime.now(UTC)
            db.commit()
            return True
        return False


def delete_session(token: str) -> bool:
    """Delete a session (logout)"""
    with get_db() as db:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if not session:
            return False

        username = session.username
        db.delete(session)
        db.commit()
        log_audit(username, 'logout', 'session', token[:8],
                  f"User {username} logged out")
        return True


def delete_session_by_prefix(token_prefix: str, admin_user: str | None = None) -> bool:
    """Delete a session by token prefix (for admin session termination)"""
    with get_db() as db:
        session = db.query(UserSession).filter(
            UserSession.token.like(token_prefix + '%'),
            UserSession.expires_at > datetime.now(UTC)
        ).first()

        if not session:
            return False

        full_token = session.token
        username = session.username

        db.delete(session)
        db.commit()
        log_audit(admin_user or 'admin', 'terminate_session', 'session',
                  full_token[:8], f"Admin terminated session for {username}")
        return True


def cleanup_expired_sessions() -> int:
    """Remove expired sessions"""
    with get_db() as db:
        expired = db.query(UserSession).filter(
            UserSession.expires_at < datetime.now(UTC)
        ).all()
        count = len(expired)
        for session in expired:
            db.delete(session)
        db.commit()
        if count > 0:
            logger.info(f"Cleaned up {count} expired sessions")
        return count


def get_active_sessions(username: str | None = None) -> list[dict[str, Any]]:
    """Get all active sessions, optionally filtered by username"""
    with get_db() as db:
        query = db.query(UserSession).filter(
            UserSession.expires_at > datetime.now(UTC)
        )
        if username:
            query = query.filter(UserSession.username == username)
        query = query.order_by(UserSession.last_activity.desc())

        sessions = []
        for session in query.all():
            result = {
                "token": session.token[:8] + '...',  # Mask for security
                "username": session.username,
                "role": session.role,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "last_activity": session.last_activity.isoformat() if session.last_activity else None,
                "ip_address": session.ip_address,
            }
            sessions.append(result)
        return sessions
