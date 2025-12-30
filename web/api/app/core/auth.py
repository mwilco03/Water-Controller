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

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..persistence.audit import log_command
from ..persistence.sessions import create_session, get_session, update_session_activity
from ..persistence.users import authenticate_user
from .logging import get_logger

logger = get_logger(__name__)

# Session configuration
SESSION_DURATION_HOURS = 8
COMMAND_MODE_DURATION_MINUTES = 5

# Optional bearer token security (won't fail if not provided)
optional_bearer = HTTPBearer(auto_error=False)


async def get_token_from_header(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    authorization: str | None = Header(None),
) -> str | None:
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
    token: str | None = Depends(get_token_from_header)
) -> dict | None:
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
    session: dict | None = Depends(get_current_session)
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
    session: dict | None = Depends(get_current_session)
) -> dict | None:
    """
    Optional session for audit logging on view endpoints.
    Returns session if available, None otherwise (no error).
    """
    return session


def log_control_action(
    session: dict,
    action: str,
    target: str,
    details: str | None = None,
    success: bool = True
):
    """
    Log a control action for audit trail.

    Args:
        session: User session dict containing username, token, etc.
        action: The action type (e.g., "CONTROL_COMMAND")
        target: Target in format "rtu_station/control_id"
        details: Command details (e.g., "ON value=100")
        success: Whether the command succeeded
    """
    username = session.get("username", "unknown")

    # Parse target format: "rtu_station/control_id"
    parts = target.split("/", 1)
    rtu_station = parts[0] if len(parts) > 0 else "unknown"
    control_id = parts[1] if len(parts) > 1 else "unknown"

    # Extract command from details
    command = details or action

    log_command(
        username=username,
        rtu_station=rtu_station,
        control_id=control_id,
        command=command,
        session_token=session.get("token")
    )


class AuthService:
    """
    Authentication service for login/logout operations.
    """

    @staticmethod
    def login(username: str, password: str, ip_address: str | None = None, user_agent: str | None = None) -> dict | None:
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
        expires_at = datetime.now(UTC) + timedelta(hours=SESSION_DURATION_HOURS)

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
    def validate_session(token: str) -> dict | None:
        """Validate a session token and return session info."""
        return get_session(token)


# Export auth service instance
auth_service = AuthService()
