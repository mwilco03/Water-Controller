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

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ...core.auth import log_control_action, require_control_access
from ...core.errors import build_success_response
from ...core.exceptions import (
    CommandRejectedError,
    ControlNotFoundError,
    RtuNotConnectedError,
)
from ...core.rtu_utils import get_data_quality, get_rtu_or_404
from ...services.profinet_client import ControllerNotConnectedError, get_profinet_client
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

    Retrieves live actuator states from the PROFINET controller (via shared memory)
    or from demo mode if enabled. Falls back to database configuration if no live
    data is available.
    """
    rtu = get_rtu_or_404(db, name)

    controls = db.query(Control).filter(Control.rtu_id == rtu.id).order_by(Control.tag).all()

    # Get live state from controller SHM (preferred over stale DB state)
    profinet = get_profinet_client()
    live_state = profinet.get_rtu_state(rtu.station_name)
    effective_state = live_state or rtu.state

    quality = get_data_quality(effective_state)
    now = datetime.now(UTC)

    # Get live actuator states from controller or demo mode
    live_actuators = profinet.get_actuator_states(name)

    # Build lookup by slot for efficient access
    actuator_by_slot = {a["slot"]: a for a in live_actuators}

    result = []
    for control in controls:
        # Try to get live state from controller/demo mode
        live = actuator_by_slot.get(control.slot, {})

        # Build control state based on type
        if control.control_type == ControlType.DISCRETE:
            # Map command values: 0=OFF, 1=ON, 2=PWM
            live_command = live.get("command", 0)
            state = "ON" if live_command == 1 else ("PWM" if live_command == 2 else "OFF")

            state_obj = ControlState(
                tag=control.tag,
                type=control.equipment_type or "discrete",
                control_type=control.control_type,
                state=state,
                commanded_state=state,
                quality=quality,
                timestamp=now,
                interlock_active=live.get("forced", False),
                available_commands=["ON", "OFF"] if quality == DataQuality.GOOD else [],
            )
        else:  # Analog
            live_value = live.get("pwm_duty", 0.0)

            state_obj = ControlState(
                tag=control.tag,
                type=control.equipment_type or "analog",
                control_type=control.control_type,
                value=float(live_value),
                commanded_value=float(live_value),
                unit=control.unit,
                min_value=control.min_value or 0.0,
                max_value=control.max_value or 100.0,
                quality=quality,
                timestamp=now,
                interlock_active=live.get("forced", False),
            )

        result.append(state_obj.model_dump())

    meta = ControlListMeta(
        rtu_state=effective_state,
        last_io_update=now if effective_state == RtuState.RUNNING else None,
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

    # Send command to C controller via shared memory / demo mode
    profinet = get_profinet_client()
    mode_code = 1 if command.command == "ON" else (2 if command.command == "PWM" else 0)
    try:
        if is_discrete:
            profinet.command_actuator(name, control.slot, mode_code)
        else:
            profinet.command_actuator(name, control.slot, 2, int(command.value))
    except ControllerNotConnectedError as e:
        raise HTTPException(status_code=503, detail=str(e))

    db.commit()

    now = datetime.now(UTC)

    # Get current state for proper before/after tracking
    actuator_states = profinet.get_actuator_states(name)
    current_state = next(
        (a for a in actuator_states if a.get("slot") == control.slot),
        {}
    )
    previous_state_val = (
        ("ON" if current_state.get("command", 0) == 1 else "OFF")
        if is_discrete else str(current_state.get("pwm_duty", 0.0))
    )

    response_data = CommandResponse(
        tag=tag,
        command=command.command if is_discrete else None,
        value=command.value if not is_discrete else None,
        accepted=True,
        previous_state=previous_state_val if is_discrete else None,
        new_state=command.command if is_discrete else None,
        timestamp=now,
        coupled_actions=[],
    )

    return build_success_response(response_data.model_dump())
