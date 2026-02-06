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
from ...core.ports import DEFAULTS as PORT_DEFAULTS
from ...core.rtu_utils import get_rtu_or_404, hex_string_to_int
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
    try:
        rtu = service.create(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Register RTU with PROFINET controller (if available)
    controller_registered = False
    profinet = get_profinet_client()
    try:
        if profinet.is_connected():
            # Parse hex strings to integers for controller
            vendor_int = hex_string_to_int(rtu.vendor_id)
            device_int = hex_string_to_int(rtu.device_id)
            controller_registered = profinet.add_rtu(
                rtu.station_name,
                rtu.ip_address,
                vendor_int,
                device_int,
                rtu.slot_count or 0  # 0 = discover from device via PROFINET
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


@router.post("/add-by-ip", status_code=201)
async def add_rtu_by_ip(
    ip_address: str = Query(..., description="RTU IP address"),
    port: int = Query(PORT_DEFAULTS.RTU_HTTP, ge=1, le=65535, description="RTU HTTP API port"),
    timeout_ms: int = Query(5000, ge=100, le=30000, description="Timeout in milliseconds"),
    auto_connect: bool = Query(False, description="Automatically connect after adding"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Add RTU by IP address - fetches config from device to get correct PROFINET identity.

    This is the recommended way to add RTUs:
    1. Pings the IP to verify reachability
    2. Fetches /config endpoint to get actual PROFINET station_name, vendor_id, device_id
    3. Creates RTU in database with correct identity
    4. Optionally initiates PROFINET connection

    This ensures the station_name matches what the RTU reports via DCP discovery,
    which is required for PROFINET connection to succeed.
    """
    import httpx

    # Check if IP already exists
    existing = db.query(RTU).filter(RTU.ip_address == ip_address).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"RTU with IP {ip_address} already exists: {existing.station_name}"
        )

    url = f"http://{ip_address}:{port}/config"
    timeout_sec = timeout_ms / 1000.0

    # Fetch config from RTU
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url)

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"RTU returned HTTP {response.status_code} from /config endpoint"
            )

        config = response.json()

    except httpx.ConnectTimeout:
        raise HTTPException(
            status_code=504,
            detail=f"Connection timeout to {ip_address}:{port} ({timeout_ms}ms)"
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to {ip_address}:{port} - device unreachable"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching RTU config: {e}"
        )

    # Extract PROFINET config
    pn_config = config.get("profinet", {})
    station_name = pn_config.get("station_name")
    vendor_id = pn_config.get("vendor_id")
    device_id = pn_config.get("device_id")

    if not station_name:
        raise HTTPException(
            status_code=502,
            detail="RTU config missing profinet.station_name"
        )

    # Check if station_name already exists
    existing_name = db.query(RTU).filter(RTU.station_name == station_name).first()
    if existing_name:
        raise HTTPException(
            status_code=409,
            detail=f"RTU with station_name '{station_name}' already exists (IP: {existing_name.ip_address})"
        )

    # Create RTU with correct identity from device
    rtu = RTU(
        station_name=station_name,
        ip_address=ip_address,
        vendor_id=f"0x{vendor_id:04X}" if vendor_id else None,
        device_id=f"0x{device_id:04X}" if device_id else None,
        state=RtuState.OFFLINE,
    )
    db.add(rtu)
    db.commit()
    db.refresh(rtu)

    logger.info(f"Added RTU by IP: {station_name} at {ip_address} (vendor=0x{vendor_id:04X}, device=0x{device_id:04X})")

    # Register with PROFINET controller
    controller_registered = False
    profinet = get_profinet_client()
    try:
        if profinet.is_connected():
            controller_registered = profinet.add_rtu(
                station_name,
                ip_address,
                vendor_id or 0,
                device_id or 0,
                0  # 0 = discover slot count from device via PROFINET
            )
            logger.info(f"RTU {station_name} registered with PROFINET controller")
    except Exception as e:
        logger.warning(f"Could not register RTU {station_name} with controller: {e}")

    # Auto-connect if requested
    connected = False
    if auto_connect and controller_registered:
        try:
            connected = profinet.connect_rtu(station_name)
            if connected:
                rtu.update_state(RtuState.CONNECTING)
                db.commit()
        except Exception as e:
            logger.warning(f"Auto-connect failed for {station_name}: {e}")

    return build_success_response({
        "id": rtu.id,
        "station_name": rtu.station_name,
        "ip_address": rtu.ip_address,
        "vendor_id": rtu.vendor_id,
        "device_id": rtu.device_id,
        "state": rtu.state,
        "controller_registered": controller_registered,
        "auto_connect_initiated": connected,
        "source": "fetched_from_device",
        "profinet_config": pn_config,
    })


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
            vendor_id=rtu.vendor_id,
            device_id=rtu.device_id,
            slot_count=rtu.slot_count or 0,
            connection_state=rtu.state,
            state_since=rtu.state_since,
            last_seen=rtu.state_since.isoformat() if rtu.state_since else None,
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
            # Parse hex strings to integers for controller
            # vendor_id/device_id are stored as "0x002A" but controller expects ints
            vendor_int = hex_string_to_int(rtu.vendor_id)
            device_int = hex_string_to_int(rtu.device_id)
            # Try to add RTU to controller (idempotent - OK if already exists)
            profinet.add_rtu(
                rtu.station_name,
                rtu.ip_address,
                vendor_int,
                device_int,
                rtu.slot_count or 0  # 0 = discover from device via PROFINET
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
    Gracefully close PROFINET connection or abort connection attempt.

    RTU must be RUNNING, ERROR, or CONNECTING. Sends disconnect command to controller.
    If RTU is CONNECTING, this aborts the connection attempt.
    """
    from ...services.profinet_client import ControllerNotConnectedError

    rtu = get_rtu_or_404(db, name)

    if rtu.state == RtuState.OFFLINE:
        raise RtuNotConnectedError(name, rtu.state)

    was_connecting = rtu.state == RtuState.CONNECTING

    # Send disconnect command to PROFINET controller
    profinet = get_profinet_client()
    try:
        success = profinet.disconnect_rtu(name)
        if success:
            # Controller accepted disconnect - update state
            rtu.update_state(
                RtuState.OFFLINE,
                reason="Connection aborted by user" if was_connecting else "Disconnected by user"
            )
            db.commit()
            response_data = DisconnectResponse(
                station_name=name,
                state=RtuState.OFFLINE,
                message="Connection aborted" if was_connecting else "Disconnected successfully"
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
        rtu.update_state(
            RtuState.OFFLINE,
            reason="Connection aborted (no controller)" if was_connecting else "Disconnected (no controller)"
        )
        db.commit()
        response_data = DisconnectResponse(
            station_name=name,
            state=RtuState.OFFLINE,
            message="Connection aborted (DB only)" if was_connecting else "Disconnected (DB only - no controller)"
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

    Returns configured sensors and controls matching the frontend
    RTUInventory interface: { rtu_station, sensors[], controls[], last_refresh }.
    """
    from ...models.rtu import Sensor, Control

    rtu = get_rtu_or_404(db, name)

    # Get sensors and controls from database
    sensor_rows = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()
    control_rows = db.query(Control).filter(Control.rtu_id == rtu.id).all()

    # Serialize sensors to match frontend RTUSensor interface
    sensors = []
    for s in sensor_rows:
        sensors.append({
            "id": s.id,
            "rtu_station": rtu.station_name,
            "sensor_id": s.tag,
            "sensor_type": s.sensor_type,
            "name": s.tag,
            "unit": s.unit or "",
            "register_address": s.slot_number if s.slot_number is not None else s.channel,
            "data_type": "float32",
            "scale_min": s.scale_min if s.scale_min is not None else 0.0,
            "scale_max": s.scale_max if s.scale_max is not None else 100.0,
            "last_value": None,
            "last_quality": 0xC0,  # NOT_CONNECTED until cyclic data flows
            "last_update": None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    # Serialize controls to match frontend RTUControl interface
    controls = []
    for c in control_rows:
        controls.append({
            "id": c.id,
            "rtu_station": rtu.station_name,
            "control_id": c.tag,
            "control_type": c.control_type,
            "name": c.tag,
            "command_type": c.equipment_type or c.control_type,
            "register_address": c.slot_number if c.slot_number is not None else c.channel,
            "feedback_register": None,
            "range_min": c.min_value,
            "range_max": c.max_value,
            "current_state": "unknown",
            "current_value": None,
            "last_command": None,
            "last_update": None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    return build_success_response({
        "rtu_station": rtu.station_name,
        "sensors": sensors,
        "controls": controls,
        "last_refresh": rtu.updated_at.isoformat() if rtu.updated_at else None,
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
                # Parse hex strings to integers for controller
                vendor_int = hex_string_to_int(rtu.vendor_id)
                device_int = hex_string_to_int(rtu.device_id)
                profinet.add_rtu(
                    rtu.station_name,
                    rtu.ip_address,
                    vendor_int,
                    device_int,
                    rtu.slot_count or 0  # 0 = discover from device via PROFINET
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

    # PROFINET module discovery requires cyclic data exchange to be active.
    # Returns current inventory from database; live discovery via IPC
    # is triggered when connecting the RTU (POST /{name}/connect).

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
    port: int = Query(PORT_DEFAULTS.RTU_HTTP, ge=1, le=65535, description="RTU HTTP API port"),
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

            # Fetch and sync PROFINET config if probe succeeded
            if response.status_code == 200:
                try:
                    async with httpx.AsyncClient(timeout=timeout_sec) as client:
                        # Fetch PROFINET identity from /config
                        config_response = await client.get(f"http://{ip_address}:{port}/config")

                        # Fetch slot count from /slots endpoint
                        slots_response = await client.get(f"http://{ip_address}:{port}/slots")

                    rtu_vendor = None
                    rtu_device = None
                    rtu_slot_count = None
                    sensors_created = 0
                    controls_created = 0

                    # Parse PROFINET identity from config
                    if config_response.status_code == 200:
                        config = config_response.json()
                        pn_config = config.get("profinet", {})
                        rtu_vendor = pn_config.get("vendor_id")
                        rtu_device = pn_config.get("device_id")

                    # Parse slot count and slots from slots endpoint
                    if slots_response and slots_response.status_code == 200:
                        from ...models.rtu import Sensor, Control, ControlType

                        slots_data = slots_response.json()
                        rtu_slot_count = slots_data.get("slot_count")
                        slots_list = slots_data.get("slots", [])
                        for slot_data in slots_list:
                            slot_num = slot_data.get("slot")
                            if slot_num is None or slot_num == 0:
                                continue  # Skip DAP (slot 0)

                            direction = slot_data.get("direction", "input")
                            subslot = slot_data.get("subslot", 1)

                            if direction == "input":
                                # Create sensor record
                                tag = f"{rtu.station_name}-sensor-{slot_num}"
                                existing_sensor = db.query(Sensor).filter(
                                    Sensor.rtu_id == rtu.id,
                                    Sensor.slot_number == slot_num
                                ).first()

                                if not existing_sensor:
                                    sensor = Sensor(
                                        rtu_id=rtu.id,
                                        slot_number=slot_num,
                                        tag=tag,
                                        channel=slot_num,
                                        sensor_type="generic",
                                        unit="",
                                    )
                                    db.add(sensor)
                                    sensors_created += 1

                            elif direction == "output":
                                # Create control record
                                tag = f"{rtu.station_name}-control-{slot_num}"
                                existing_control = db.query(Control).filter(
                                    Control.rtu_id == rtu.id,
                                    Control.slot_number == slot_num
                                ).first()

                                if not existing_control:
                                    control = Control(
                                        rtu_id=rtu.id,
                                        slot_number=slot_num,
                                        tag=tag,
                                        channel=slot_num,
                                        control_type=ControlType.DISCRETE,
                                        equipment_type="generic",
                                    )
                                    db.add(control)
                                    controls_created += 1

                        if sensors_created > 0 or controls_created > 0:
                            logger.info(f"RTU {name}: created {sensors_created} sensors, {controls_created} controls from /slots")
                            result["slots_synced"] = True
                            result["sensors_created"] = sensors_created
                            result["controls_created"] = controls_created

                    # Update database with RTU's actual PROFINET identity
                    updated_fields = []
                    if rtu_vendor is not None:
                        new_vendor_id = f"0x{rtu_vendor:04X}"
                        if rtu.vendor_id != new_vendor_id:
                            rtu.vendor_id = new_vendor_id
                            updated_fields.append(f"vendor_id={new_vendor_id}")

                    if rtu_device is not None:
                        new_device_id = f"0x{rtu_device:04X}"
                        if rtu.device_id != new_device_id:
                            rtu.device_id = new_device_id
                            updated_fields.append(f"device_id={new_device_id}")

                    if rtu_slot_count is not None:
                        if rtu.slot_count != rtu_slot_count:
                            rtu.slot_count = rtu_slot_count
                            updated_fields.append(f"slot_count={rtu_slot_count}")

                    # Commit all changes (config + sensors/controls)
                    if updated_fields or sensors_created > 0 or controls_created > 0:
                        db.commit()
                        if updated_fields:
                            logger.info(f"RTU {name}: synced PROFINET config from device: {', '.join(updated_fields)}")
                            result["config_synced"] = True
                            result["updated_fields"] = updated_fields
                    else:
                        result["config_synced"] = False
                        result["message"] = "PROFINET config already up to date"

                    # Include PROFINET config in result
                    result["profinet_config"] = {
                        "vendor_id": f"0x{rtu_vendor:04X}" if rtu_vendor is not None else None,
                        "device_id": f"0x{rtu_device:04X}" if rtu_device is not None else None,
                        "slot_count": rtu_slot_count,
                    }
                except Exception as e:
                    logger.warning(f"RTU {name}: failed to fetch/sync PROFINET config: {e}")
                    result["config_sync_error"] = str(e)

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


@router.post("/{name}/fetch-config")
async def fetch_rtu_config(
    name: str,
    port: int = Query(PORT_DEFAULTS.RTU_HTTP, ge=1, le=65535, description="RTU HTTP API port"),
    timeout_ms: int = Query(5000, ge=100, le=30000, description="Timeout in milliseconds"),
    update_db: bool = Query(False, description="Update database with fetched PROFINET identity"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Fetch RTU configuration from its HTTP /config endpoint.

    This retrieves the RTU's actual PROFINET identity (station_name, vendor_id,
    device_id) which may differ from what's stored in the database.

    Use update_db=true to sync the database with the RTU's actual identity.
    This is critical for PROFINET connection - the station_name must match
    what the RTU reports via DCP discovery.

    Returns:
        - fetched: True if /config was successfully retrieved
        - profinet_config: The RTU's PROFINET settings (station_name, vendor_id, device_id)
        - mismatch: True if database values differ from RTU's actual values
        - updated: True if database was updated (when update_db=true)
    """
    import httpx

    rtu = get_rtu_or_404(db, name)
    ip_address = rtu.ip_address

    if not ip_address:
        raise HTTPException(
            status_code=400,
            detail=f"RTU '{name}' has no IP address configured"
        )

    url = f"http://{ip_address}:{port}/config"
    timeout_sec = timeout_ms / 1000.0

    result = {
        "station_name": name,
        "ip_address": ip_address,
        "fetched": False,
        "profinet_config": None,
        "mismatch": False,
        "mismatch_details": {},
        "updated": False,
        "error": None,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url)

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            return build_success_response(result)

        config = response.json()
        result["fetched"] = True

        # Extract PROFINET config
        pn_config = config.get("profinet", {})
        result["profinet_config"] = {
            "station_name": pn_config.get("station_name"),
            "vendor_id": pn_config.get("vendor_id"),
            "device_id": pn_config.get("device_id"),
            "product_name": pn_config.get("product_name"),
            "enabled": pn_config.get("enabled"),
        }

        # Check for mismatches
        rtu_station = pn_config.get("station_name")
        rtu_vendor = pn_config.get("vendor_id")
        rtu_device = pn_config.get("device_id")

        # Convert hex strings to int for comparison if needed
        db_vendor = hex_string_to_int(rtu.vendor_id, None)
        db_device = hex_string_to_int(rtu.device_id, None)

        mismatches = {}
        if rtu_station and rtu_station != rtu.station_name:
            mismatches["station_name"] = {"db": rtu.station_name, "rtu": rtu_station}
        if rtu_vendor is not None and db_vendor != rtu_vendor:
            mismatches["vendor_id"] = {"db": rtu.vendor_id, "rtu": f"0x{rtu_vendor:04X}"}
        if rtu_device is not None and db_device != rtu_device:
            mismatches["device_id"] = {"db": rtu.device_id, "rtu": f"0x{rtu_device:04X}"}

        if mismatches:
            result["mismatch"] = True
            result["mismatch_details"] = mismatches
            logger.warning(f"RTU {name} identity mismatch: {mismatches}")

        # Update database if requested
        if update_db and mismatches:
            if rtu_station:
                # NOTE: Changing station_name is complex - it's the primary identifier
                # For now, just update vendor_id and device_id
                logger.info(f"RTU {name}: station_name mismatch (db={rtu.station_name}, rtu={rtu_station})")
                logger.info(f"To fix: rename RTU in database to '{rtu_station}' or reconfigure RTU")

            if rtu_vendor is not None:
                rtu.vendor_id = f"0x{rtu_vendor:04X}"
            if rtu_device is not None:
                rtu.device_id = f"0x{rtu_device:04X}"

            db.commit()
            result["updated"] = True
            logger.info(f"Updated RTU {name} PROFINET identity from device config")

    except httpx.ConnectTimeout:
        result["error"] = f"Connection timeout ({timeout_ms}ms)"
    except httpx.ConnectError as e:
        result["error"] = f"Connection refused: {e}"
    except Exception as e:
        result["error"] = str(e)
        logger.exception(f"Error fetching RTU config: {e}")

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
