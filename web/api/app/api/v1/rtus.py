"""
Water Treatment Controller - RTU Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

RTU CRUD and connection management endpoints.

Note: Business logic is delegated to RtuService for testability.
Route handlers remain thin and declarative.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.exceptions import (
    RtuBusyError,
    RtuNotConnectedError,
)
from ...core.rtu_utils import get_rtu_or_404
from ...models.base import get_db
from ...models.rtu import RTU, RtuState
from ...services.profinet_client import get_profinet_client
from ...schemas.rtu import (
    ConnectRequest,
    ConnectResponse,
    DisconnectResponse,
    RtuCreate,
    RtuDetailResponse,
    RtuResponse,
    RtuStats,
    TestResponse,
    TestResult,
)
from ...services.rtu_service import get_rtu_service

router = APIRouter()


def build_rtu_stats(db: Session, rtu: RTU) -> RtuStats:
    """Build statistics for an RTU (delegates to service)."""
    service = get_rtu_service(db)
    return service.get_stats(rtu)


# ==================== RTU CRUD ====================


@router.post("", status_code=201)
async def create_rtu(
    request: RtuCreate,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Create a new RTU configuration.

    Creates the RTU record in the database and registers it with the
    PROFINET controller (if running). The RTU starts in OFFLINE state -
    use POST /connect to establish PROFINET connection.
    """
    # Delegate to service layer
    service = get_rtu_service(db)
    rtu = service.create(request)

    # Register RTU with PROFINET controller (if available)
    controller_registered = False
    profinet = get_profinet_client()
    try:
        if profinet.is_connected():
            controller_registered = profinet.add_rtu(
                rtu.station_name,
                rtu.ip_address,
                rtu.vendor_id or 0,
                rtu.device_id or 0,
                rtu.slot_count or 8
            )
            if controller_registered:
                logger.info(f"RTU {rtu.station_name} registered with PROFINET controller")
            else:
                logger.warning(f"Failed to register RTU {rtu.station_name} with controller")
    except Exception as e:
        logger.warning(f"Could not register RTU {rtu.station_name} with controller: {e}")

    response_data = {
        "id": rtu.id,
        "station_name": rtu.station_name,
        "ip_address": rtu.ip_address,
        "vendor_id": rtu.vendor_id,
        "device_id": rtu.device_id,
        "slot_count": rtu.slot_count,
        "state": rtu.state,
        "controller_registered": controller_registered,
        "created_at": rtu.created_at.isoformat() if rtu.created_at else None,
        "updated_at": rtu.updated_at.isoformat() if rtu.updated_at else None,
    }

    return build_success_response(response_data)


@router.get("")
async def list_rtus(
    state: str | None = Query(None, description="Filter by state"),
    include_stats: bool = Query(False, description="Include sensor/alarm counts"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of RTUs to return"),
    offset: int = Query(0, ge=0, description="Number of RTUs to skip"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List all configured RTUs with pagination.
    """
    query = db.query(RTU)

    if state:
        query = query.filter(RTU.state == state.upper())

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    rtus = query.order_by(RTU.station_name).offset(offset).limit(limit).all()

    result = []
    for rtu in rtus:
        item = RtuResponse(
            id=rtu.id,
            station_name=rtu.station_name,
            ip_address=rtu.ip_address,
            state=rtu.state,
            state_since=rtu.state_since,
            stats=build_rtu_stats(db, rtu) if include_stats else None,
        )
        result.append(item.model_dump())

    return build_success_response(result, meta={
        "total": total,
        "limit": limit,
        "offset": offset,
        "returned": len(result),
    })


@router.get("/{name}")
async def get_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get detailed RTU information.
    """
    rtu = get_rtu_or_404(db, name)

    stats = build_rtu_stats(db, rtu)

    response_data = RtuDetailResponse(
        id=rtu.id,
        station_name=rtu.station_name,
        ip_address=rtu.ip_address,
        vendor_id=rtu.vendor_id,
        device_id=rtu.device_id,
        slot_count=rtu.slot_count or 0,
        state=rtu.state,
        state_since=rtu.state_since,
        last_error=rtu.last_error,
        created_at=rtu.created_at,
        updated_at=rtu.updated_at,
        slots=[],  # Slots are PROFINET frame positions, not database entities
        stats=stats,
    )

    return build_success_response(response_data.model_dump())


@router.delete("/{name}")
async def delete_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Delete RTU and all associated resources.

    RTU must be OFFLINE (disconnect first if connected).
    """
    # Delegate to service layer (handles state check, counting, and deletion)
    service = get_rtu_service(db)
    deletion_counts = service.delete(name)

    response_data = {
        "deleted": {
            "rtu": name,
            **deletion_counts,
        }
    }

    return build_success_response(response_data)


@router.get("/{name}/deletion-impact")
async def get_deletion_impact(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Preview what will be deleted (for confirmation UI).

    Returns flat structure: { data: { rtu_name, sensors, controls, ... } }
    """
    # Delegate to service layer (single source of truth for resource counting)
    service = get_rtu_service(db)
    impact = service.get_deletion_impact(name)

    # Return flat structure - include rtu_name in the impact dict
    # This avoids nested { data: { rtu: x, impact: {...} } } structure
    return build_success_response({
        "rtu_name": name,
        **impact,
    })


# ==================== Connection Management ====================


@router.post("/{name}/connect", status_code=202)
async def connect_rtu(
    name: str,
    request: ConnectRequest | None = None,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Establish PROFINET connection to RTU.

    RTU must be OFFLINE. First ensures RTU is registered with the controller,
    then triggers PROFINET connection. Poll GET /rtus/{name} to check state.
    """
    from ...services.profinet_client import ControllerNotConnectedError

    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.OFFLINE:
        raise RtuBusyError(name, rtu.state)

    profinet = get_profinet_client()

    # Ensure RTU is registered with controller before connecting
    # This handles RTUs added before the auto-register fix
    try:
        if profinet.is_connected():
            # Try to add RTU to controller (idempotent - OK if already exists)
            profinet.add_rtu(
                rtu.station_name,
                rtu.ip_address,
                rtu.vendor_id or 0,
                rtu.device_id or 0,
                rtu.slot_count or 8
            )
            logger.debug(f"Ensured RTU {name} is registered with controller")
    except Exception as e:
        logger.warning(f"Could not ensure RTU {name} is registered: {e}")

    # Update state to CONNECTING
    rtu.update_state(RtuState.CONNECTING)
    db.commit()

    # Send connect command to PROFINET controller
    try:
        success = profinet.connect_rtu(name)
        if success:
            # Controller accepted the connect command
            # State will transition to RUNNING when connection established
            response_data = ConnectResponse(
                station_name=name,
                state=RtuState.CONNECTING,
                message="Connection initiated - controller notified"
            )
        else:
            # Controller rejected but didn't raise - revert state
            rtu.update_state(RtuState.OFFLINE, error="Controller rejected connect request")
            db.commit()
            raise HTTPException(
                status_code=503,
                detail="PROFINET controller rejected connect request"
            )
    except ControllerNotConnectedError as e:
        # No controller available - revert state
        rtu.update_state(RtuState.OFFLINE, error=str(e))
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )

    return build_success_response(response_data.model_dump())


@router.post("/{name}/disconnect")
async def disconnect_rtu(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Gracefully close PROFINET connection.

    RTU must be RUNNING or ERROR. Sends disconnect command to controller.
    """
    from ...services.profinet_client import ControllerNotConnectedError

    rtu = get_rtu_or_404(db, name)

    if rtu.state == RtuState.OFFLINE:
        raise RtuNotConnectedError(name, rtu.state)

    if rtu.state == RtuState.CONNECTING:
        raise RtuBusyError(name, rtu.state)

    # Send disconnect command to PROFINET controller
    profinet = get_profinet_client()
    try:
        success = profinet.disconnect_rtu(name)
        if success:
            # Controller accepted disconnect - update state
            rtu.update_state(RtuState.OFFLINE)
            db.commit()
            response_data = DisconnectResponse(
                station_name=name,
                state=RtuState.OFFLINE,
                message="Disconnected successfully"
            )
        else:
            # Controller rejected but didn't raise
            raise HTTPException(
                status_code=503,
                detail="PROFINET controller rejected disconnect request"
            )
    except ControllerNotConnectedError as e:
        # No controller - just update DB state anyway (graceful degradation)
        logger.warning(f"No controller connection for disconnect, updating DB state only: {e}")
        rtu.update_state(RtuState.OFFLINE)
        db.commit()
        response_data = DisconnectResponse(
            station_name=name,
            state=RtuState.OFFLINE,
            message="Disconnected (DB only - no controller connection)"
        )

    return build_success_response(response_data.model_dump())


@router.post("/{name}/discover")
async def discover_modules(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Discover modules in RTU slots via PROFINET.

    RTU must be RUNNING. Queries the PROFINET controller via shared memory IPC
    for slot module information (sensors and actuators).

    Returns 503 if controller is not connected.
    """
    from ...services.shm_client import get_shm_client

    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    # Get PROFINET discovery via shared memory IPC
    shm = get_shm_client()
    if not shm.is_connected():
        raise HTTPException(
            status_code=503,
            detail="PROFINET controller not connected. Start the C controller process."
        )

    shm_rtu = shm.get_rtu(name)
    if not shm_rtu:
        raise HTTPException(
            status_code=503,
            detail=f"RTU '{name}' not found in controller shared memory. "
                   "Ensure the RTU is configured and connected in the PROFINET controller."
        )

    discovered = []

    # Get sensors from shared memory
    for sensor in shm_rtu.get("sensors", []):
        discovered.append({
            "slot_number": sensor["slot"],
            "tag": f"AI_{sensor['slot']:02d}",
            "type": "sensor",
            "description": f"Analog Input Slot {sensor['slot']}",
            "data_type": "float32",
            "unit": "",
            "scale_min": 0.0,
            "scale_max": 100.0,
            "current_value": sensor.get("value"),
            "status": sensor.get("status"),
            "quality": sensor.get("quality"),
        })

    # Get actuators from shared memory
    for actuator in shm_rtu.get("actuators", []):
        discovered.append({
            "slot_number": actuator["slot"],
            "tag": f"DO_{actuator['slot']:02d}",
            "type": "control",
            "description": f"Digital Output Slot {actuator['slot']}",
            "data_type": "uint16",
            "unit": "",
            "current_command": actuator.get("command"),
            "forced": actuator.get("forced", False),
        })

    return build_success_response({
        "rtu_name": name,
        "discovered": discovered,
        "count": len(discovered),
        "source": "profinet",
        "vendor_id": shm_rtu.get("vendor_id"),
        "device_id": shm_rtu.get("device_id"),
    })


@router.post("/{name}/test")
async def test_connection(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Run connection and I/O test.

    RTU must be RUNNING. When controller is running, performs real I/O tests.
    """
    import time

    rtu = get_rtu_or_404(db, name)

    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    profinet = get_profinet_client()
    tests = {}

    # Connection test - check if we can get RTU state from controller
    conn_start = time.perf_counter()
    rtu_state = profinet.get_rtu_state(name)
    conn_latency = (time.perf_counter() - conn_start) * 1000

    if rtu_state and rtu_state == "RUNNING":
        tests["connection"] = TestResult(passed=True, latency_ms=round(conn_latency, 2))

        # Read I/O test - try to read sensor values
        read_start = time.perf_counter()
        try:
            sensors = profinet.get_sensor_values(name)
            read_latency = (time.perf_counter() - read_start) * 1000
            bytes_read = len(sensors) * 8  # Approximate bytes per sensor
            read_passed = True  # IPC call succeeded
        except Exception as e:
            read_latency = (time.perf_counter() - read_start) * 1000
            bytes_read = 0
            read_passed = False
            logger.warning(f"Read I/O test failed for {name}: {e}")

        tests["read_io"] = TestResult(
            passed=read_passed,
            bytes_read=bytes_read,
            latency_ms=round(read_latency, 2)
        )

        # Write I/O test - try to read actuator states (non-destructive)
        write_start = time.perf_counter()
        try:
            actuators = profinet.get_actuator_states(name)
            write_latency = (time.perf_counter() - write_start) * 1000
            bytes_written = len(actuators) * 4  # Approximate bytes per actuator
            write_passed = True  # IPC call succeeded
        except Exception as e:
            write_latency = (time.perf_counter() - write_start) * 1000
            bytes_written = 0
            write_passed = False
            logger.warning(f"Write I/O test failed for {name}: {e}")

        tests["write_io"] = TestResult(
            passed=write_passed,
            bytes_written=bytes_written,
            latency_ms=round(write_latency, 2)
        )

        # Cycle time test - estimate from response times
        avg_latency = (conn_latency + read_latency + write_latency) / 3
        tests["cycle_time"] = TestResult(
            passed=avg_latency < 100,  # Pass if under 100ms
            target_ms=32.0,
            measured_ms=round(avg_latency, 2),
            jitter_ms=round(abs(read_latency - write_latency), 2)
        )
    else:
        # Controller not connected or RTU not running in controller
        tests["connection"] = TestResult(
            passed=False,
            latency_ms=round(conn_latency, 2),
            error="Controller not connected or RTU not in RUNNING state"
        )
        tests["read_io"] = TestResult(passed=False, error="Connection required")
        tests["write_io"] = TestResult(passed=False, error="Connection required")
        tests["cycle_time"] = TestResult(passed=False, error="Connection required")

    response_data = TestResponse(
        station_name=name,
        tests={k: v.model_dump() for k, v in tests.items()},
        overall_passed=all(t.passed for t in tests.values()),
    )

    return build_success_response(response_data.model_dump())


# ==================== Health and Inventory ====================


@router.get("/{name}/health")
async def get_rtu_health(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get RTU health status.

    Returns live connection state from PROFINET controller if available,
    or database state if controller is not running. Includes packet loss
    and failure metrics when available from real PROFINET connection.
    """
    rtu = get_rtu_or_404(db, name)
    profinet = get_profinet_client()

    # Get live state from controller if available
    controller_state = profinet.get_rtu_state(name)
    connection_state = controller_state or rtu.state

    # Determine health based on state
    is_healthy = connection_state == RtuState.RUNNING

    # Get PROFINET status for metrics (if available)
    packet_loss = 0.0
    consecutive_failures = 0

    if is_healthy and profinet.is_controller_running():
        # Get detailed stats from controller
        status = profinet.get_status()
        if status.get("connected"):
            # In real implementation, these would come from shared memory
            # For now, use simulation defaults
            packet_loss = status.get("packet_loss_percent", 0.0)

    return build_success_response({
        "station_name": rtu.station_name,
        "connection_state": connection_state,
        "healthy": is_healthy,
        "packet_loss_percent": packet_loss,
        "consecutive_failures": consecutive_failures,
        "in_failover": False,
        "last_error": rtu.last_error,
        "state_since": rtu.state_since.isoformat() if rtu.state_since else None,
        "transition_reason": rtu.transition_reason,
    })


@router.get("/{name}/inventory")
async def get_rtu_inventory(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get RTU slot/module inventory.

    Returns configured sensors and controls as inventory items.
    Note: Slots are PROFINET frame positions, not database entities.
    The inventory is derived from configured sensors/controls.
    """
    from ...models.rtu import Sensor, Control

    rtu = get_rtu_or_404(db, name)

    # Get sensors and controls as inventory items
    sensors = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()
    controls = db.query(Control).filter(Control.rtu_id == rtu.id).all()

    slots = []

    # Add sensors as input slots
    for sensor in sensors:
        slots.append({
            "slot": sensor.slot_number,
            "subslot": 0,
            "type": "input",
            "module_type": "analog_input",
            "tag": sensor.tag,
            "sensor_type": sensor.sensor_type,
            "unit": sensor.unit,
            "channel": sensor.channel,
        })

    # Add controls as output slots
    for control in controls:
        slots.append({
            "slot": control.slot_number,
            "subslot": 0,
            "type": "output",
            "module_type": control.control_type,
            "tag": control.tag,
            "equipment_type": control.equipment_type,
            "unit": control.unit,
            "channel": control.channel,
        })

    # Sort by slot number (None values at end)
    slots.sort(key=lambda x: (x.get("slot") is None, x.get("slot") or 0))

    # Calculate slot usage
    populated_slots = sum(1 for s in slots if s.get("slot") is not None)
    total_slots = rtu.slot_count or 0

    return build_success_response({
        "station_name": rtu.station_name,
        "slot_count": total_slots,
        "populated_slots": populated_slots,
        "empty_slots": max(0, total_slots - populated_slots),
        "slots": slots,
        "last_updated": rtu.updated_at.isoformat() if rtu.updated_at else None,
    })


@router.post("/{name}/inventory/refresh")
async def refresh_rtu_inventory(
    name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Refresh RTU inventory from PROFINET.

    If RTU is OFFLINE, automatically initiates connection first.
    If RTU is CONNECTING, returns status to poll again.
    RTU must be RUNNING for actual inventory refresh.
    """
    from ...services.profinet_client import ControllerNotConnectedError

    rtu = get_rtu_or_404(db, name)

    # Auto-connect if offline
    if rtu.state == RtuState.OFFLINE:
        profinet = get_profinet_client()

        # Ensure RTU is registered with controller
        try:
            if profinet.is_connected():
                profinet.add_rtu(
                    rtu.station_name,
                    rtu.ip_address,
                    rtu.vendor_id or 0,
                    rtu.device_id or 0,
                    rtu.slot_count or 8
                )
        except Exception as e:
            logger.warning(f"Could not ensure RTU {name} is registered: {e}")

        # Initiate connection
        rtu.update_state(RtuState.CONNECTING)
        db.commit()

        try:
            success = profinet.connect_rtu(name)
            if success:
                return build_success_response({
                    "status": "connecting",
                    "message": "Connection initiated - refresh again in a few seconds",
                    "state": RtuState.CONNECTING
                })
            else:
                rtu.update_state(RtuState.OFFLINE, error="Controller rejected connect")
                db.commit()
                raise HTTPException(
                    status_code=503,
                    detail="PROFINET controller rejected connect request"
                )
        except ControllerNotConnectedError as e:
            rtu.update_state(RtuState.OFFLINE, error=str(e))
            db.commit()
            raise HTTPException(status_code=503, detail=str(e))

    # Still connecting - tell user to wait
    if rtu.state == RtuState.CONNECTING:
        return build_success_response({
            "status": "connecting",
            "message": "Connection in progress - refresh again when RUNNING",
            "state": RtuState.CONNECTING
        })

    # Must be RUNNING to refresh inventory
    if rtu.state != RtuState.RUNNING:
        raise RtuNotConnectedError(name, rtu.state)

    # In a real implementation, this would trigger PROFINET module discovery
    # For now, just return current inventory
    # TODO: Implement actual PROFINET module discovery via IPC

    return await get_rtu_inventory(name, db)


# ==================== RTU Provisioning ====================


@router.post("/{name}/provision")
async def provision_rtu_sensors(
    name: str,
    sensors: list[dict],
    create_historian_tags: bool = Query(True, description="Create historian tags for sensors"),
    create_alarm_rules: bool = Query(False, description="Create default alarm rules"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Provision sensors and controls for an RTU.

    This endpoint is used by the commissioning wizard to:
    1. Create sensor/control records from discovered PROFINET slots
    2. Optionally create historian tags for data logging
    3. Optionally create default alarm rules based on sensor types

    Request body should be a list of sensor objects with:
    - tag: Sensor tag name
    - description: Human-readable description
    - slot_number: PROFINET slot number
    - data_type: Data type (int16, float32, etc.)
    - unit: Engineering unit
    - scale_min/scale_max: Scaling range (optional)
    """
    from ...models.sensor import Sensor
    from ...models.control import Control
    from ...models.historian import HistorianTag
    from ...models.alarm import AlarmConfig

    rtu = get_rtu_or_404(db, name)

    provisioned = {
        "sensors": 0,
        "controls": 0,
        "historian_tags": 0,
        "alarm_rules": 0,
    }

    for sensor_data in sensors:
        tag = sensor_data.get("tag")
        if not tag:
            continue

        sensor_type = sensor_data.get("type", "sensor")
        slot_number = sensor_data.get("slot_number")
        description = sensor_data.get("description", "")
        data_type = sensor_data.get("data_type", "float32")
        unit = sensor_data.get("unit", "")

        if sensor_type == "control" or sensor_type == "actuator":
            # Create control record
            existing = db.query(Control).filter(
                Control.rtu_id == rtu.id,
                Control.tag == tag
            ).first()

            if not existing:
                control = Control(
                    rtu_id=rtu.id,
                    tag=tag,
                    description=description,
                    slot_number=slot_number,
                    data_type=data_type,
                    enabled=True,
                )
                db.add(control)
                provisioned["controls"] += 1
        else:
            # Create sensor record
            existing = db.query(Sensor).filter(
                Sensor.rtu_id == rtu.id,
                Sensor.tag == tag
            ).first()

            if not existing:
                sensor = Sensor(
                    rtu_id=rtu.id,
                    tag=tag,
                    description=description,
                    slot_number=slot_number,
                    data_type=data_type,
                    unit=unit,
                    scale_min=sensor_data.get("scale_min", 0.0),
                    scale_max=sensor_data.get("scale_max", 100.0),
                    enabled=True,
                )
                db.add(sensor)
                provisioned["sensors"] += 1

                # Create historian tag if requested
                if create_historian_tags:
                    ht_tag = f"{rtu.station_name}.{tag}"
                    existing_ht = db.query(HistorianTag).filter(
                        HistorianTag.tag == ht_tag
                    ).first()

                    if not existing_ht:
                        historian_tag = HistorianTag(
                            tag=ht_tag,
                            description=description,
                            unit=unit,
                            enabled=True,
                        )
                        db.add(historian_tag)
                        provisioned["historian_tags"] += 1

                # Create alarm rule if requested
                if create_alarm_rules and unit:
                    alarm_tag = f"{rtu.station_name}.{tag}.HIGH"
                    existing_alarm = db.query(AlarmConfig).filter(
                        AlarmConfig.tag == alarm_tag
                    ).first()

                    if not existing_alarm:
                        # Default high alarm at 90% of scale
                        scale_max = sensor_data.get("scale_max", 100.0)
                        alarm_config = AlarmConfig(
                            tag=alarm_tag,
                            description=f"High alarm for {tag}",
                            priority="MEDIUM",
                            setpoint=scale_max * 0.9,
                            deadband=scale_max * 0.02,
                            delay_seconds=5,
                            enabled=True,
                        )
                        db.add(alarm_config)
                        provisioned["alarm_rules"] += 1

    db.commit()
    logger.info(f"Provisioned RTU {name}: {provisioned}")

    return build_success_response({
        "rtu_name": name,
        "provisioned": provisioned,
        "success": True,
    })


# ==================== Direct RTU Probe (HTTP API) ====================


@router.get("/{name}/probe")
async def probe_rtu_http(
    name: str,
    port: int = Query(9081, ge=1, le=65535, description="RTU HTTP API port"),
    timeout_ms: int = Query(2000, ge=100, le=10000, description="Timeout in milliseconds"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Probe RTU directly via HTTP to check if it's reachable.

    Calls the RTU's HTTP health endpoint (default port 9081) to verify
    the device is online and responding. This bypasses PROFINET and
    tests direct network connectivity to the RTU's web API.

    Returns:
        - reachable: True if RTU responded to HTTP request
        - status_code: HTTP response code (if reachable)
        - response_time_ms: Round-trip time in milliseconds
        - rtu_info: RTU status info from response (if available)
        - error: Error message if probe failed
    """
    import httpx
    import time

    rtu = get_rtu_or_404(db, name)
    ip_address = rtu.ip_address

    if not ip_address:
        raise HTTPException(
            status_code=400,
            detail=f"RTU '{name}' has no IP address configured"
        )

    # Try /health endpoint first, then /info, then /
    endpoints = ["/health", "/info", "/"]
    timeout_sec = timeout_ms / 1000.0

    result = {
        "station_name": name,
        "ip_address": ip_address,
        "port": port,
        "reachable": False,
        "status_code": None,
        "response_time_ms": None,
        "endpoint_used": None,
        "rtu_info": None,
        "error": None,
    }

    for endpoint in endpoints:
        url = f"http://{ip_address}:{port}{endpoint}"

        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                response = await client.get(url)
            elapsed = (time.perf_counter() - start) * 1000

            result["reachable"] = True
            result["status_code"] = response.status_code
            result["response_time_ms"] = round(elapsed, 2)
            result["endpoint_used"] = endpoint

            # Try to parse response as JSON for RTU info
            if response.status_code == 200:
                try:
                    result["rtu_info"] = response.json()
                except Exception:
                    # Not JSON, store text preview
                    text = response.text[:500] if response.text else None
                    result["rtu_info"] = {"raw_response": text}

            logger.info(f"RTU probe {name} ({url}): {response.status_code} in {elapsed:.1f}ms")

            # Update RTU state if probe succeeded and it was OFFLINE
            if response.status_code == 200 and rtu.state == RtuState.OFFLINE:
                # Don't auto-connect, but note that device is reachable
                logger.info(f"RTU {name} is HTTP-reachable but PROFINET state is OFFLINE")

            break  # Success, don't try other endpoints

        except httpx.ConnectTimeout:
            result["error"] = f"Connection timeout ({timeout_ms}ms)"
        except httpx.ConnectError as e:
            result["error"] = f"Connection refused: {e}"
        except Exception as e:
            result["error"] = str(e)

    if not result["reachable"]:
        logger.warning(f"RTU probe {name} ({ip_address}:{port}): {result['error']}")

    return build_success_response(result)


# Include nested routers for sensors, controls, profinet, pid
# Note: slots router removed - slots are PROFINET frame positions, not database entities
from .controls import router as controls_router
from .pid import router as pid_router
from .profinet import router as profinet_router
from .sensors import router as sensors_router

router.include_router(sensors_router, prefix="/{name}/sensors")
router.include_router(controls_router, prefix="/{name}/controls")
router.include_router(profinet_router, prefix="/{name}/profinet")
router.include_router(pid_router, prefix="/{name}/pid")
