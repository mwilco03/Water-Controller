"""
Water Treatment Controller - Control/Actuator Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from ...core.exceptions import (
    RtuNotConnectedError,
    ControlNotFoundError,
    CommandRejectedError,
    CommandTimeoutError,
)
from ...core.errors import build_success_response
from ...core.rtu_utils import get_rtu_or_404, get_data_quality
from ...models.base import get_db
from ...models.rtu import RTU, Control, RtuState, ControlType
from ...models.audit import CommandAudit, CommandResult
from ...schemas.common import DataQuality
from ...schemas.control import (
    ControlState,
    ControlCommand,
    CommandResponse,
    ControlListMeta,
    CoupledAction,
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
) -> Dict[str, Any]:
    """
    Get current control states.
    """
    rtu = get_rtu_or_404(db, name)

    controls = db.query(Control).filter(Control.rtu_id == rtu.id).order_by(Control.tag).all()

    quality = get_data_quality(rtu.state)
    now = datetime.now(timezone.utc)

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
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Issue command to a control.

    Commands are routed THROUGH the RTU - never direct to actuator.
    RTU applies local interlocks.
    """
    rtu = get_rtu_or_404(db, name)
    control = get_control_or_404(db, rtu, tag)

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

    # Log command before execution
    audit = CommandAudit(
        control_id=control.id,
        rtu_name=rtu.station_name,
        control_tag=tag,
        command=cmd_value,
        value=command.value if not is_discrete else None,
        result=CommandResult.SUCCESS,  # Will update on failure
        user="system",  # Would come from auth context
    )
    db.add(audit)

    # In a real implementation, send command via IPC to C controller
    # For now, simulate success

    db.commit()

    now = datetime.now(timezone.utc)

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
