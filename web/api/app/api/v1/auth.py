"""
Water Treatment Controller - Authentication Router
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Authentication endpoints for the read-first access model.
Login is only required for control actions, not viewing.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.auth import auth_service
from ...core.logging import get_logger
from ...persistence.sessions import delete_session, get_session

logger = get_logger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body"""
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response body"""
    token: str
    username: str
    role: str
    expires_at: str


class SessionResponse(BaseModel):
    """Session info response"""
    authenticated: bool
    username: str | None = None
    role: str | None = None
    expires_at: str | None = None


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, body: LoginRequest):
    """
    Authenticate user and create session for control access.

    This endpoint is used when an operator attempts a control action
    and needs to authenticate. View access does not require login.
    """
    # Get client info for session tracking
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    result = auth_service.login(
        username=body.username,
        password=body.password,
        ip_address=ip_address,
        user_agent=user_agent
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Invalid credentials",
                "code": "INVALID_CREDENTIALS",
                "message": "Username or password is incorrect"
            }
        )

    return LoginResponse(**result)


@router.post("/logout")
async def logout(request: Request):
    """
    End the current session.

    After logout, the operator returns to view-only mode.
    """
    # Get token from header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return {"status": "ok", "message": "No active session"}

    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header

    if delete_session(token):
        logger.info("User logged out")
        return {"status": "ok", "message": "Logged out successfully"}

    return {"status": "ok", "message": "Session not found or already expired"}


@router.get("/session", response_model=SessionResponse)
async def get_session_info(request: Request):
    """
    Get current session information.

    Returns authentication status and user info if authenticated.
    This is a view endpoint - no authentication required to check session status.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return SessionResponse(authenticated=False)

    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    session = get_session(token)

    if not session:
        return SessionResponse(authenticated=False)

    return SessionResponse(
        authenticated=True,
        username=session.get("username"),
        role=session.get("role"),
        expires_at=session.get("expires_at")
    )
