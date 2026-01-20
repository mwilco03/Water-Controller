"""
Water Treatment Controller - Users Management Router
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

User management endpoints for admin operations.
All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...core.auth import require_admin_access
from ...core.errors import build_success_response
from ...core.logging import get_logger
from ...core.password_policy import (
    DEFAULT_POLICY,
    calculate_password_expiry,
    validate_password,
)
from ...persistence.audit import log_audit
from ...persistence.users import (
    check_password_status,
    create_user,
    delete_user,
    get_user,
    get_user_by_username,
    get_users,
    get_users_for_sync,
    unlock_user,
    update_user,
)

logger = get_logger(__name__)

router = APIRouter()


class UserCreate(BaseModel):
    """Request body for creating a user."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    role: str = Field(default="viewer", pattern="^(viewer|operator|admin)$")
    active: bool = Field(default=True)
    sync_to_rtus: bool = Field(default=True)


class UserUpdate(BaseModel):
    """Request body for updating a user."""

    password: str | None = Field(default=None, min_length=1)
    role: str | None = Field(default=None, pattern="^(viewer|operator|admin)$")
    active: bool | None = None
    sync_to_rtus: bool | None = None


class UserResponse(BaseModel):
    """User response model (no password hash exposed)."""

    id: int
    username: str
    role: str
    active: bool
    sync_to_rtus: bool
    created_at: str | None = None
    updated_at: str | None = None
    last_login: str | None = None
    password_changed_at: str | None = None
    password_expires_at: str | None = None


class PasswordPolicyResponse(BaseModel):
    """Password policy configuration response."""

    min_length: int
    max_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digit: bool
    require_special: bool
    password_expiry_days: int | None
    max_failed_attempts: int
    lockout_duration_minutes: int


@router.get("")
async def list_users(
    request: Request,
    include_inactive: bool = False,
    session: dict = Depends(require_admin_access),
):
    """
    List all users.

    Admin access required.
    """
    users = get_users(include_inactive=include_inactive)

    # Remove sensitive fields
    safe_users = []
    for user in users:
        safe_user = {k: v for k, v in user.items() if k != "password_hash"}
        safe_users.append(safe_user)

    return build_success_response(safe_users)


@router.get("/policy")
async def get_password_policy(
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Get current password policy configuration.

    Admin access required.
    """
    return build_success_response({
        "min_length": DEFAULT_POLICY.min_length,
        "max_length": DEFAULT_POLICY.max_length,
        "require_uppercase": DEFAULT_POLICY.require_uppercase,
        "require_lowercase": DEFAULT_POLICY.require_lowercase,
        "require_digit": DEFAULT_POLICY.require_digit,
        "require_special": DEFAULT_POLICY.require_special,
        "password_expiry_days": DEFAULT_POLICY.password_expiry_days,
        "max_failed_attempts": DEFAULT_POLICY.max_failed_attempts,
        "lockout_duration_minutes": DEFAULT_POLICY.lockout_duration_minutes,
    })


@router.get("/sync")
async def get_sync_users(
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Get users configured for RTU synchronization.

    Returns users with sync_to_rtus=True for PROFINET sync.
    Admin access required.
    """
    users = get_users_for_sync()
    return build_success_response(users)


@router.get("/{user_id}")
async def get_user_by_id(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Get a specific user by ID.

    Admin access required.
    """
    user = get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "message": f"User with ID {user_id} not found",
            }
        )

    # Remove sensitive fields
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return build_success_response(safe_user)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    body: UserCreate,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Create a new user.

    Admin access required.
    """
    # Check if username already exists
    existing = get_user_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Username already exists",
                "code": "USER_EXISTS",
                "message": f"User '{body.username}' already exists",
            }
        )

    # Validate password against policy
    is_valid, errors = validate_password(body.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Password does not meet policy requirements",
                "code": "INVALID_PASSWORD",
                "message": "; ".join(errors),
                "policy_errors": errors,
            }
        )

    # Create user
    user_data = {
        "username": body.username,
        "password": body.password,
        "role": body.role,
        "active": body.active,
        "sync_to_rtus": body.sync_to_rtus,
        "password_expires_at": calculate_password_expiry(),
    }

    user_id = create_user(user_data)

    log_audit(
        session.get("username", "admin"),
        "create",
        "user",
        body.username,
        f"Created user '{body.username}' with role '{body.role}'",
        ip_address=request.client.host if request.client else None,
    )

    logger.info(f"User created: {body.username} by {session.get('username')}")

    # Return created user
    user = get_user(user_id)
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return build_success_response(safe_user)


@router.put("/{user_id}")
async def update_existing_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Update an existing user.

    Admin access required.
    """
    # Check user exists
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "message": f"User with ID {user_id} not found",
            }
        )

    # Validate password if being changed
    if body.password:
        is_valid, errors = validate_password(body.password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Password does not meet policy requirements",
                    "code": "INVALID_PASSWORD",
                    "message": "; ".join(errors),
                    "policy_errors": errors,
                }
            )

    # Build update dict
    update_data = {}
    if body.password is not None:
        update_data["password"] = body.password
        update_data["password_expires_at"] = calculate_password_expiry()
    if body.role is not None:
        update_data["role"] = body.role
    if body.active is not None:
        update_data["active"] = body.active
    if body.sync_to_rtus is not None:
        update_data["sync_to_rtus"] = body.sync_to_rtus

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "No fields to update",
                "code": "NO_UPDATE",
                "message": "At least one field must be provided for update",
            }
        )

    success = update_user(user_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to update user",
                "code": "UPDATE_FAILED",
                "message": "An error occurred while updating the user",
            }
        )

    # Log changes
    changes = ", ".join(f"{k}={v}" for k, v in update_data.items() if k != "password")
    if body.password:
        changes = "password changed" + (f", {changes}" if changes else "")

    log_audit(
        session.get("username", "admin"),
        "update",
        "user",
        existing["username"],
        f"Updated user '{existing['username']}': {changes}",
        ip_address=request.client.host if request.client else None,
    )

    logger.info(f"User updated: {existing['username']} by {session.get('username')}")

    # Return updated user
    user = get_user(user_id)
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    return build_success_response(safe_user)


@router.post("/{user_id}/unlock")
async def unlock_user_account(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Unlock a locked user account.

    Admin access required.
    """
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "message": f"User with ID {user_id} not found",
            }
        )

    success = unlock_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to unlock user",
                "code": "UNLOCK_FAILED",
                "message": "An error occurred while unlocking the user",
            }
        )

    log_audit(
        session.get("username", "admin"),
        "unlock",
        "user",
        existing["username"],
        f"Unlocked user account '{existing['username']}'",
        ip_address=request.client.host if request.client else None,
    )

    logger.info(f"User unlocked: {existing['username']} by {session.get('username')}")

    return build_success_response({"unlocked": True, "username": existing["username"]})


@router.get("/{user_id}/password-status")
async def get_user_password_status(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Get password status for a user (expiry, locked status, etc.).

    Admin access required.
    """
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "message": f"User with ID {user_id} not found",
            }
        )

    status_info = check_password_status(user_id)
    return build_success_response(status_info)


@router.delete("/{user_id}")
async def delete_existing_user(
    user_id: int,
    request: Request,
    session: dict = Depends(require_admin_access),
):
    """
    Delete a user.

    Admin access required. Cannot delete own account.
    """
    # Check user exists
    existing = get_user(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "User not found",
                "code": "USER_NOT_FOUND",
                "message": f"User with ID {user_id} not found",
            }
        )

    # Prevent self-deletion
    if existing["username"] == session.get("username"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Cannot delete own account",
                "code": "SELF_DELETE",
                "message": "You cannot delete your own account",
            }
        )

    success = delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to delete user",
                "code": "DELETE_FAILED",
                "message": "An error occurred while deleting the user",
            }
        )

    log_audit(
        session.get("username", "admin"),
        "delete",
        "user",
        existing["username"],
        f"Deleted user '{existing['username']}'",
        ip_address=request.client.host if request.client else None,
    )

    logger.info(f"User deleted: {existing['username']} by {session.get('username')}")

    return build_success_response({"deleted": True, "username": existing["username"]})
