"""
Water Treatment Controller - Control/Actuator Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Access Model:
- GET endpoints: View access (no authentication required)
- POST/PUT/DELETE endpoints: Control access (authentication required)
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from ...core.auth import log_control_action, require_control_access
from ...core.errors import build_success_response
from ...core.exceptions import (
    CommandRejectedError,
    ControlNotFoundError,
    RtuNotConnectedError,
)
from ...core.rtu_utils import get_data_quality, get_rtu_or_404
from ...models.audit import CommandAudit, CommandResult
from ...models.base import get_db
from ...models.rtu import RTU, Control, ControlType, RtuState
from ...schemas.common import DataQuality
from ...schemas.control import (
    CommandResponse,
    ControlCommand,
    ControlListMeta,
    ControlState,
)

router = APIRouter()


def get_control_or_404(db: Session, rtu: RTU, tag: str) -> Control:
    """Get control by tag or raise 404."""
    control = db.query(Control).filter(
        Control.rtu_id == rtu.id,
        Control.tag == tag
    ).first()
    if not control:
        raise ControlNotFoundError(rtu.station_name, tag)
    return control


@router.get("")
async def get_controls(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get current control states.
    """
    rtu = get_rtu_or_404(db, name)

    controls = db.query(Control).filter(Control.rtu_id == rtu.id).order_by(Control.tag).all()

    quality = get_data_quality(rtu.state)
    now = datetime.now(UTC)

    result = []
    for control in controls:
        # Build control state based on type
        if control.control_type == ControlType.DISCRETE:
            state_obj = ControlState(
                tag=control.tag,
                type=control.equipment_type or "discrete",
                control_type=control.control_type,
                state="OFF",  # Placeholder - would come from real I/O
                commanded_state="OFF",
                quality=quality,
                timestamp=now,
                interlock_active=False,
                available_commands=["ON"] if quality == DataQuality.GOOD else [],
            )
        else:  # Analog
            state_obj = ControlState(
                tag=control.tag,
                type=control.equipment_type or "analog",
                control_type=control.control_type,
                value=0.0,  # Placeholder
                commanded_value=0.0,
                unit=control.unit,
                min_value=control.min_value or 0.0,
                max_value=control.max_value or 100.0,
                quality=quality,
                timestamp=now,
                interlock_active=False,
            )

        result.append(state_obj.model_dump())

    meta = ControlListMeta(
        rtu_state=rtu.state,
        last_io_update=now if rtu.state == RtuState.RUNNING else None,
    )

    return {
        "data": result,
        "meta": meta.model_dump(),
    }


@router.post("/{tag}/command")
async def send_command(
    name: str = Path(..., description="RTU station name"),
    tag: str = Path(..., description="Control tag"),
    command: ControlCommand = None,
    db: Session = Depends(get_db),
    session: dict = Depends(require_control_access)
) -> dict[str, Any]:
    """
    Issue command to a control.

    Commands are routed THROUGH the RTU - never direct to actuator.
    RTU applies local interlocks.

    **Idempotency**: If `idempotency_key` is provided, duplicate requests
    with the same key return the original result. This ensures safe retries
    in field deployments with unreliable networks.

    **Authentication Required**: This is a control action requiring
    operator or admin role.
    """
    rtu = get_rtu_or_404(db, name)
    control = get_control_or_404(db, rtu, tag)

    # Idempotency check: Return cached result if this request was already processed
    if command.idempotency_key:
        existing = db.query(CommandAudit).filter(
            CommandAudit.idempotency_key == command.idempotency_key
        ).first()
        if existing:
            # Return the original response for this idempotent request
            response_data = CommandResponse(
                tag=existing.control_tag,
                command=existing.command if existing.value is None else None,
                value=existing.value,
                accepted=(existing.result == CommandResult.SUCCESS),
                previous_state=None,
                new_state=existing.command if existing.value is None else None,
                timestamp=existing.timestamp,
                coupled_actions=[],
            )
            return build_success_response(response_data.model_dump())

    # Get username from authenticated session for audit trail
    username = session.get("username", "unknown")

    # Check RTU is connected
    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    # Determine command type
    is_discrete = control.control_type == ControlType.DISCRETE

    if is_discrete:
        if not command.command:
            raise CommandRejectedError(
                "Discrete control requires 'command' field",
                interlock=None,
            )
        cmd_value = command.command
    else:
        if command.value is None:
            raise CommandRejectedError(
                "Analog control requires 'value' field",
                interlock=None,
            )
        cmd_value = str(command.value)

    # Log command before execution (with idempotency key for safe retries)
    audit = CommandAudit(
        control_id=control.id,
        rtu_name=rtu.station_name,
        control_tag=tag,
        command=cmd_value,
        value=command.value if not is_discrete else None,
        result=CommandResult.SUCCESS,  # Will update on failure
        user=username,  # From authenticated session
        idempotency_key=command.idempotency_key,
    )
    db.add(audit)

    # Log control action for audit trail
    log_control_action(
        session=session,
        action="CONTROL_COMMAND",
        target=f"{rtu.station_name}/{tag}",
        details=f"{cmd_value}" + (f" value={command.value}" if not is_discrete else ""),
    )

    # In a real implementation, send command via IPC to C controller
    # For now, simulate success

    db.commit()

    now = datetime.now(UTC)

    response_data = CommandResponse(
        tag=tag,
        command=command.command if is_discrete else None,
        value=command.value if not is_discrete else None,
        accepted=True,
        previous_state="OFF" if is_discrete else None,
        new_state=command.command if is_discrete else None,
        timestamp=now,
        coupled_actions=[],  # Would be populated based on configuration
    )

    return build_success_response(response_data.model_dump())
