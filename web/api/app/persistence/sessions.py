"""
Water Treatment Controller - Sessions Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User session management operations.
"""

import json
import logging
from datetime import datetime
from typing import Any

from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)


def create_session(token: str, username: str, role: str, groups: list[str],
                   expires_at: datetime, ip_address: str | None = None,
                   user_agent: str | None = None) -> bool:
    """Create a new user session"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO user_sessions (token, username, role, groups, expires_at,
                    ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (token, username, role, json.dumps(groups), expires_at.isoformat(),
                  ip_address, user_agent))
            conn.commit()
            log_audit(username, 'login', 'session', token[:8],
                      f"User {username} logged in", ip_address)
            return True
        except Exception as e:
            # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
            logger.error(
                f"Session creation failed: {e}. "
                "User login not persisted. "
                "Check database connectivity and have user retry login."
            )
            return False


def get_session(token: str) -> dict[str, Any] | None:
    """Get session by token"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_sessions
            WHERE token = ? AND expires_at > datetime('now')
        ''', (token,))
        row = cursor.fetchone()
        if row:
            session = dict(row)
            # Parse groups from JSON
            if session.get('groups'):
                try:
                    session['groups'] = json.loads(session['groups'])
                except json.JSONDecodeError:
                    session['groups'] = []
            return session
        return None


def update_session_activity(token: str) -> bool:
    """Update session last activity time"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_sessions SET last_activity = CURRENT_TIMESTAMP
            WHERE token = ?
        ''', (token,))
        conn.commit()
        return cursor.rowcount > 0


def delete_session(token: str) -> bool:
    """Delete a session (logout)"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get username for audit log
        cursor.execute('SELECT username FROM user_sessions WHERE token = ?', (token,))
        row = cursor.fetchone()
        username = row['username'] if row else 'unknown'

        cursor.execute('DELETE FROM user_sessions WHERE token = ?', (token,))
        conn.commit()

        if cursor.rowcount > 0:
            log_audit(username, 'logout', 'session', token[:8],
                      f"User {username} logged out")
            return True
        return False


def delete_session_by_prefix(token_prefix: str, admin_user: str | None = None) -> bool:
    """Delete a session by token prefix (for admin session termination)"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Find the session matching the prefix
        cursor.execute('''
            SELECT token, username FROM user_sessions
            WHERE token LIKE ? AND expires_at > datetime('now')
        ''', (token_prefix + '%',))
        row = cursor.fetchone()

        if not row:
            return False

        full_token = row['token']
        username = row['username']

        cursor.execute('DELETE FROM user_sessions WHERE token = ?', (full_token,))
        conn.commit()

        if cursor.rowcount > 0:
            log_audit(admin_user or 'admin', 'terminate_session', 'session',
                      full_token[:8], f"Admin terminated session for {username}")
            return True
        return False


def cleanup_expired_sessions() -> int:
    """Remove expired sessions"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM user_sessions WHERE expires_at < datetime('now')
        ''')
        conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired sessions")
        return deleted


def get_active_sessions(username: str | None = None) -> list[dict[str, Any]]:
    """Get all active sessions, optionally filtered by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        if username:
            cursor.execute('''
                SELECT token, username, role, created_at, last_activity, ip_address
                FROM user_sessions
                WHERE username = ? AND expires_at > datetime('now')
                ORDER BY last_activity DESC
            ''', (username,))
        else:
            cursor.execute('''
                SELECT token, username, role, created_at, last_activity, ip_address
                FROM user_sessions
                WHERE expires_at > datetime('now')
                ORDER BY last_activity DESC
            ''')
        sessions = []
        for row in cursor.fetchall():
            session = dict(row)
            # Mask token for security
            session['token'] = session['token'][:8] + '...'
            sessions.append(session)
        return sessions
