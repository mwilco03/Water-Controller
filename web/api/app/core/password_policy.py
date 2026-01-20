"""
Water Treatment Controller - Password Policy Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Password validation and policy enforcement for defense in depth.
Uses DJB2 hashing for RTU compatibility (lowest common denominator).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class PasswordPolicy:
    """Password policy configuration."""

    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = False
    require_lowercase: bool = False
    require_digit: bool = False
    require_special: bool = False
    password_expiry_days: int | None = 90  # None = never expires
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 15


# Default policy - basic requirements for industrial system
DEFAULT_POLICY = PasswordPolicy(
    min_length=8,
    max_length=128,
    require_uppercase=False,
    require_lowercase=False,
    require_digit=False,
    require_special=False,
    password_expiry_days=90,
    max_failed_attempts=5,
    lockout_duration_minutes=15,
)


def validate_password(password: str, policy: PasswordPolicy | None = None) -> tuple[bool, list[str]]:
    """
    Validate password against policy.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    if policy is None:
        policy = DEFAULT_POLICY

    errors: list[str] = []

    # Length checks
    if len(password) < policy.min_length:
        errors.append(f"Password must be at least {policy.min_length} characters")

    if len(password) > policy.max_length:
        errors.append(f"Password must be at most {policy.max_length} characters")

    # Complexity checks
    if policy.require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if policy.require_lowercase and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if policy.require_digit and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")

    if policy.require_special and not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        errors.append("Password must contain at least one special character")

    return len(errors) == 0, errors


def is_password_expired(
    password_changed_at: datetime | None,
    policy: PasswordPolicy | None = None
) -> bool:
    """Check if password has expired based on policy."""
    if policy is None:
        policy = DEFAULT_POLICY

    # No expiry configured
    if policy.password_expiry_days is None:
        return False

    # No change date recorded - treat as expired to force reset
    if password_changed_at is None:
        return True

    expiry_date = password_changed_at + timedelta(days=policy.password_expiry_days)
    return datetime.now(UTC) > expiry_date


def calculate_password_expiry(policy: PasswordPolicy | None = None) -> datetime | None:
    """Calculate when a newly set password will expire."""
    if policy is None:
        policy = DEFAULT_POLICY

    if policy.password_expiry_days is None:
        return None

    return datetime.now(UTC) + timedelta(days=policy.password_expiry_days)


def is_account_locked(
    locked_until: datetime | None
) -> bool:
    """Check if account is currently locked."""
    if locked_until is None:
        return False

    return datetime.now(UTC) < locked_until


def calculate_lockout_time(policy: PasswordPolicy | None = None) -> datetime:
    """Calculate when lockout should end."""
    if policy is None:
        policy = DEFAULT_POLICY

    return datetime.now(UTC) + timedelta(minutes=policy.lockout_duration_minutes)
