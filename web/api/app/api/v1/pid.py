"""
Water Treatment Controller - PID Loop Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.exceptions import PidLoopNotFoundError, ValidationError
from ...core.rtu_utils import get_rtu_or_404
from ...models.base import get_db
from ...models.pid import PidLoop
from ...schemas.pid import (
    AutoTuneRequest,
    AutoTuneResponse,
    ModeRequest,
    PidLoopCreate,
    PidLoopResponse,
    PidLoopUpdate,
    SetpointRequest,
    TuningRequest,
)
from ...services.profinet_client import ControllerNotConnectedError, get_profinet_client

router = APIRouter()


def pid_not_found(loop_id: int):
    """Raise 404 for PID loop not found."""
    raise PidLoopNotFoundError(loop_id)


@router.get("")
async def list_pid_loops(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List all PID loops for an RTU.
    """
    rtu = get_rtu_or_404(db, name)

    # Query PID loops by input_rtu (string station name)
    loops = db.query(PidLoop).filter(PidLoop.input_rtu == rtu.station_name).all()

    # Get live PV/CV from controller if available
    profinet = get_profinet_client()
    live_loops = {pid_loop["loop_id"]: pid_loop for pid_loop in profinet.get_pid_loops()}

    result = []
    for loop in loops:
        live = live_loops.get(loop.id, {})
        # Format process_variable and control_output as "rtu:slot" descriptors
        pv_desc = f"{loop.input_rtu}:slot{loop.input_slot}"
        cv_desc = f"{loop.output_rtu}:slot{loop.output_slot}"
        result.append(PidLoopResponse(
            id=loop.id,
            name=loop.name,
            process_variable=pv_desc,
            control_output=cv_desc,
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
) -> dict[str, Any]:
    """
    Create a new PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    # Parse process_variable and control_output as "rtu:slotN" or just slot number
    # Format: "RTU_NAME:slot5" or just "5" (assumes current RTU)
    from ...models.rtu import Control, Sensor

    def parse_slot_ref(ref: str, default_rtu: str) -> tuple[str, int]:
        """Parse slot reference like 'RTU1:slot5' or '5' into (rtu_name, slot_num)."""
        if ":" in ref:
            parts = ref.split(":", 1)
            rtu_name = parts[0]
            slot_str = parts[1].replace("slot", "")
        else:
            rtu_name = default_rtu
            slot_str = ref.replace("slot", "")
        return rtu_name, int(slot_str)

    input_rtu, input_slot = parse_slot_ref(request.process_variable, rtu.station_name)
    output_rtu, output_slot = parse_slot_ref(request.control_output, rtu.station_name)

    # Verify slot references are valid by checking sensors/controls exist
    sensor = db.query(Sensor).filter(
        Sensor.rtu_id == rtu.id,
        Sensor.slot_number == input_slot
    ).first()
    if not sensor:
        raise ValidationError(
            f"No sensor at slot {input_slot} on RTU '{input_rtu}'",
            details={"field": "process_variable"}
        )

    control = db.query(Control).filter(
        Control.rtu_id == rtu.id,
        Control.slot_number == output_slot
    ).first()
    if not control:
        raise ValidationError(
            f"No control at slot {output_slot} on RTU '{output_rtu}'",
            details={"field": "control_output"}
        )

    loop = PidLoop(
        name=request.name,
        input_rtu=input_rtu,
        input_slot=input_slot,
        output_rtu=output_rtu,
        output_slot=output_slot,
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

    pv_desc = f"{loop.input_rtu}:slot{loop.input_slot}"
    cv_desc = f"{loop.output_rtu}:slot{loop.output_slot}"
    return build_success_response(PidLoopResponse(
        id=loop.id,
        name=loop.name,
        process_variable=pv_desc,
        control_output=cv_desc,
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
) -> dict[str, Any]:
    """
    Get a specific PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
    ).first()
    if not loop:
        pid_not_found(loop_id)

    # Get live values
    profinet = get_profinet_client()
    live_loops = {pid_loop["loop_id"]: pid_loop for pid_loop in profinet.get_pid_loops()}
    live = live_loops.get(loop.id, {})

    pv_desc = f"{loop.input_rtu}:slot{loop.input_slot}"
    cv_desc = f"{loop.output_rtu}:slot{loop.output_slot}"
    return build_success_response(PidLoopResponse(
        id=loop.id,
        name=loop.name,
        process_variable=pv_desc,
        control_output=cv_desc,
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
) -> dict[str, Any]:
    """
    Update a PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
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
) -> dict[str, Any]:
    """
    Delete a PID loop.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
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
) -> dict[str, Any]:
    """
    Update PID loop setpoint.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
    ).first()
    if not loop:
        pid_not_found(loop_id)

    old_setpoint = loop.setpoint
    loop.setpoint = request.setpoint
    db.commit()

    # Send to controller
    profinet = get_profinet_client()
    try:
        profinet.set_setpoint(loop_id, request.setpoint)
    except ControllerNotConnectedError as e:
        raise HTTPException(status_code=503, detail=str(e))

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
) -> dict[str, Any]:
    """
    Update PID tuning parameters.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
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
) -> dict[str, Any]:
    """
    Update PID loop operating mode.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
    ).first()
    if not loop:
        pid_not_found(loop_id)

    old_mode = loop.mode
    loop.mode = request.mode.value
    db.commit()

    # Send to controller
    mode_map = {"MANUAL": 0, "AUTO": 1, "CASCADE": 2}
    profinet = get_profinet_client()
    try:
        profinet.set_pid_mode(loop_id, mode_map.get(request.mode.value, 1))
    except ControllerNotConnectedError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return build_success_response({
        "id": loop_id,
        "old_mode": old_mode,
        "new_mode": request.mode.value,
    })


@router.post("/{loop_id}/autotune")
async def start_autotune(
    name: str = Path(..., description="RTU station name"),
    loop_id: int = Path(..., description="PID loop ID"),
    request: AutoTuneRequest = None,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Start PID auto-tuning process.

    Supported methods:
    - ziegler-nichols: Classic step response method
    - cohen-coon: Better for processes with significant dead time
    - relay: Relay feedback method for oscillation-based tuning

    The auto-tune process runs asynchronously. Use GET to check status.
    """
    rtu = get_rtu_or_404(db, name)

    loop = db.query(PidLoop).filter(
        PidLoop.id == loop_id,
        PidLoop.input_rtu == rtu.station_name
    ).first()
    if not loop:
        pid_not_found(loop_id)

    # Validate tuning method
    valid_methods = ["ziegler-nichols", "cohen-coon", "relay"]
    if request.method not in valid_methods:
        raise ValidationError(
            f"Invalid tuning method. Must be one of: {', '.join(valid_methods)}",
            details={"field": "method", "valid_values": valid_methods}
        )

    # Auto-tuning requires step test data from the PROFINET controller
    # This is not yet implemented - return 501 Not Implemented
    # DO NOT return fake calculated parameters - that violates industrial control safety
    raise HTTPException(
        status_code=501,
        detail=(
            f"Auto-tuning method '{request.method}' is not yet implemented. "
            "Real PID auto-tuning requires performing a step test on the physical process "
            "to measure process gain, time constant, and dead time. "
            "Please configure PID parameters manually via PUT /{loop_id}/tuning."
        )
    )

    # DISABLED: The following code used placeholder values instead of real measurements.
    # This has been removed to comply with industrial control safety requirements.
    # When auto-tuning is implemented, it must:
    # 1. Trigger a step test via the C controller
    # 2. Measure actual process response (gain, time constant, dead time)
    # 3. Apply tuning formulas to measured values
    #
    # Store current tuning
    old_tuning = {"kp": loop.kp, "ki": loop.ki, "kd": loop.kd}  # noqa: F841 - kept for future use

    # For now, we implement a simplified Ziegler-Nichols calculation
    # In production, this would trigger an async step test on the controller
    if False and request.method == "ziegler-nichols":  # DISABLED - uses fake data
        # Simplified Z-N tuning based on step response characteristics
        # These would normally be measured from a step test
        # Using placeholder calculations for demonstration
        process_gain = 1.0  # Would be measured: delta_PV / delta_CV
        time_constant = 60.0  # Would be measured from step response
        dead_time = 5.0  # Would be measured from step response

        # Ziegler-Nichols formulas for PID
        kp = 1.2 * time_constant / (process_gain * dead_time)
        ki = kp / (2.0 * dead_time)
        kd = kp * 0.5 * dead_time

        new_tuning = {
            "kp": round(kp, 4),
            "ki": round(ki, 4),
            "kd": round(kd, 4),
        }

        metrics = {
            "process_gain": process_gain,
            "time_constant": time_constant,
            "dead_time": dead_time,
            "method": "ziegler-nichols",
        }

        # Apply new tuning
        loop.kp = new_tuning["kp"]
        loop.ki = new_tuning["ki"]
        loop.kd = new_tuning["kd"]
        db.commit()

        return build_success_response(AutoTuneResponse(
            loop_id=loop_id,
            method=request.method,
            status="completed",
            old_tuning=old_tuning,
            new_tuning=new_tuning,
            metrics=metrics,
            message="Auto-tune completed. New parameters applied.",
        ).model_dump())

    elif request.method == "cohen-coon":
        # Cohen-Coon method (better for dead time)
        process_gain = 1.0
        time_constant = 60.0
        dead_time = 10.0

        tau_ratio = dead_time / time_constant
        kp = (1.35 / process_gain) * (time_constant / dead_time + 0.185)
        ti = 2.5 * dead_time * (time_constant + 0.185 * dead_time) / (time_constant + 0.611 * dead_time)
        td = 0.37 * dead_time * time_constant / (time_constant + 0.185 * dead_time)

        ki = kp / ti
        kd_val = kp * td

        new_tuning = {
            "kp": round(kp, 4),
            "ki": round(ki, 4),
            "kd": round(kd_val, 4),
        }

        loop.kp = new_tuning["kp"]
        loop.ki = new_tuning["ki"]
        loop.kd = new_tuning["kd"]
        db.commit()

        return build_success_response(AutoTuneResponse(
            loop_id=loop_id,
            method=request.method,
            status="completed",
            old_tuning=old_tuning,
            new_tuning=new_tuning,
            metrics={
                "process_gain": process_gain,
                "time_constant": time_constant,
                "dead_time": dead_time,
                "tau_ratio": tau_ratio,
            },
            message="Cohen-Coon auto-tune completed.",
        ).model_dump())

    else:  # relay method
        # Relay method would require async operation
        return build_success_response(AutoTuneResponse(
            loop_id=loop_id,
            method=request.method,
            status="pending",
            old_tuning=old_tuning,
            new_tuning=None,
            metrics=None,
            message=f"Relay auto-tune started. Settle time: {request.settle_time}s",
        ).model_dump())
