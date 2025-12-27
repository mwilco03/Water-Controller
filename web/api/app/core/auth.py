"""
Water Treatment Controller - Authorization Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Authorization middleware and dependencies for the read-first access model:
- All GET requests: No authentication required (view access)
- All WebSocket connections: No authentication required (view access)
- POST/PUT/DELETE requests: Authentication required (control access)

This implements industrial SCADA best practices where:
- Situational awareness should never be blocked by login screens
- View access enables monitoring from any station
- Control actions require accountability (audit trail)
"""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..persistence.sessions import get_session, create_session, update_session_activity
from ..persistence.users import authenticate_user
from ..persistence.audit import log_command
from .logging import get_logger

logger = get_logger(__name__)

# Session configuration
SESSION_DURATION_HOURS = 8
COMMAND_MODE_DURATION_MINUTES = 5

# Optional bearer token security (won't fail if not provided)
optional_bearer = HTTPBearer(auto_error=False)


async def get_token_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """
    Extract token from Authorization header.
    Supports both Bearer token and direct header value.
    """
    if credentials and credentials.credentials:
        return credentials.credentials

    if authorization:
        if authorization.startswith("Bearer "):
            return authorization[7:]
        return authorization

    return None


async def get_current_session(
    token: Optional[str] = Depends(get_token_from_header)
) -> Optional[dict]:
    """
    Get current session if token is valid.
    Returns None if no token or invalid token (no error raised).
    """
    if not token:
        return None

    session = get_session(token)
    if session:
        # Update last activity
        update_session_activity(token)
        return session

    return None


async def require_control_access(
    request: Request,
    session: Optional[dict] = Depends(get_current_session)
) -> dict:
    """
    Dependency for control endpoints - requires authenticated operator.

    Raises 401 Unauthorized if:
    - No valid session token provided
    - Session has expired

    Returns the session dict with user info for audit logging.
    """
    if not session:
        logger.warning(
            "Control access denied - no valid session",
            extra={"path": request.url.path, "method": request.method}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Authentication required for control actions",
                "code": "AUTH_REQUIRED",
                "message": "Please authenticate to perform this control action"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check role - must be at least operator
    role = session.get("role", "viewer")
    if role not in ("operator", "admin"):
        logger.warning(
            f"Control access denied - insufficient role: {role}",
            extra={"username": session.get("username"), "path": request.url.path}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Insufficient permissions",
                "code": "INSUFFICIENT_ROLE",
                "message": "Operator or Admin role required for control actions"
            }
        )

    return session


async def optional_session_for_audit(
    session: Optional[dict] = Depends(get_current_session)
) -> Optional[dict]:
    """
    Optional session for audit logging on view endpoints.
    Returns session if available, None otherwise (no error).
    """
    return session


def log_control_action(
    session: dict,
    action: str,
    target: str,
    details: str = None,
    success: bool = True
):
    """Log a control action for audit trail."""
    username = session.get("username", "unknown")
    log_command(
        username=username,
        command_type=action,
        target=target,
        parameters=details or "",
        result="success" if success else "failed"
    )


class AuthService:
    """
    Authentication service for login/logout operations.
    """

    @staticmethod
    def login(username: str, password: str, ip_address: str = None, user_agent: str = None) -> Optional[dict]:
        """
        Authenticate user and create session.

        Returns dict with token and user info on success, None on failure.
        """
        user = authenticate_user(username, password)
        if not user:
            logger.warning(f"Login failed for user: {username}")
            return None

        # Generate session token
        token = token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)

        # Create session
        success = create_session(
            token=token,
            username=user["username"],
            role=user["role"],
            groups=[],
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )

        if not success:
            logger.error(f"Failed to create session for user: {username}")
            return None

        logger.info(f"User logged in: {username} (role: {user['role']})")

        return {
            "token": token,
            "username": user["username"],
            "role": user["role"],
            "expires_at": expires_at.isoformat(),
        }

    @staticmethod
    def validate_session(token: str) -> Optional[dict]:
        """Validate a session token and return session info."""
        return get_session(token)


# Export auth service instance
auth_service = AuthService()
