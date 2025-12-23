"""
Water Treatment Controller - PID Loop Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Path, HTTPException
from sqlalchemy.orm import Session

from ...core.exceptions import RtuNotFoundError, ValidationError
from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU
from ...models.pid import PidLoop, PidMode
from ...schemas.pid import (
    PidLoopCreate,
    PidLoopUpdate,
    PidLoopResponse,
    SetpointRequest,
    TuningRequest,
    ModeRequest,
)
from ...services.profinet_client import get_profinet_client

router = APIRouter()


def get_rtu_or_404(db: Session, name: str) -> RTU:
    """Get RTU by station name or raise 404."""
    rtu = db.query(RTU).filter(RTU.station_name == name).first()
    if not rtu:
        raise RtuNotFoundError(name)
    return rtu


def pid_not_found(loop_id: int):
    """Raise 404 for PID loop not found."""
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "PID_LOOP_NOT_FOUND",
                "message": f"PID loop {loop_id} not found",
            }
        }
    )


@router.get("")
async def list_pid_loops(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List all PID loops for an RTU.
    """
    rtu = get_rtu_or_404(db, name)

    loops = db.query(PidLoop).filter(PidLoop.rtu_id == rtu.id).all()

    # Get live PV/CV from controller if available
    profinet = get_profinet_client()
    live_loops = {l["loop_id"]: l for l in profinet.get_pid_loops()}

    result = []
    for loop in loops:
        live = live_loops.get(loop.id, {})
        result.append(PidLoopResponse(
            id=loop.id,
            name=loop.name,
            process_variable=loop.pv_sensor_tag,
            control_output=loop.cv_control_tag,
            setpoint=loop.setpoint,
            kp=loop.kp,
            ki=loop.ki,
            kd=loop.kd,
            output_min=loop.output_min,
            output_max=loop.output_max,
            mode=loop.mode,
            enabled=loop.enabled,
            pv=live.get("pv"),
            cv=live.get("cv"),
            error=live.get("pv", 0) - loop.setpoint if live.get("pv") is not None else None,
        ).model_dump())

    return build_success_response(result)


@router.post("", status_code=201)
async def create_pid_loop(
    name: str = Path(..., description="RTU station name"),
    request: PidLoopCreate = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Create a new PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    # Verify sensor and control tags exist
    from ...models.rtu import Sensor, Control

    sensor = db.query(Sensor).filter(
        Sensor.rtu_id == rtu.id,
        Sensor.tag == request.process_variable
    ).first()
    if not sensor:
        raise ValidationError(
            f"Sensor tag '{request.process_variable}' not found on RTU",
            details={"field": "process_variable"}
        )

    control = db.query(Control).filter(
        Control.rtu_id == rtu.id,
        Control.tag == request.control_output
    ).first()
    if not control:
        raise ValidationError(
            f"Control tag '{request.control_output}' not found on RTU",
            details={"field": "control_output"}
        )

    loop = PidLoop(
        rtu_id=rtu.id,
        name=request.name,
        pv_sensor_tag=request.process_variable,
        cv_control_tag=request.control_output,
        setpoint=request.setpoint,
        kp=request.kp,
        ki=request.ki,
        kd=request.kd,
        output_min=request.output_min,
        output_max=request.output_max,
        mode=request.mode.value,
        enabled=request.enabled,
    )
    db.add(loop)
    db.commit()
    db.refresh(loop)

    return build_success_response(PidLoopResponse(
        id=loop.id,
        name=loop.name,
        process_variable=loop.pv_sensor_tag,
        control_output=loop.cv_control_tag,
        setpoint=loop.setpoint,
        kp=loop.kp,
        ki=loop.ki,
        kd=loop.kd,
        output_min=loop.output_min,
        output_max=loop.output_max,
        mode=loop.mode,
        enabled=loop.enabled,
    ).model_dump())


@router.get("/{loop_id}")
async def get_pid_loop(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get a specific PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    # Get live values
    profinet = get_profinet_client()
    live_loops = {l["loop_id"]: l for l in profinet.get_pid_loops()}
    live = live_loops.get(loop.id, {})

    return build_success_response(PidLoopResponse(
        id=loop.id,
        name=loop.name,
        process_variable=loop.pv_sensor_tag,
        control_output=loop.cv_control_tag,
        setpoint=loop.setpoint,
        kp=loop.kp,
        ki=loop.ki,
        kd=loop.kd,
        output_min=loop.output_min,
        output_max=loop.output_max,
        mode=loop.mode,
        enabled=loop.enabled,
        pv=live.get("pv"),
        cv=live.get("cv"),
        error=live.get("pv", 0) - loop.setpoint if live.get("pv") is not None else None,
    ).model_dump())


@router.put("/{loop_id}")
async def update_pid_loop(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    request: PidLoopUpdate = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update a PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    # Update fields
    if request.name is not None:
        loop.name = request.name
    if request.setpoint is not None:
        loop.setpoint = request.setpoint
    if request.kp is not None:
        loop.kp = request.kp
    if request.ki is not None:
        loop.ki = request.ki
    if request.kd is not None:
        loop.kd = request.kd
    if request.output_min is not None:
        loop.output_min = request.output_min
    if request.output_max is not None:
        loop.output_max = request.output_max
    if request.mode is not None:
        loop.mode = request.mode.value
    if request.enabled is not None:
        loop.enabled = request.enabled

    db.commit()

    return build_success_response({"id": loop.id, "updated": True})


@router.delete("/{loop_id}")
async def delete_pid_loop(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Delete a PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    db.delete(loop)
    db.commit()

    return build_success_response({"id": loop_id, "deleted": True})


@router.put("/{loop_id}/setpoint")
async def update_setpoint(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    request: SetpointRequest = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update PID loop setpoint.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    old_setpoint = loop.setpoint
    loop.setpoint = request.setpoint
    db.commit()

    # Send to controller
    profinet = get_profinet_client()
    profinet.set_setpoint(loop_id, request.setpoint)

    return build_success_response({
        "id": loop_id,
        "old_setpoint": old_setpoint,
        "new_setpoint": request.setpoint,
    })


@router.put("/{loop_id}/tuning")
async def update_tuning(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    request: TuningRequest = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update PID tuning parameters.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    old_tuning = {"kp": loop.kp, "ki": loop.ki, "kd": loop.kd}
    loop.kp = request.kp
    loop.ki = request.ki
    loop.kd = request.kd
    db.commit()

    return build_success_response({
        "id": loop_id,
        "old_tuning": old_tuning,
        "new_tuning": {"kp": request.kp, "ki": request.ki, "kd": request.kd},
    })


@router.put("/{loop_id}/mode")
async def update_mode(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    request: ModeRequest = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Update PID loop operating mode.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.rtu_id == rtu.id
    ).first()
    if not loop:
        pid_not_found(loop_id)

    old_mode = loop.mode
    loop.mode = request.mode.value
    db.commit()

    # Send to controller
    mode_map = {"MANUAL": 0, "AUTO": 1, "CASCADE": 2}
    profinet = get_profinet_client()
    profinet.set_pid_mode(loop_id, mode_map.get(request.mode.value, 1))

    return build_success_response({
        "id": loop_id,
        "old_mode": old_mode,
        "new_mode": request.mode.value,
    })
