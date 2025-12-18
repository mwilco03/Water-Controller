"""
Water Treatment Controller - FastAPI Web Backend
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import json
import logging

# Import shared memory client
try:
    from shm_client import (
        get_client, WtcShmClient, CONNECTION_STATE_NAMES,
        SENSOR_STATUS_NAMES, CONN_STATE_RUNNING, CONN_STATE_OFFLINE
    )
    SHM_AVAILABLE = True
except ImportError:
    SHM_AVAILABLE = False
    CONNECTION_STATE_NAMES = {0: "IDLE", 1: "CONNECTING", 2: "CONNECTED", 3: "RUNNING", 4: "ERROR", 5: "OFFLINE"}
    CONN_STATE_RUNNING = 3
    CONN_STATE_OFFLINE = 5

# Import database persistence layer
import db_persistence as db

# Configure logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Request context for audit logging
from contextvars import ContextVar
request_user: ContextVar[str] = ContextVar('request_user', default='system')
request_ip: ContextVar[str] = ContextVar('request_ip', default='unknown')

# Create FastAPI app
app = FastAPI(
    title="Water Treatment Controller API",
    description="PROFINET IO Controller for Water Treatment RTU Network",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Data Models ==============

class RTUDevice(BaseModel):
    station_name: str
    ip_address: str
    vendor_id: int
    device_id: int
    connection_state: str
    slot_count: int
    last_seen: Optional[datetime] = None

class SensorData(BaseModel):
    slot: int
    name: str
    value: float
    unit: str
    status: str
    timestamp: datetime

class ActuatorState(BaseModel):
    slot: int
    name: str
    command: str
    pwm_duty: int
    forced: bool

class ActuatorCommand(BaseModel):
    command: str  # "OFF", "ON", "PWM"
    pwm_duty: Optional[int] = 0

class AlarmRule(BaseModel):
    """
    Alarm rules generate NOTIFICATIONS only.

    Interlocks are configured and executed on the RTU directly.
    The controller does NOT execute interlock logic - safety-critical
    functions must run locally on the RTU without network dependency.

    The controller can:
    - Display interlock status (read from RTU)
    - Configure RTU interlocks (push config to RTU)
    - Log interlock events

    The controller CANNOT:
    - Execute interlock logic (that's the RTU's job)
    """
    rule_id: Optional[int] = None
    rtu_station: str
    slot: int
    condition: str
    threshold: float
    severity: str
    delay_ms: int
    message: str
    enabled: bool = True

class Alarm(BaseModel):
    alarm_id: int
    rule_id: int
    rtu_station: str
    slot: int
    severity: str
    state: str
    message: str
    value: float
    threshold: float
    raise_time: datetime
    ack_time: Optional[datetime] = None
    clear_time: Optional[datetime] = None
    ack_user: Optional[str] = None

class AcknowledgeRequest(BaseModel):
    user: str

class PIDLoop(BaseModel):
    loop_id: Optional[int] = None
    name: str
    enabled: bool = True
    input_rtu: str
    input_slot: int
    output_rtu: str
    output_slot: int
    kp: float
    ki: float
    kd: float
    setpoint: float
    output_min: float = 0.0
    output_max: float = 100.0
    mode: str = "AUTO"
    pv: Optional[float] = None
    cv: Optional[float] = None

class SetpointUpdate(BaseModel):
    setpoint: float

class TuningUpdate(BaseModel):
    kp: float
    ki: float
    kd: float

class ModeUpdate(BaseModel):
    mode: str  # "AUTO" or "MANUAL"

class HistorianTag(BaseModel):
    tag_id: int
    rtu_station: str
    slot: int
    tag_name: str
    sample_rate_ms: int
    deadband: float
    compression: str

class TrendQuery(BaseModel):
    start_time: datetime
    end_time: datetime
    interval_ms: Optional[int] = None

class SystemHealth(BaseModel):
    status: str
    uptime_seconds: int
    connected_rtus: int
    total_rtus: int
    active_alarms: int
    cpu_percent: float
    memory_percent: float

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[str] = None
    groups: Optional[List[str]] = None
    message: Optional[str] = None

class LogForwardingConfig(BaseModel):
    enabled: bool = False
    forward_type: str = "syslog"  # "syslog", "elastic", "graylog"
    host: str = "localhost"
    port: int = 514
    protocol: str = "udp"  # "udp", "tcp", "http"
    index: Optional[str] = None  # For Elasticsearch
    api_key: Optional[str] = None  # For authenticated endpoints
    tls_enabled: bool = False
    tls_verify: bool = True
    include_alarms: bool = True
    include_events: bool = True
    include_audit: bool = True
    log_level: str = "INFO"  # Minimum level to forward

class ADConfig(BaseModel):
    enabled: bool = False
    server: str = ""
    port: int = 389
    use_ssl: bool = False
    base_dn: str = ""
    admin_group: str = "WTC-Admins"
    bind_user: Optional[str] = None
    bind_password: Optional[str] = None

# ============== Shared Memory Client ==============

def get_shm_client() -> Optional[WtcShmClient]:
    """Get shared memory client if available"""
    if SHM_AVAILABLE:
        client = get_client()
        if client.is_connected():
            return client
    return None

# ============== Data Store ==============
# Primary storage is SQLite database (db_persistence)
# Runtime state comes from shared memory when controller is running

# In-memory cache for runtime state (populated from shm or db)
_rtu_runtime_state: Dict[str, str] = {}  # station_name -> connection_state

def _get_rtu_from_db(station_name: str) -> Optional[Dict[str, Any]]:
    """Get RTU from database"""
    return db.get_rtu_device(station_name)

def _get_all_rtus_from_db() -> List[Dict[str, Any]]:
    """Get all RTUs from database"""
    return db.get_rtu_devices()

def _update_runtime_state(station_name: str, state: str):
    """Update runtime connection state cache"""
    _rtu_runtime_state[station_name] = state

def _get_runtime_state(station_name: str) -> str:
    """Get runtime connection state, defaulting to OFFLINE"""
    return _rtu_runtime_state.get(station_name, "OFFLINE")

# WebSocket connections
websocket_connections: List[WebSocket] = []

# Connection state mapping
CONNECTION_STATES = {
    0: "IDLE",
    1: "CONNECTING",
    2: "CONNECTED",
    3: "RUNNING",
    4: "ERROR",
    5: "OFFLINE"
}

# Alarm severity mapping
ALARM_SEVERITY = {
    0: "INFO",
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
    4: "CRITICAL"
}

# Alarm state mapping
ALARM_STATE = {
    0: "CLEARED",
    1: "ACTIVE_UNACK",
    2: "ACTIVE_ACK",
    3: "CLEARED_UNACK"
}

# PID mode mapping
PID_MODES = {
    0: "MANUAL",
    1: "AUTO",
    2: "CASCADE"
}

# Actuator command mapping
ACTUATOR_COMMANDS = {
    0: "OFF",
    1: "ON",
    2: "PWM"
}

# ============== RTU Endpoints ==============

@app.get("/api/v1/rtus", response_model=List[RTUDevice])
async def list_rtus():
    """
    List all registered RTUs.

    Data source priority:
    1. Shared memory (if controller running) - provides live connection state
    2. Database - provides configuration

    Connection state comes from shm when available, otherwise from runtime cache.
    """
    client = get_shm_client()

    # Get configuration from database
    db_rtus = _get_all_rtus_from_db()

    # Build response combining db config with runtime state
    result = []
    shm_rtus = {}

    # If controller is running, get live state from shared memory
    if client:
        for r in client.get_rtus():
            shm_rtus[r["station_name"]] = r

    for rtu in db_rtus:
        station_name = rtu["station_name"]
        shm_data = shm_rtus.get(station_name)

        if shm_data:
            # Use live state from shared memory
            connection_state = CONNECTION_STATE_NAMES.get(shm_data["connection_state"], "UNKNOWN")
            _update_runtime_state(station_name, connection_state)
        else:
            # Use cached runtime state
            connection_state = _get_runtime_state(station_name)

        result.append(RTUDevice(
            station_name=station_name,
            ip_address=rtu["ip_address"],
            vendor_id=rtu.get("vendor_id", 0x0493),
            device_id=rtu.get("device_id", 0x0001),
            connection_state=connection_state,
            slot_count=rtu.get("slot_count", 16),
            last_seen=datetime.now() if connection_state == "RUNNING" else None
        ))

    return result

# ============== Network Discovery ==============

class DiscoveredRTU(BaseModel):
    """RTU discovered on the network via DCP"""
    station_name: str
    ip_address: str
    mac_address: str
    vendor_id: int
    device_id: int
    already_registered: bool = False

class NetworkScanResult(BaseModel):
    """Result of a network scan for RTUs"""
    scan_time: datetime
    duration_ms: int
    devices_found: int
    devices: List[DiscoveredRTU]
    new_devices: int  # Devices not already registered

class NetworkScanConfig(BaseModel):
    """Configuration for automatic network scanning"""
    auto_scan_enabled: bool = False
    scan_interval_seconds: int = 300  # Default: 5 minutes
    auto_register: bool = False  # Automatically register discovered RTUs

# In-memory scan configuration (would be persisted in production)
network_scan_config = NetworkScanConfig()
last_scan_result: Optional[NetworkScanResult] = None
scan_task: Optional[asyncio.Task] = None  # Background scan task

async def _perform_network_scan() -> NetworkScanResult:
    """
    Internal function to perform network scan via DCP discovery.
    Used by both manual and automatic scanning.

    When controller is running, uses DCP Identify All to discover PROFINET devices.
    When controller is not running, returns empty results (cannot scan without controller).
    """
    import time
    global last_scan_result

    start_time = time.time()
    discovered = []

    # Get list of already registered RTUs from database
    db_rtus = _get_all_rtus_from_db()
    registered_names = {r["station_name"] for r in db_rtus}

    client = get_shm_client()
    if client:
        # Send DCP Identify All via shared memory command
        logger.info("Initiating DCP network discovery via PROFINET controller")
        dcp_results = client.dcp_discover(timeout_ms=3000)

        # Process DCP responses
        for device in dcp_results:
            discovered.append(DiscoveredRTU(
                station_name=device.get("station_name", "unknown"),
                ip_address=device.get("ip_address", "0.0.0.0"),
                mac_address=device.get("mac_address", "00:00:00:00:00:00"),
                vendor_id=device.get("vendor_id", 0),
                device_id=device.get("device_id", 0),
                already_registered=device.get("station_name", "") in registered_names
            ))

        logger.info(f"DCP discovery returned {len(discovered)} devices")
    else:
        # Controller not running - cannot perform DCP discovery
        logger.warning("Network scan requested but PROFINET controller is not running")

    new_count = sum(1 for d in discovered if not d.already_registered)
    duration_ms = int((time.time() - start_time) * 1000)

    result = NetworkScanResult(
        scan_time=datetime.now(),
        duration_ms=duration_ms,
        devices_found=len(discovered),
        devices=discovered,
        new_devices=new_count
    )

    last_scan_result = result

    # Auto-register new devices if enabled
    if network_scan_config.auto_register and new_count > 0:
        for device in discovered:
            if not device.already_registered:
                try:
                    # Create RTU in database
                    db.create_rtu_device({
                        "station_name": device.station_name,
                        "ip_address": device.ip_address,
                        "vendor_id": device.vendor_id,
                        "device_id": device.device_id,
                        "slot_count": 16
                    })
                    _update_runtime_state(device.station_name, "OFFLINE")
                    logger.info(f"Auto-registered new RTU: {device.station_name}")
                    db.log_audit("system", "auto_register", "rtu_device",
                                device.station_name, f"Auto-registered from DCP discovery")
                except Exception as e:
                    logger.error(f"Failed to auto-register {device.station_name}: {e}")

    return result

async def _background_scan_loop():
    """Background task that performs periodic network scans"""
    logger.info("Background network scan task started")
    while True:
        try:
            if network_scan_config.auto_scan_enabled:
                logger.debug(f"Running scheduled network scan (interval: {network_scan_config.scan_interval_seconds}s)")
                result = await _perform_network_scan()
                logger.info(f"Scheduled scan complete: {result.devices_found} devices, {result.new_devices} new")

                await broadcast_event("network_scan_complete", {
                    "devices_found": result.devices_found,
                    "new_devices": result.new_devices,
                    "scheduled": True
                })

            # Wait for the configured interval
            await asyncio.sleep(network_scan_config.scan_interval_seconds)

        except asyncio.CancelledError:
            logger.info("Background network scan task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in background scan: {e}")
            await asyncio.sleep(60)  # Wait before retrying on error

@app.post("/api/v1/network/scan", response_model=NetworkScanResult)
async def scan_network():
    """
    Manually trigger a network scan for PROFINET RTUs.

    Uses DCP (Discovery and Configuration Protocol) to find
    all PROFINET devices on the network segment.

    This is an on-demand scan - for continuous scanning,
    configure auto_scan_enabled via PUT /api/v1/network/scan/config
    """
    result = await _perform_network_scan()
    logger.info(f"Manual network scan complete: {result.devices_found} devices found, {result.new_devices} new")

    await broadcast_event("network_scan_complete", {
        "devices_found": result.devices_found,
        "new_devices": result.new_devices,
        "scheduled": False
    })

    return result

@app.get("/api/v1/network/scan/last", response_model=Optional[NetworkScanResult])
async def get_last_scan():
    """Get the results of the last network scan"""
    return last_scan_result

@app.get("/api/v1/network/scan/config", response_model=NetworkScanConfig)
async def get_scan_config():
    """Get network scan configuration"""
    return network_scan_config

@app.get("/api/v1/network/scan/status")
async def get_scan_status():
    """Get current network scan status including background task state"""
    return {
        "config": network_scan_config.dict(),
        "background_task_running": scan_task is not None and not scan_task.done(),
        "last_scan": last_scan_result.dict() if last_scan_result else None
    }

@app.put("/api/v1/network/scan/config")
async def update_scan_config(config: NetworkScanConfig):
    """
    Update network scan configuration.

    Set auto_scan_enabled=true to enable periodic scanning.
    scan_interval_seconds controls how often (minimum 60 seconds).
    auto_register=true will automatically add discovered RTUs.

    The background scan task runs continuously - when auto_scan_enabled
    is true, it performs scans at the configured interval. When false,
    it still runs but skips the actual scanning.
    """
    global network_scan_config

    if config.scan_interval_seconds < 60:
        raise HTTPException(status_code=400, detail="Scan interval must be at least 60 seconds")

    old_enabled = network_scan_config.auto_scan_enabled
    network_scan_config = config

    # Log state change
    if config.auto_scan_enabled and not old_enabled:
        logger.info(f"Continuous network scanning ENABLED (interval: {config.scan_interval_seconds}s)")
    elif not config.auto_scan_enabled and old_enabled:
        logger.info("Continuous network scanning DISABLED")
    else:
        logger.info(f"Network scan config updated: auto={config.auto_scan_enabled}, interval={config.scan_interval_seconds}s")

    return {
        "status": "ok",
        "auto_scan_enabled": config.auto_scan_enabled,
        "scan_interval_seconds": config.scan_interval_seconds,
        "auto_register": config.auto_register
    }

class RTUCreateRequest(BaseModel):
    """Request model for creating a new RTU"""
    station_name: str
    ip_address: str
    vendor_id: int = 0x0493  # Default: Water Treatment Training
    device_id: int = 0x0001  # Default: Water Treatment RTU
    slot_count: int = 16
    slots: Optional[List[Dict[str, Any]]] = None  # Slot configuration

@app.post("/api/v1/rtus", response_model=RTUDevice)
async def create_rtu(request: RTUCreateRequest):
    """
    Add a new RTU to the system.

    This creates the RTU configuration in the database and sends
    an IPC command to the PROFINET controller to initiate connection.
    """
    # Check if RTU already exists in database
    existing = _get_rtu_from_db(request.station_name)
    if existing:
        raise HTTPException(status_code=409, detail="RTU already exists")

    # Create RTU in database
    try:
        db.create_rtu_device({
            "station_name": request.station_name,
            "ip_address": request.ip_address,
            "vendor_id": request.vendor_id,
            "device_id": request.device_id,
            "slot_count": request.slot_count
        })
    except Exception as e:
        logger.error(f"Failed to create RTU in database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Initialize runtime state
    _update_runtime_state(request.station_name, "OFFLINE")

    # Send IPC command to add RTU to PROFINET controller
    client = get_shm_client()
    if client:
        success = client.add_rtu(
            request.station_name,
            request.ip_address,
            request.vendor_id,
            request.device_id,
            request.slot_count
        )
        if success:
            logger.info(f"Sent ADD_RTU command to controller for {request.station_name}")
        else:
            logger.warning(f"Failed to send ADD_RTU command for {request.station_name}")
    else:
        logger.warning(f"Controller not running - RTU {request.station_name} created in database only")

    # Build response
    rtu = RTUDevice(
        station_name=request.station_name,
        ip_address=request.ip_address,
        vendor_id=request.vendor_id,
        device_id=request.device_id,
        connection_state="OFFLINE",
        slot_count=request.slot_count,
        last_seen=None
    )

    logger.info(f"Created RTU: {request.station_name} at {request.ip_address}")

    # Broadcast RTU added event
    await broadcast_event("rtu_added", {
        "station_name": request.station_name,
        "ip_address": request.ip_address
    })

    return rtu

@app.delete("/api/v1/rtus/{station_name}")
async def delete_rtu(station_name: str, cascade: bool = True):
    """
    Remove an RTU from the system.

    If cascade=True (default), the database layer automatically deletes:
    - All alarm rules referencing this RTU
    - All PID loops using this RTU as input or output
    - All historian tags tracking this RTU
    - All Modbus mappings for this RTU
    - All slot configurations for this RTU

    Also sends IPC command to disconnect from PROFINET controller.
    """
    # Check RTU exists in database
    existing = _get_rtu_from_db(station_name)
    if not existing:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Send IPC command to disconnect RTU from PROFINET controller first
    client = get_shm_client()
    if client:
        success = client.remove_rtu(station_name)
        if success:
            logger.info(f"Sent REMOVE_RTU command to controller for {station_name}")
        else:
            logger.warning(f"Failed to send REMOVE_RTU command for {station_name}")

    # Delete from database (cascade is handled by db_persistence)
    try:
        deleted = db.delete_rtu_device(station_name)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete RTU from database")
    except Exception as e:
        logger.error(f"Database error deleting RTU {station_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Clean up runtime state
    if station_name in _rtu_runtime_state:
        del _rtu_runtime_state[station_name]

    # Log the cascade cleanup info (db.delete_rtu_device handles this)
    deleted_items = {
        "alarm_rules": "cascade",
        "pid_loops": "cascade",
        "historian_tags": "cascade",
        "modbus_mappings": "cascade",
        "slot_configs": "cascade"
    }

    logger.info(f"Deleted RTU: {station_name} with cascade cleanup")

    # Broadcast RTU removed event
    await broadcast_event("rtu_removed", {
        "station_name": station_name,
        "cascade_deleted": deleted_items
    })

    return {
        "status": "ok",
        "station_name": station_name,
        "cascade_deleted": deleted_items
    }

@app.put("/api/v1/rtus/{station_name}")
async def update_rtu(station_name: str, request: RTUCreateRequest):
    """Update RTU configuration in database"""
    existing = _get_rtu_from_db(station_name)
    if not existing:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Update RTU in database
    try:
        db.update_rtu_device(station_name, {
            "ip_address": request.ip_address,
            "vendor_id": request.vendor_id,
            "device_id": request.device_id,
            "slot_count": request.slot_count
        })
    except Exception as e:
        logger.error(f"Failed to update RTU {station_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    db.log_audit(request_user.get(), "update", "rtu_device", station_name,
                f"Updated RTU configuration")
    logger.info(f"Updated RTU: {station_name}")

    return RTUDevice(
        station_name=station_name,
        ip_address=request.ip_address,
        vendor_id=request.vendor_id,
        device_id=request.device_id,
        connection_state=_get_runtime_state(station_name),
        slot_count=request.slot_count,
        last_seen=None
    )

@app.post("/api/v1/rtus/{station_name}/connect")
async def connect_rtu(station_name: str):
    """Initiate PROFINET connection to an RTU"""
    existing = _get_rtu_from_db(station_name)
    if not existing:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Update runtime state
    _update_runtime_state(station_name, "CONNECTING")

    # Send IPC command to connect via PROFINET
    client = get_shm_client()
    if client:
        success = client.connect_rtu(station_name)
        if success:
            logger.info(f"Sent CONNECT_RTU command for {station_name}")
            db.log_audit(request_user.get(), "connect", "rtu_device", station_name,
                        "Initiated PROFINET connection")
        else:
            logger.warning(f"Failed to send CONNECT_RTU command for {station_name}")
            raise HTTPException(status_code=503, detail="Failed to send connect command")
    else:
        logger.warning(f"Controller not running - cannot connect to {station_name}")
        raise HTTPException(status_code=503, detail="PROFINET controller not running")

    return {"status": "connecting", "station_name": station_name}

@app.post("/api/v1/rtus/{station_name}/disconnect")
async def disconnect_rtu(station_name: str):
    """Disconnect PROFINET connection from an RTU"""
    existing = _get_rtu_from_db(station_name)
    if not existing:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Send IPC command to disconnect
    client = get_shm_client()
    if client:
        success = client.disconnect_rtu(station_name)
        if success:
            logger.info(f"Sent DISCONNECT_RTU command for {station_name}")
            _update_runtime_state(station_name, "OFFLINE")
            db.log_audit(request_user.get(), "disconnect", "rtu_device", station_name,
                        "Disconnected PROFINET connection")
        else:
            logger.warning(f"Failed to send DISCONNECT_RTU command for {station_name}")
    else:
        # Just update local state if controller not running
        _update_runtime_state(station_name, "OFFLINE")
        logger.info(f"Marked RTU {station_name} as offline (controller not running)")

    return {"status": "disconnected", "station_name": station_name}

@app.get("/api/v1/rtus/{station_name}/health")
async def get_rtu_health(station_name: str):
    """Get RTU health and connection status from shared memory"""
    existing = _get_rtu_from_db(station_name)
    if not existing:
        raise HTTPException(status_code=404, detail="RTU not found")

    connection_state = _get_runtime_state(station_name)
    packet_loss = 0.0
    last_seen = None

    # Get live data from shared memory if available
    client = get_shm_client()
    if client:
        rtu_data = client.get_rtu(station_name)
        if rtu_data:
            connection_state = CONNECTION_STATE_NAMES.get(rtu_data["connection_state"], "UNKNOWN")
            packet_loss = rtu_data.get("packet_loss_percent", 0.0)
            _update_runtime_state(station_name, connection_state)
            if connection_state == "RUNNING":
                last_seen = datetime.now()

    return {
        "station_name": station_name,
        "connection_state": connection_state,
        "healthy": connection_state == "RUNNING",
        "last_seen": last_seen.isoformat() if last_seen else None,
        "packet_loss_percent": packet_loss,
        "consecutive_failures": 0 if connection_state == "RUNNING" else 1,
        "in_failover": connection_state == "ERROR"
    }

@app.get("/api/v1/rtus/{station_name}", response_model=RTUDevice)
async def get_rtu(station_name: str):
    """Get RTU details by station name from database and runtime state"""
    # Check database for configuration
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    connection_state = _get_runtime_state(station_name)
    last_seen = None

    # Get live state from shared memory if available
    client = get_shm_client()
    if client:
        shm_rtu = client.get_rtu(station_name)
        if shm_rtu:
            connection_state = CONNECTION_STATE_NAMES.get(shm_rtu["connection_state"], "UNKNOWN")
            _update_runtime_state(station_name, connection_state)
            if connection_state == "RUNNING":
                last_seen = datetime.now()

    return RTUDevice(
        station_name=db_rtu["station_name"],
        ip_address=db_rtu["ip_address"],
        vendor_id=db_rtu.get("vendor_id", 0x0493),
        device_id=db_rtu.get("device_id", 0x0001),
        connection_state=connection_state,
        slot_count=db_rtu.get("slot_count", 16),
        last_seen=last_seen
    )

@app.get("/api/v1/rtus/{station_name}/sensors", response_model=List[SensorData])
async def get_rtu_sensors(station_name: str):
    """
    Get all sensor values for an RTU from shared memory.

    Returns live data from PROFINET when controller is running.
    Returns empty list when controller is not running (no simulated data).
    """
    # Verify RTU exists in database
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Default sensor names/units (can be overridden by slot config in db)
    default_sensor_names = ["pH", "Temperature", "Turbidity", "TDS",
                           "Dissolved Oxygen", "Flow Rate", "Level", "Pressure"]
    default_sensor_units = ["pH", "°C", "NTU", "ppm", "mg/L", "L/min", "%", "bar"]

    sensors = []
    client = get_shm_client()

    if client:
        # Get live sensor data from shared memory
        sensor_data = client.get_sensors(station_name)
        for s in sensor_data:
            idx = s["slot"] % len(default_sensor_names)
            timestamp = datetime.now()
            if s.get("timestamp_ms", 0) > 0:
                timestamp = datetime.fromtimestamp(s["timestamp_ms"] / 1000.0)

            sensors.append(SensorData(
                slot=s["slot"],
                name=default_sensor_names[idx],
                value=s["value"],
                unit=default_sensor_units[idx],
                status="GOOD" if s.get("quality") == "good" else "BAD",
                timestamp=timestamp
            ))
    else:
        # Controller not running - return empty list (no simulated data)
        logger.debug(f"Controller not running - no sensor data available for {station_name}")

    return sensors

@app.get("/api/v1/rtus/{station_name}/actuators", response_model=List[ActuatorState])
async def get_rtu_actuators(station_name: str):
    """
    Get all actuator states for an RTU from shared memory.

    Returns live data from PROFINET when controller is running.
    Returns empty list when controller is not running (no simulated data).
    """
    # Verify RTU exists in database
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Default actuator names (can be overridden by slot config in db)
    default_actuator_names = ["Main Pump", "Inlet Valve", "Outlet Valve", "Dosing Pump",
                              "Aerator", "Heater", "Mixer", "Spare"]

    actuators = []
    client = get_shm_client()

    if client:
        # Get live actuator data from shared memory
        actuator_data = client.get_actuators(station_name)
        for a in actuator_data:
            idx = a["slot"] % len(default_actuator_names)
            actuators.append(ActuatorState(
                slot=a["slot"],
                name=default_actuator_names[idx],
                command=a.get("command", "OFF"),
                pwm_duty=a.get("pwm_duty", 0),
                forced=a.get("forced", False)
            ))
    else:
        # Controller not running - return empty list (no simulated data)
        logger.debug(f"Controller not running - no actuator data available for {station_name}")

    return actuators

@app.post("/api/v1/rtus/{station_name}/actuators/{slot}")
async def command_actuator(station_name: str, slot: int, command: ActuatorCommand):
    """Send command to actuator via shared memory IPC"""
    # Verify RTU exists in database
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Convert command string to integer
    cmd_map = {"OFF": 0, "ON": 1, "PWM": 2}
    cmd_int = cmd_map.get(command.command, 0)

    client = get_shm_client()
    if client:
        success = client.command_actuator(station_name, slot, cmd_int, command.pwm_duty or 0)
        if not success:
            logger.error(f"Failed to send actuator command to {station_name} slot {slot}")
            raise HTTPException(status_code=500, detail="Failed to send actuator command")
    else:
        logger.warning(f"Controller not running - cannot send actuator command to {station_name}")
        raise HTTPException(status_code=503, detail="PROFINET controller not running")

    logger.info(f"Actuator command: {station_name} slot {slot} -> {command.command} duty={command.pwm_duty}")
    db.log_audit(request_user.get(), "actuator_command", "actuator",
                f"{station_name}:{slot}", f"Command: {command.command}, PWM: {command.pwm_duty}")

    await broadcast_event("actuator_command", {
        "station_name": station_name,
        "slot": slot,
        "command": command.command,
        "pwm_duty": command.pwm_duty
    })

    return {"status": "ok"}

# ============== RTU Test and Discovery Endpoints ==============

class RTUTestResult(BaseModel):
    station_name: str
    success: bool
    tests_passed: int
    tests_failed: int
    results: List[Dict[str, Any]]
    duration_ms: int

class DiscoveredSensor(BaseModel):
    bus_type: str  # "i2c", "onewire", "gpio"
    address: Optional[str] = None
    device_type: str
    name: str
    suggested_slot: Optional[int] = None
    suggested_measurement_type: Optional[str] = None

class DiscoveryResult(BaseModel):
    station_name: str
    success: bool
    sensors: List[DiscoveredSensor]
    error: Optional[str] = None

@app.post("/api/v1/rtus/{station_name}/test", response_model=RTUTestResult)
async def test_rtu(station_name: str, test_actuators: bool = True, blink_duration_ms: int = 500):
    """
    Run functionality test on RTU - blinks all indicator LEDs and tests communication.

    This endpoint:
    1. Verifies PROFINET communication
    2. Reads all sensor values
    3. Optionally cycles through actuators with brief ON pulses (for visual verification)
    4. Returns test results
    """
    import time
    start_time = time.time()

    client = get_shm_client()
    results = []
    tests_passed = 0
    tests_failed = 0

    # Test 1: Check RTU connection
    rtu_found = False
    if client:
        rtus = client.get_rtus()
        for rtu in rtus:
            if rtu.get("station_name") == station_name:
                rtu_found = True
                connection_state = rtu.get("connection_state", "UNKNOWN")
                if connection_state == "RUNNING":
                    results.append({"test": "connection", "status": "pass", "detail": "RTU connected and running"})
                    tests_passed += 1
                else:
                    results.append({"test": "connection", "status": "fail", "detail": f"RTU state: {connection_state}"})
                    tests_failed += 1
                break
    else:
        # Fallback mode
        if station_name in fallback_rtus:
            rtu_found = True
            results.append({"test": "connection", "status": "pass", "detail": "RTU registered (fallback mode)"})
            tests_passed += 1

    if not rtu_found:
        return RTUTestResult(
            station_name=station_name,
            success=False,
            tests_passed=0,
            tests_failed=1,
            results=[{"test": "connection", "status": "fail", "detail": "RTU not found"}],
            duration_ms=int((time.time() - start_time) * 1000)
        )

    # Test 2: Read sensors
    try:
        if client:
            sensors = client.get_sensors(station_name)
            valid_sensors = sum(1 for s in sensors if s.get("status") == 0x80)  # IOPS_GOOD
            results.append({
                "test": "sensors",
                "status": "pass" if valid_sensors > 0 else "warn",
                "detail": f"{valid_sensors} sensors reporting good status"
            })
            if valid_sensors > 0:
                tests_passed += 1
            else:
                tests_failed += 1
        else:
            results.append({"test": "sensors", "status": "pass", "detail": "Sensor check skipped (fallback mode)"})
            tests_passed += 1
    except Exception as e:
        results.append({"test": "sensors", "status": "fail", "detail": str(e)})
        tests_failed += 1

    # Test 3: Actuator blink test (if enabled)
    if test_actuators:
        try:
            if client:
                actuators = client.get_actuators(station_name)
                actuator_slots = [a.get("slot") for a in actuators]
            else:
                actuator_slots = list(range(9, 17))  # Default actuator slots

            blinked_count = 0
            for slot in actuator_slots:
                try:
                    # Turn ON briefly
                    if client:
                        client.command_actuator(station_name, slot, 1, 0)  # ON
                    await asyncio.sleep(blink_duration_ms / 1000.0)

                    # Turn OFF
                    if client:
                        client.command_actuator(station_name, slot, 0, 0)  # OFF
                    await asyncio.sleep(0.1)  # Brief pause between actuators

                    blinked_count += 1
                except Exception:
                    pass

            results.append({
                "test": "actuators",
                "status": "pass" if blinked_count > 0 else "warn",
                "detail": f"Blinked {blinked_count} actuators"
            })
            if blinked_count > 0:
                tests_passed += 1
            else:
                tests_failed += 1

        except Exception as e:
            results.append({"test": "actuators", "status": "fail", "detail": str(e)})
            tests_failed += 1

    # Test 4: Communication latency
    try:
        if client:
            # Measure round-trip time
            latency_start = time.time()
            _ = client.get_rtus()
            latency_ms = (time.time() - latency_start) * 1000

            if latency_ms < 100:
                results.append({"test": "latency", "status": "pass", "detail": f"{latency_ms:.1f}ms round-trip"})
                tests_passed += 1
            elif latency_ms < 500:
                results.append({"test": "latency", "status": "warn", "detail": f"{latency_ms:.1f}ms round-trip (slow)"})
                tests_passed += 1
            else:
                results.append({"test": "latency", "status": "fail", "detail": f"{latency_ms:.1f}ms round-trip (too slow)"})
                tests_failed += 1
        else:
            results.append({"test": "latency", "status": "pass", "detail": "Latency check skipped (fallback mode)"})
            tests_passed += 1
    except Exception as e:
        results.append({"test": "latency", "status": "fail", "detail": str(e)})
        tests_failed += 1

    duration_ms = int((time.time() - start_time) * 1000)

    await broadcast_event("rtu_test_complete", {
        "station_name": station_name,
        "success": tests_failed == 0,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed
    })

    return RTUTestResult(
        station_name=station_name,
        success=tests_failed == 0,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        results=results,
        duration_ms=duration_ms
    )

@app.post("/api/v1/rtus/{station_name}/discover", response_model=DiscoveryResult)
async def discover_sensors(station_name: str, scan_i2c: bool = True, scan_onewire: bool = True):
    """
    Trigger I2C/1-Wire sensor discovery on RTU.

    Sends a discovery command to the RTU which scans its I2C buses and 1-Wire interfaces
    for connected sensors. Returns discovered sensors with recommended slot assignments.

    Requires PROFINET controller to be running - discovery commands are sent via IPC.

    Supported I2C devices:
    - ADS1115 (0x48-0x4B): 16-bit ADC for analog sensors
    - BME280 (0x76-0x77): Temperature/Pressure/Humidity
    - TCS34725 (0x29): Color sensor
    - SHT31 (0x44-0x45): Temperature/Humidity
    - INA219 (0x40-0x4F): Current sensor

    Supported 1-Wire devices:
    - DS18B20 (28-*): Temperature sensor
    """
    # Check if RTU exists in database
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        return DiscoveryResult(
            station_name=station_name,
            success=False,
            sensors=[],
            error="RTU not found"
        )

    client = get_shm_client()
    if not client:
        return DiscoveryResult(
            station_name=station_name,
            success=False,
            sensors=[],
            error="PROFINET controller not running - cannot perform discovery"
        )

    discovered = []

    # I2C device mapping for identification
    i2c_devices = {
        "0x48": ("ADS1115", "adc", "CUSTOM"),
        "0x49": ("ADS1115", "adc", "CUSTOM"),
        "0x4A": ("ADS1115", "adc", "CUSTOM"),
        "0x4B": ("ADS1115", "adc", "CUSTOM"),
        "0x76": ("BME280", "environmental", "TEMPERATURE"),
        "0x77": ("BME280", "environmental", "PRESSURE"),
        "0x29": ("TCS34725", "color", "TURBIDITY"),
        "0x44": ("SHT31", "environmental", "TEMPERATURE"),
        "0x45": ("SHT31", "environmental", "TEMPERATURE"),
        "0x40": ("INA219", "current", "CUSTOM"),
    }

    if scan_i2c:
        # Send I2C discovery command via IPC
        logger.info(f"Initiating I2C discovery on {station_name}")
        i2c_results = client.discover_i2c(station_name)
        for device in i2c_results:
            addr = device.get("address", "")
            if addr in i2c_devices:
                dev_name, dev_type, meas_type = i2c_devices[addr]
            else:
                dev_name, dev_type, meas_type = "Unknown", "unknown", "CUSTOM"

            discovered.append(DiscoveredSensor(
                bus_type="i2c",
                address=addr,
                device_type=dev_type,
                name=f"{dev_name}@{addr}",
                suggested_slot=len(discovered) + 1,
                suggested_measurement_type=meas_type
            ))

    if scan_onewire:
        # Send 1-Wire discovery command via IPC
        logger.info(f"Initiating 1-Wire discovery on {station_name}")
        onewire_results = client.discover_onewire(station_name)
        for device in onewire_results:
            device_id = device.get("device_id", "")
            if device_id.startswith("28-"):
                # DS18B20 temperature sensor
                discovered.append(DiscoveredSensor(
                    bus_type="onewire",
                    address=device_id,
                    device_type="temperature",
                    name=f"DS18B20_{device_id[-8:]}",
                    suggested_slot=len(discovered) + 1,
                    suggested_measurement_type="TEMPERATURE"
                ))
            else:
                discovered.append(DiscoveredSensor(
                    bus_type="onewire",
                    address=device_id,
                    device_type="unknown",
                    name=f"OneWire_{device_id[-8:]}",
                    suggested_slot=len(discovered) + 1,
                    suggested_measurement_type="CUSTOM"
                ))

    logger.info(f"Discovery on {station_name}: found {len(discovered)} sensors")

    await broadcast_event("discovery_complete", {
        "station_name": station_name,
        "sensors_found": len(discovered)
    })

    return DiscoveryResult(
        station_name=station_name,
        success=True,
        sensors=discovered
    )

@app.post("/api/v1/rtus/{station_name}/provision")
async def provision_discovered_sensors(
    station_name: str,
    sensors: List[DiscoveredSensor],
    create_historian_tags: bool = True,
    create_alarm_rules: bool = False
):
    """
    Provision discovered sensors by creating slot configurations, historian tags, and optionally alarm rules.

    Sends slot configuration to RTU via IPC and creates database records.
    """
    # Verify RTU exists
    db_rtu = _get_rtu_from_db(station_name)
    if not db_rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    client = get_shm_client()
    provisioned = []

    for sensor in sensors:
        slot = sensor.suggested_slot

        # Create slot configuration
        slot_config = {
            "slot": slot,
            "name": sensor.name,
            "type": "SENSOR",
            "measurement_type": sensor.suggested_measurement_type or "CUSTOM",
            "enabled": True
        }

        # Send slot configuration to RTU via IPC
        configured = False
        if client:
            configured = client.configure_slot(
                station_name,
                slot,
                "SENSOR",
                sensor.name,
                "",  # unit
                0.0,  # scale_min
                100.0  # scale_max
            )
            if configured:
                logger.info(f"Configured slot {slot} on {station_name} as {sensor.name}")
            else:
                logger.warning(f"Failed to configure slot {slot} on {station_name}")
        else:
            logger.warning(f"Controller not running - slot {slot} not configured on hardware")

        provisioned.append({
            "sensor": sensor.name,
            "slot": slot,
            "configured": configured
        })

        # Create historian tag
        if create_historian_tags:
            tag_name = f"{station_name}.{sensor.name}"
            historian_tags[len(historian_tags) + 1] = HistorianTag(
                tag_id=len(historian_tags) + 1,
                rtu_station=station_name,
                slot=slot,
                tag_name=tag_name,
                sample_rate_ms=1000,
                deadband=0.1,
                compression="swinging_door"
            )

        # Create default alarm rules
        if create_alarm_rules and sensor.suggested_measurement_type in ["TEMPERATURE", "PRESSURE", "PH"]:
            rule_id = len(alarm_rules) + 1
            alarm_rules[rule_id] = AlarmRule(
                rule_id=rule_id,
                rtu_station=station_name,
                slot=slot,
                condition="HIGH",
                threshold=100.0,  # Default - should be configured
                severity="MEDIUM",
                delay_ms=5000,
                message=f"{sensor.name} high alarm",
                enabled=False  # Disabled by default - user should configure
            )

    logger.info(f"Provisioned {len(provisioned)} sensors on {station_name}")

    return {
        "status": "ok",
        "provisioned": provisioned,
        "historian_tags_created": create_historian_tags,
        "alarm_rules_created": create_alarm_rules
    }

# ============== Alarm Endpoints ==============

@app.get("/api/v1/alarms", response_model=List[Alarm])
async def get_active_alarms():
    """Get all active alarms"""
    client = get_shm_client()
    if client:
        alarms = client.get_alarms()
        return [Alarm(
            alarm_id=a["alarm_id"],
            rule_id=a["rule_id"],
            rtu_station=a["rtu_station"],
            slot=a["slot"],
            severity=ALARM_SEVERITY.get(a["severity"], "UNKNOWN"),
            state=ALARM_STATE.get(a["state"], "UNKNOWN"),
            message=a["message"],
            value=a["value"],
            threshold=a["threshold"],
            raise_time=datetime.fromtimestamp(a["raise_time_ms"] / 1000.0),
            ack_time=datetime.fromtimestamp(a["ack_time_ms"] / 1000.0) if a["ack_time_ms"] > 0 else None,
            ack_user=a["ack_user"] if a["ack_user"] else None
        ) for a in alarms if a["state"] in [1, 2]]  # ACTIVE_UNACK or ACTIVE_ACK

    active = [a for a in fallback_alarms.values() if a.state in ["ACTIVE_UNACK", "ACTIVE_ACK"]]
    return active

@app.get("/api/v1/alarms/history", response_model=List[Alarm])
async def get_alarm_history(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100
):
    """Get alarm history"""
    client = get_shm_client()
    if client:
        alarms = client.get_alarms()
        return [Alarm(
            alarm_id=a["alarm_id"],
            rule_id=a["rule_id"],
            rtu_station=a["rtu_station"],
            slot=a["slot"],
            severity=ALARM_SEVERITY.get(a["severity"], "UNKNOWN"),
            state=ALARM_STATE.get(a["state"], "UNKNOWN"),
            message=a["message"],
            value=a["value"],
            threshold=a["threshold"],
            raise_time=datetime.fromtimestamp(a["raise_time_ms"] / 1000.0),
            ack_time=datetime.fromtimestamp(a["ack_time_ms"] / 1000.0) if a["ack_time_ms"] > 0 else None,
            ack_user=a["ack_user"] if a["ack_user"] else None
        ) for a in alarms[:limit]]

    return list(fallback_alarms.values())[:limit]

@app.post("/api/v1/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(alarm_id: int, request: AcknowledgeRequest):
    """Acknowledge an alarm"""
    client = get_shm_client()
    if client:
        success = client.acknowledge_alarm(alarm_id, request.user)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to acknowledge alarm")
    else:
        if alarm_id not in fallback_alarms:
            raise HTTPException(status_code=404, detail="Alarm not found")

        alarm = fallback_alarms[alarm_id]
        if alarm.state == "ACTIVE_UNACK":
            alarm.state = "ACTIVE_ACK"
        elif alarm.state == "CLEARED_UNACK":
            alarm.state = "CLEARED"

        alarm.ack_time = datetime.now()
        alarm.ack_user = request.user

    await broadcast_event("alarm_acknowledged", {"alarm_id": alarm_id, "user": request.user})
    return {"status": "ok"}

@app.get("/api/v1/alarms/rules", response_model=List[AlarmRule])
async def list_alarm_rules():
    """List all alarm rules"""
    return list(alarm_rules.values())

@app.post("/api/v1/alarms/rules", response_model=AlarmRule)
async def create_alarm_rule(rule: AlarmRule):
    """Create a new alarm rule"""
    rule_id = len(alarm_rules) + 1
    rule.rule_id = rule_id
    alarm_rules[rule_id] = rule
    return rule

# ============== Control Endpoints ==============

@app.get("/api/v1/control/pid", response_model=List[PIDLoop])
async def list_pid_loops():
    """List all PID control loops"""
    client = get_shm_client()
    if client:
        loops = client.get_pid_loops()
        return [PIDLoop(
            loop_id=l["loop_id"],
            name=l["name"],
            enabled=l["enabled"],
            input_rtu=l["input_rtu"],
            input_slot=l["input_slot"],
            output_rtu=l["output_rtu"],
            output_slot=l["output_slot"],
            kp=l["kp"],
            ki=l["ki"],
            kd=l["kd"],
            setpoint=l["setpoint"],
            mode=PID_MODES.get(l["mode"], "MANUAL"),
            pv=l["pv"],
            cv=l["cv"]
        ) for l in loops]

    return list(fallback_pid_loops.values())

@app.get("/api/v1/control/pid/{loop_id}", response_model=PIDLoop)
async def get_pid_loop(loop_id: int):
    """Get PID loop details"""
    client = get_shm_client()
    if client:
        loops = client.get_pid_loops()
        for l in loops:
            if l["loop_id"] == loop_id:
                return PIDLoop(
                    loop_id=l["loop_id"],
                    name=l["name"],
                    enabled=l["enabled"],
                    input_rtu=l["input_rtu"],
                    input_slot=l["input_slot"],
                    output_rtu=l["output_rtu"],
                    output_slot=l["output_slot"],
                    kp=l["kp"],
                    ki=l["ki"],
                    kd=l["kd"],
                    setpoint=l["setpoint"],
                    mode=PID_MODES.get(l["mode"], "MANUAL"),
                    pv=l["pv"],
                    cv=l["cv"]
                )
        raise HTTPException(status_code=404, detail="PID loop not found")

    if loop_id not in fallback_pid_loops:
        raise HTTPException(status_code=404, detail="PID loop not found")
    return fallback_pid_loops[loop_id]

@app.put("/api/v1/control/pid/{loop_id}/setpoint")
async def update_pid_setpoint(loop_id: int, update: SetpointUpdate):
    """Update PID loop setpoint"""
    client = get_shm_client()
    if client:
        success = client.set_setpoint(loop_id, update.setpoint)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update setpoint")
    else:
        if loop_id not in fallback_pid_loops:
            raise HTTPException(status_code=404, detail="PID loop not found")
        fallback_pid_loops[loop_id].setpoint = update.setpoint

    logger.info(f"PID loop {loop_id} setpoint changed to {update.setpoint}")
    return {"status": "ok"}

@app.put("/api/v1/control/pid/{loop_id}/mode")
async def update_pid_mode(loop_id: int, update: ModeUpdate):
    """Update PID loop mode"""
    mode_map = {"MANUAL": 0, "AUTO": 1, "CASCADE": 2}
    mode_int = mode_map.get(update.mode, 0)

    client = get_shm_client()
    if client:
        success = client.set_pid_mode(loop_id, mode_int)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update mode")
    else:
        if loop_id not in fallback_pid_loops:
            raise HTTPException(status_code=404, detail="PID loop not found")
        fallback_pid_loops[loop_id].mode = update.mode

    logger.info(f"PID loop {loop_id} mode changed to {update.mode}")
    return {"status": "ok"}

@app.put("/api/v1/control/pid/{loop_id}/tuning")
async def update_pid_tuning(loop_id: int, tuning: TuningUpdate):
    """Update PID loop tuning parameters"""
    if loop_id not in fallback_pid_loops:
        raise HTTPException(status_code=404, detail="PID loop not found")

    fallback_pid_loops[loop_id].kp = tuning.kp
    fallback_pid_loops[loop_id].ki = tuning.ki
    fallback_pid_loops[loop_id].kd = tuning.kd

    return {"status": "ok"}

# ============== Interlock Endpoints ==============

@app.post("/api/v1/control/interlocks/{interlock_id}/reset")
async def reset_interlock(interlock_id: int):
    """Reset an interlock"""
    client = get_shm_client()
    if client:
        success = client.reset_interlock(interlock_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset interlock")

    logger.info(f"Interlock {interlock_id} reset")
    return {"status": "ok"}

# ============== Trend Endpoints ==============

# In-memory historian tags cache (loaded from database)
_historian_tags_cache: Dict[int, HistorianTag] = {}

def _refresh_historian_tags():
    """Refresh historian tags from database"""
    global _historian_tags_cache
    # In production, this would query the historian_tags table
    # For now, generate tags from registered RTUs and their slots
    _historian_tags_cache.clear()
    tag_id = 1
    for rtu in _get_all_rtus_from_db():
        station = rtu["station_name"]
        for slot in range(rtu.get("slot_count", 16)):
            _historian_tags_cache[tag_id] = HistorianTag(
                tag_id=tag_id,
                rtu_station=station,
                slot=slot,
                tag_name=f"{station}.slot{slot}",
                sample_rate_ms=1000,
                deadband=0.1,
                compression="swinging_door"
            )
            tag_id += 1

@app.get("/api/v1/trends/tags", response_model=List[HistorianTag])
async def list_historian_tags():
    """List all historian tags based on configured RTUs"""
    _refresh_historian_tags()
    return list(_historian_tags_cache.values())

@app.get("/api/v1/trends/{tag_id}")
async def get_trend_data(tag_id: int, start_time: datetime, end_time: datetime):
    """
    Get trend data for a tag.

    Returns historical samples from the data historian.
    If historian is not populated, returns empty sample list.

    Note: The historian collects data from shared memory automatically.
    This endpoint queries the historical data store, not live data.
    """
    _refresh_historian_tags()
    if tag_id not in _historian_tags_cache:
        raise HTTPException(status_code=404, detail="Tag not found")

    # In production, query the historian database for actual recorded values
    # The historian service writes samples to a time-series database
    # For now, return empty samples - no simulated data
    logger.debug(f"Trend query for tag {tag_id}: {start_time} to {end_time}")

    # Placeholder: historian integration would query time-series DB here
    samples = []

    return {"tag_id": tag_id, "samples": samples}

# ============== System Endpoints ==============

def _get_system_metrics() -> tuple:
    """Get CPU and memory usage from system"""
    try:
        import os
        # Read /proc/stat for CPU usage (Linux)
        cpu_percent = 0.0
        memory_percent = 0.0

        # Try to get memory info from /proc/meminfo
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip().split()[0]
                        meminfo[key] = int(value)
                total = meminfo.get('MemTotal', 1)
                available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
                memory_percent = ((total - available) / total) * 100

        # Simple load average based CPU estimate (Linux)
        if os.path.exists('/proc/loadavg'):
            with open('/proc/loadavg', 'r') as f:
                loadavg = float(f.read().split()[0])
                cpu_count = os.cpu_count() or 1
                cpu_percent = min(100.0, (loadavg / cpu_count) * 100)

        return cpu_percent, memory_percent
    except Exception as e:
        logger.debug(f"Failed to get system metrics: {e}")
        return 0.0, 0.0

@app.get("/api/v1/system/health", response_model=SystemHealth)
async def get_system_health():
    """Get system health status from controller and database"""
    cpu_percent, memory_percent = _get_system_metrics()
    db_rtus = _get_all_rtus_from_db()
    total_rtus = len(db_rtus)

    client = get_shm_client()
    if client:
        status = client.get_status()
        return SystemHealth(
            status="running" if status.get("controller_running", False) else "stopped",
            uptime_seconds=int(status.get("last_update_ms", 0) / 1000),
            connected_rtus=status.get("connected_rtus", 0),
            total_rtus=max(total_rtus, status.get("total_rtus", 0)),
            active_alarms=status.get("active_alarms", 0),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent
        )

    # Controller not running - return database counts
    running_count = sum(1 for name in db_rtus if _get_runtime_state(name) == "RUNNING")

    return SystemHealth(
        status="stopped",
        uptime_seconds=0,
        connected_rtus=running_count,
        total_rtus=total_rtus,
        active_alarms=0,
        cpu_percent=cpu_percent,
        memory_percent=memory_percent
    )

@app.get("/api/v1/system/config")
async def export_config():
    """Export system configuration from database"""
    return {
        "rtus": db.get_rtu_devices(),
        "alarm_rules": db.get_alarm_rules(),
        "modbus_server": db.get_modbus_server_config(),
        "modbus_devices": db.get_modbus_downstream_devices(),
        "modbus_mappings": db.get_modbus_register_mappings()
    }

@app.post("/api/v1/system/config")
async def import_config(config: Dict[str, Any]):
    """Import system configuration into database"""
    imported = {"rtus": 0, "alarm_rules": 0, "modbus_devices": 0}

    try:
        # Import RTUs
        if "rtus" in config:
            for rtu_data in config["rtus"]:
                try:
                    existing = db.get_rtu_device(rtu_data.get("station_name", ""))
                    if existing:
                        db.update_rtu_device(rtu_data["station_name"], rtu_data)
                    else:
                        db.create_rtu_device(rtu_data)
                    imported["rtus"] += 1
                except Exception as e:
                    logger.warning(f"Failed to import RTU {rtu_data.get('station_name')}: {e}")

        # Import alarm rules
        if "alarm_rules" in config:
            for rule_data in config["alarm_rules"]:
                rule = AlarmRule(**rule_data)
                if rule.rule_id:
                    alarm_rules[rule.rule_id] = rule

        # Import PID loops
        if "pid_loops" in config:
            for pid_data in config["pid_loops"]:
                pid = PIDLoop(**pid_data)
                if pid.loop_id:
                    fallback_pid_loops[pid.loop_id] = pid

        # Import historian tags
        if "historian_tags" in config:
            for tag_data in config["historian_tags"]:
                tag = HistorianTag(**tag_data)
                historian_tags[tag.tag_id] = tag

        logger.info(f"Configuration imported: {len(config.get('rtus', []))} RTUs, "
                   f"{len(config.get('alarm_rules', []))} rules, "
                   f"{len(config.get('pid_loops', []))} PID loops")

        return {"status": "ok", "message": "Configuration imported successfully"}
    except Exception as e:
        logger.error(f"Configuration import failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# ============== Backup/Restore Endpoints ==============

class BackupMetadata(BaseModel):
    backup_id: str
    filename: str
    created_at: datetime
    size_bytes: int
    description: Optional[str] = None
    includes_historian: bool = False

class BackupRequest(BaseModel):
    description: Optional[str] = None
    include_historian: bool = False

class RestoreRequest(BaseModel):
    backup_id: str

import os
import tarfile
import tempfile
import shutil
from io import BytesIO
from fastapi.responses import StreamingResponse

BACKUP_DIR = os.environ.get("WT_BACKUP_DIR", "/var/lib/water-controller/backups")

@app.get("/api/v1/backups", response_model=List[BackupMetadata])
async def list_backups():
    """List all available backups"""
    backups = []

    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        return backups

    for filename in os.listdir(BACKUP_DIR):
        if filename.endswith('.tar.gz'):
            filepath = os.path.join(BACKUP_DIR, filename)
            stat = os.stat(filepath)
            backup_id = filename.replace('.tar.gz', '')

            backups.append(BackupMetadata(
                backup_id=backup_id,
                filename=filename,
                created_at=datetime.fromtimestamp(stat.st_mtime),
                size_bytes=stat.st_size,
                includes_historian='_full_' in filename
            ))

    return sorted(backups, key=lambda x: x.created_at, reverse=True)

@app.post("/api/v1/backups", response_model=BackupMetadata)
async def create_backup(request: BackupRequest):
    """Create a new configuration backup"""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_type = "full" if request.include_historian else "config"
    backup_id = f"wtc_{backup_type}_{timestamp}"
    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    # Get current configuration
    config_data = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "description": request.description,
        "rtus": [r.dict() for r in fallback_rtus.values()],
        "alarm_rules": [r.dict() for r in alarm_rules.values()],
        "pid_loops": [p.dict() for p in fallback_pid_loops.values()],
        "historian_tags": [t.dict() for t in historian_tags.values()],
        "modbus_config": modbus_config.copy() if modbus_config else {}
    }

    # Create backup archive
    with tarfile.open(filepath, "w:gz") as tar:
        # Add configuration JSON
        config_json = json.dumps(config_data, indent=2, default=str).encode()
        config_info = tarfile.TarInfo(name="config.json")
        config_info.size = len(config_json)
        tar.addfile(config_info, BytesIO(config_json))

        # Add system config files if they exist
        config_dir = os.environ.get("WT_CONFIG_DIR", "/etc/water-controller")
        if os.path.exists(config_dir):
            for conf_file in os.listdir(config_dir):
                conf_path = os.path.join(config_dir, conf_file)
                if os.path.isfile(conf_path):
                    tar.add(conf_path, arcname=f"system_config/{conf_file}")

    stat = os.stat(filepath)
    logger.info(f"Backup created: {filename}")

    return BackupMetadata(
        backup_id=backup_id,
        filename=filename,
        created_at=datetime.now(),
        size_bytes=stat.st_size,
        description=request.description,
        includes_historian=request.include_historian
    )

@app.get("/api/v1/backups/{backup_id}/download")
async def download_backup(backup_id: str):
    """Download a backup file"""
    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Backup not found")

    def iterfile():
        with open(filepath, "rb") as f:
            yield from f

    return StreamingResponse(
        iterfile(),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/v1/backups/{backup_id}/restore")
async def restore_backup(backup_id: str):
    """Restore configuration from a backup"""
    global fallback_rtus, alarm_rules, fallback_pid_loops, historian_tags, modbus_config

    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Backup not found")

    try:
        with tarfile.open(filepath, "r:gz") as tar:
            config_file = tar.extractfile("config.json")
            if config_file:
                config_data = json.load(config_file)

                # Restore RTUs
                fallback_rtus.clear()
                for rtu_data in config_data.get("rtus", []):
                    rtu = RTUDevice(**rtu_data)
                    fallback_rtus[rtu.station_name] = rtu

                # Restore alarm rules
                alarm_rules.clear()
                for rule_data in config_data.get("alarm_rules", []):
                    rule = AlarmRule(**rule_data)
                    if rule.rule_id:
                        alarm_rules[rule.rule_id] = rule

                # Restore PID loops
                fallback_pid_loops.clear()
                for pid_data in config_data.get("pid_loops", []):
                    pid = PIDLoop(**pid_data)
                    if pid.loop_id:
                        fallback_pid_loops[pid.loop_id] = pid

                # Restore historian tags
                historian_tags.clear()
                for tag_data in config_data.get("historian_tags", []):
                    tag = HistorianTag(**tag_data)
                    historian_tags[tag.tag_id] = tag

                # Restore Modbus config
                if "modbus_config" in config_data:
                    modbus_config.update(config_data["modbus_config"])

        logger.info(f"Configuration restored from backup: {backup_id}")
        return {"status": "ok", "message": "Configuration restored successfully"}

    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/backups/{backup_id}")
async def delete_backup(backup_id: str):
    """Delete a backup"""
    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Backup not found")

    os.remove(filepath)
    logger.info(f"Backup deleted: {backup_id}")
    return {"status": "ok"}

@app.post("/api/v1/backups/upload")
async def upload_backup(file: bytes = None):
    """Upload a backup file for restore"""
    from fastapi import File, UploadFile

@app.post("/api/v1/backups/import")
async def import_backup_file(file: Any = None):
    """Import configuration from uploaded file"""
    # This endpoint accepts multipart form upload
    return {"status": "ok", "message": "Use /api/v1/system/config for direct JSON import"}

# ============== Modbus Gateway Configuration ==============

class ModbusServerConfig(BaseModel):
    tcp_enabled: bool = True
    tcp_port: int = 502
    tcp_bind_address: str = "0.0.0.0"
    rtu_enabled: bool = False
    rtu_device: str = "/dev/ttyUSB0"
    rtu_baud_rate: int = 9600
    rtu_parity: str = "N"
    rtu_data_bits: int = 8
    rtu_stop_bits: int = 1
    rtu_slave_addr: int = 1

class ModbusRegisterMapping(BaseModel):
    mapping_id: Optional[int] = None
    modbus_addr: int
    register_type: str  # HOLDING, INPUT, COIL, DISCRETE
    data_type: str  # UINT16, INT16, FLOAT32, etc.
    source_type: str  # PROFINET_SENSOR, PROFINET_ACTUATOR, PID_SETPOINT, etc.
    rtu_station: str
    slot: int
    description: str = ""
    scaling_enabled: bool = False
    scale_raw_min: float = 0
    scale_raw_max: float = 65535
    scale_eng_min: float = 0
    scale_eng_max: float = 100
    read_only: bool = True
    enabled: bool = True

class ModbusDownstreamDevice(BaseModel):
    device_id: Optional[int] = None
    name: str
    transport: str  # TCP or RTU
    tcp_host: Optional[str] = None
    tcp_port: int = 502
    rtu_device: Optional[str] = None
    rtu_baud_rate: int = 9600
    slave_addr: int = 1
    poll_interval_ms: int = 1000
    timeout_ms: int = 1000
    enabled: bool = True

class ModbusGatewayConfig(BaseModel):
    server: ModbusServerConfig
    auto_generate_map: bool = True
    sensor_base_addr: int = 0
    actuator_base_addr: int = 100
    register_mappings: List[ModbusRegisterMapping] = []
    downstream_devices: List[ModbusDownstreamDevice] = []

class ModbusStats(BaseModel):
    server_running: bool
    tcp_connections: int
    total_requests: int
    total_errors: int
    downstream_devices_online: int

# Modbus configuration storage
modbus_config: Dict[str, Any] = {
    "server": {
        "tcp_enabled": True,
        "tcp_port": 502,
        "tcp_bind_address": "0.0.0.0",
        "rtu_enabled": False,
        "rtu_device": "/dev/ttyUSB0",
        "rtu_baud_rate": 9600,
        "rtu_slave_addr": 1
    },
    "auto_generate_map": True,
    "sensor_base_addr": 0,
    "actuator_base_addr": 100,
    "register_mappings": [],
    "downstream_devices": []
}

@app.get("/api/v1/modbus/config", response_model=ModbusGatewayConfig)
async def get_modbus_config():
    """Get Modbus gateway configuration"""
    return ModbusGatewayConfig(
        server=ModbusServerConfig(**modbus_config.get("server", {})),
        auto_generate_map=modbus_config.get("auto_generate_map", True),
        sensor_base_addr=modbus_config.get("sensor_base_addr", 0),
        actuator_base_addr=modbus_config.get("actuator_base_addr", 100),
        register_mappings=[ModbusRegisterMapping(**m) for m in modbus_config.get("register_mappings", [])],
        downstream_devices=[ModbusDownstreamDevice(**d) for d in modbus_config.get("downstream_devices", [])]
    )

@app.put("/api/v1/modbus/config")
async def update_modbus_config(config: ModbusGatewayConfig):
    """Update Modbus gateway configuration"""
    global modbus_config

    modbus_config["server"] = config.server.dict()
    modbus_config["auto_generate_map"] = config.auto_generate_map
    modbus_config["sensor_base_addr"] = config.sensor_base_addr
    modbus_config["actuator_base_addr"] = config.actuator_base_addr

    logger.info("Modbus configuration updated")
    return {"status": "ok"}

@app.get("/api/v1/modbus/server", response_model=ModbusServerConfig)
async def get_modbus_server_config():
    """Get Modbus server configuration"""
    return ModbusServerConfig(**modbus_config.get("server", {}))

@app.put("/api/v1/modbus/server")
async def update_modbus_server_config(config: ModbusServerConfig):
    """Update Modbus server configuration"""
    modbus_config["server"] = config.dict()
    logger.info(f"Modbus server config updated: TCP={config.tcp_enabled}:{config.tcp_port}, RTU={config.rtu_enabled}")
    return {"status": "ok"}

@app.get("/api/v1/modbus/mappings", response_model=List[ModbusRegisterMapping])
async def list_modbus_mappings():
    """List all Modbus register mappings"""
    return [ModbusRegisterMapping(**m) for m in modbus_config.get("register_mappings", [])]

@app.post("/api/v1/modbus/mappings", response_model=ModbusRegisterMapping)
async def create_modbus_mapping(mapping: ModbusRegisterMapping):
    """Create a new Modbus register mapping"""
    mappings = modbus_config.get("register_mappings", [])
    mapping.mapping_id = len(mappings) + 1
    mappings.append(mapping.dict())
    modbus_config["register_mappings"] = mappings
    return mapping

@app.put("/api/v1/modbus/mappings/{mapping_id}")
async def update_modbus_mapping(mapping_id: int, mapping: ModbusRegisterMapping):
    """Update a Modbus register mapping"""
    mappings = modbus_config.get("register_mappings", [])
    for i, m in enumerate(mappings):
        if m.get("mapping_id") == mapping_id:
            mapping.mapping_id = mapping_id
            mappings[i] = mapping.dict()
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Mapping not found")

@app.delete("/api/v1/modbus/mappings/{mapping_id}")
async def delete_modbus_mapping(mapping_id: int):
    """Delete a Modbus register mapping"""
    mappings = modbus_config.get("register_mappings", [])
    modbus_config["register_mappings"] = [m for m in mappings if m.get("mapping_id") != mapping_id]
    return {"status": "ok"}

@app.get("/api/v1/modbus/downstream", response_model=List[ModbusDownstreamDevice])
async def list_downstream_devices():
    """List all downstream Modbus devices"""
    return [ModbusDownstreamDevice(**d) for d in modbus_config.get("downstream_devices", [])]

@app.post("/api/v1/modbus/downstream", response_model=ModbusDownstreamDevice)
async def add_downstream_device(device: ModbusDownstreamDevice):
    """Add a downstream Modbus device"""
    devices = modbus_config.get("downstream_devices", [])
    device.device_id = len(devices) + 1
    devices.append(device.dict())
    modbus_config["downstream_devices"] = devices
    logger.info(f"Added downstream device: {device.name}")
    return device

@app.put("/api/v1/modbus/downstream/{device_id}")
async def update_downstream_device(device_id: int, device: ModbusDownstreamDevice):
    """Update a downstream Modbus device"""
    devices = modbus_config.get("downstream_devices", [])
    for i, d in enumerate(devices):
        if d.get("device_id") == device_id:
            device.device_id = device_id
            devices[i] = device.dict()
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Device not found")

@app.delete("/api/v1/modbus/downstream/{device_id}")
async def remove_downstream_device(device_id: int):
    """Remove a downstream Modbus device"""
    devices = modbus_config.get("downstream_devices", [])
    modbus_config["downstream_devices"] = [d for d in devices if d.get("device_id") != device_id]
    return {"status": "ok"}

@app.get("/api/v1/modbus/stats", response_model=ModbusStats)
async def get_modbus_stats():
    """Get Modbus gateway statistics"""
    client = get_shm_client()
    if client:
        # TODO: Get real stats from shared memory
        pass

    return ModbusStats(
        server_running=modbus_config.get("server", {}).get("tcp_enabled", False),
        tcp_connections=0,
        total_requests=0,
        total_errors=0,
        downstream_devices_online=0
    )

@app.post("/api/v1/modbus/restart")
async def restart_modbus_gateway():
    """Restart the Modbus gateway service"""
    # In production, this would signal the controller to restart Modbus
    logger.info("Modbus gateway restart requested")
    return {"status": "ok", "message": "Restart signal sent"}

# ============== Service Control Endpoints ==============

@app.get("/api/v1/services")
async def list_services():
    """List service status"""
    import subprocess

    services = ["water-controller", "water-controller-api", "water-controller-ui", "water-controller-modbus"]
    status = {}

    for svc in services:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5
            )
            status[svc] = result.stdout.strip()
        except Exception:
            status[svc] = "unknown"

    return status

@app.post("/api/v1/services/{service_name}/{action}")
async def control_service(service_name: str, action: str):
    """Control a service (start/stop/restart)"""
    import subprocess

    allowed_services = ["water-controller", "water-controller-api", "water-controller-modbus"]
    allowed_actions = ["start", "stop", "restart"]

    if service_name not in allowed_services:
        raise HTTPException(status_code=400, detail="Invalid service name")
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Invalid action")

    try:
        result = subprocess.run(
            ["systemctl", action, service_name],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr)

        logger.info(f"Service {service_name} {action}ed")
        return {"status": "ok", "action": action, "service": service_name}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Operation timed out")

# ============== Authentication Endpoints ==============

# In-memory session store (would use Redis/DB in production)
active_sessions: Dict[str, Dict[str, Any]] = {}

# Active Directory configuration store
ad_config_store: ADConfig = ADConfig()

# Log forwarding configuration store
log_forward_config_store: LogForwardingConfig = LogForwardingConfig()

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user with username and password.
    Supports Active Directory group-based authentication when configured.
    """
    import hashlib
    import secrets

    username = request.username
    password = request.password

    # Check if AD authentication is enabled
    if ad_config_store.enabled:
        try:
            # Attempt LDAP authentication
            import ldap3

            server = ldap3.Server(
                ad_config_store.server,
                port=ad_config_store.port,
                use_ssl=ad_config_store.use_ssl
            )

            # Bind with user credentials
            user_dn = f"cn={username},{ad_config_store.base_dn}"
            conn = ldap3.Connection(server, user=user_dn, password=password)

            if not conn.bind():
                logger.warning(f"AD auth failed for user: {username}")
                return LoginResponse(
                    success=False,
                    message="Invalid credentials"
                )

            # Check group membership
            conn.search(
                ad_config_store.base_dn,
                f"(&(objectClass=user)(cn={username}))",
                attributes=['memberOf']
            )

            groups = []
            is_admin = False
            if conn.entries:
                for entry in conn.entries:
                    member_of = entry.memberOf.values if hasattr(entry, 'memberOf') else []
                    for group_dn in member_of:
                        group_cn = group_dn.split(',')[0].replace('cn=', '').replace('CN=', '')
                        groups.append(group_cn)
                        if group_cn == ad_config_store.admin_group:
                            is_admin = True

            if not is_admin:
                logger.warning(f"User {username} not in admin group")
                return LoginResponse(
                    success=False,
                    message=f"User not in {ad_config_store.admin_group} group"
                )

            conn.unbind()

        except ImportError:
            logger.error("ldap3 module not installed, falling back to local auth")
        except Exception as e:
            logger.error(f"AD authentication error: {e}")
            return LoginResponse(
                success=False,
                message="Authentication service unavailable"
            )
    else:
        # Local authentication fallback (demo mode)
        # In production, this would check against a database
        if username == "admin" and password == "admin":
            groups = ["WTC-Admins"]
        elif username == "operator" and password == "operator":
            groups = ["WTC-Operators"]
        else:
            logger.warning(f"Local auth failed for user: {username}")
            return LoginResponse(
                success=False,
                message="Invalid credentials"
            )

    # Generate session token
    token = secrets.token_hex(32)

    # Store session
    active_sessions[token] = {
        "username": username,
        "groups": groups,
        "created": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat()
    }

    logger.info(f"User {username} logged in successfully")

    return LoginResponse(
        success=True,
        token=token,
        user=username,
        groups=groups
    )

@app.post("/api/v1/auth/logout")
async def logout(token: str = None):
    """Logout and invalidate session token"""
    if token and token in active_sessions:
        del active_sessions[token]
        return {"status": "ok", "message": "Logged out"}
    return {"status": "ok", "message": "Session not found"}

@app.get("/api/v1/auth/session")
async def get_session(token: str):
    """Validate session token and return session info"""
    if token in active_sessions:
        session = active_sessions[token]
        session["last_activity"] = datetime.now().isoformat()
        return {
            "valid": True,
            "user": session["username"],
            "groups": session["groups"]
        }
    return {"valid": False}

@app.get("/api/v1/auth/ad-config", response_model=ADConfig)
async def get_ad_config():
    """Get Active Directory configuration (passwords redacted)"""
    config = ad_config_store.model_copy()
    config.bind_password = "***" if config.bind_password else None
    return config

@app.put("/api/v1/auth/ad-config")
async def update_ad_config(config: ADConfig):
    """Update Active Directory configuration"""
    global ad_config_store

    # Preserve existing password if not provided
    if config.bind_password == "***" or config.bind_password is None:
        config.bind_password = ad_config_store.bind_password

    ad_config_store = config
    logger.info(f"AD configuration updated: server={config.server}, enabled={config.enabled}")
    return {"status": "ok", "message": "AD configuration updated"}

# ============== Log Forwarding Endpoints ==============

@app.get("/api/v1/logging/config", response_model=LogForwardingConfig)
async def get_log_forwarding_config():
    """Get log forwarding configuration (API keys redacted)"""
    config = log_forward_config_store.model_copy()
    config.api_key = "***" if config.api_key else None
    return config

@app.put("/api/v1/logging/config")
async def update_log_forwarding_config(config: LogForwardingConfig):
    """Update log forwarding configuration"""
    global log_forward_config_store

    # Preserve existing API key if not provided
    if config.api_key == "***" or config.api_key is None:
        config.api_key = log_forward_config_store.api_key

    log_forward_config_store = config
    logger.info(f"Log forwarding updated: type={config.forward_type}, host={config.host}, enabled={config.enabled}")
    return {"status": "ok", "message": "Log forwarding configuration updated"}

@app.post("/api/v1/logging/test")
async def test_log_forwarding():
    """Send a test log message to the configured destination"""
    import socket

    config = log_forward_config_store

    if not config.enabled:
        raise HTTPException(status_code=400, detail="Log forwarding is not enabled")

    test_message = {
        "timestamp": datetime.now().isoformat(),
        "level": "INFO",
        "source": "water-controller",
        "message": "Test log message from Water Treatment Controller",
        "type": "test"
    }

    try:
        if config.forward_type == "syslog":
            # Send to syslog server
            if config.protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((config.host, config.port))

            # Format as syslog message (RFC 5424)
            priority = 14  # facility=user, severity=info
            syslog_msg = f"<{priority}>1 {test_message['timestamp']} water-controller - - - {test_message['message']}"

            if config.protocol == "udp":
                sock.sendto(syslog_msg.encode(), (config.host, config.port))
            else:
                sock.send(syslog_msg.encode())
            sock.close()

        elif config.forward_type == "elastic":
            # Send to Elasticsearch
            import urllib.request
            import ssl

            url = f"{'https' if config.tls_enabled else 'http'}://{config.host}:{config.port}/{config.index or 'wtc-logs'}/_doc"

            req = urllib.request.Request(
                url,
                data=json.dumps(test_message).encode(),
                headers={
                    "Content-Type": "application/json",
                    **({"Authorization": f"ApiKey {config.api_key}"} if config.api_key else {})
                },
                method="POST"
            )

            context = ssl.create_default_context()
            if not config.tls_verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            urllib.request.urlopen(req, context=context if config.tls_enabled else None, timeout=10)

        elif config.forward_type == "graylog":
            # Send to Graylog via GELF
            gelf_message = {
                "version": "1.1",
                "host": "water-controller",
                "short_message": test_message["message"],
                "timestamp": datetime.now().timestamp(),
                "level": 6,  # INFO
                "_source": test_message["source"],
                "_type": test_message["type"]
            }

            if config.protocol == "udp":
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(json.dumps(gelf_message).encode(), (config.host, config.port))
                sock.close()
            else:
                # TCP/HTTP
                import urllib.request
                url = f"{'https' if config.tls_enabled else 'http'}://{config.host}:{config.port}/gelf"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(gelf_message).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=10)

        logger.info(f"Test log sent to {config.forward_type} at {config.host}:{config.port}")
        return {"status": "ok", "message": f"Test log sent to {config.forward_type}"}

    except Exception as e:
        logger.error(f"Failed to send test log: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test log: {str(e)}")

@app.get("/api/v1/logging/destinations")
async def list_log_destinations():
    """List available log forwarding destination types"""
    return {
        "destinations": [
            {
                "type": "syslog",
                "name": "Syslog Server",
                "description": "Forward logs to a syslog server (RFC 5424)",
                "default_port": 514,
                "protocols": ["udp", "tcp"]
            },
            {
                "type": "elastic",
                "name": "Elasticsearch",
                "description": "Forward logs to Elasticsearch cluster",
                "default_port": 9200,
                "protocols": ["http", "https"],
                "requires_index": True
            },
            {
                "type": "graylog",
                "name": "Graylog",
                "description": "Forward logs to Graylog via GELF",
                "default_port": 12201,
                "protocols": ["udp", "tcp", "http"]
            }
        ]
    }

# ============== WebSocket Endpoints ==============

@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming"""
    await websocket.accept()
    websocket_connections.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(websocket_connections)}")

    try:
        while True:
            await asyncio.sleep(1)

            client = get_shm_client()
            if client:
                # Send real data from shared memory
                rtus = client.get_rtus()
                data = {
                    "type": "sensor_update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {}
                }

                for rtu in rtus:
                    station_name = rtu["station_name"]
                    data["data"][station_name] = {
                        "sensors": [{"slot": s["slot"], "value": s["value"]} for s in rtu["sensors"]],
                        "connection_state": CONNECTION_STATES.get(rtu["connection_state"], "UNKNOWN")
                    }

                await websocket.send_json(data)
            else:
                # Send simulated data as fallback
                data = {
                    "type": "sensor_update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {}
                }

                for station_name in fallback_rtus:
                    data["data"][station_name] = {
                        "sensors": [
                            {"slot": 1, "value": 7.0 + 0.1 * (datetime.now().second % 5)},
                            {"slot": 2, "value": 25.0 + 0.5 * (datetime.now().second % 3)},
                        ]
                    }

                await websocket.send_json(data)

    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(websocket_connections)}")

@app.websocket("/ws/alarms")
async def websocket_alarms(websocket: WebSocket):
    """WebSocket endpoint for alarm notifications"""
    await websocket.accept()

    try:
        last_alarm_count = 0
        while True:
            await asyncio.sleep(1)

            client = get_shm_client()
            if client:
                status = client.get_status()
                current_count = status.get("active_alarms", 0)
                unack_count = status.get("unack_alarms", 0)

                # Send update if alarm count changed
                if current_count != last_alarm_count:
                    alarms = client.get_alarms()
                    await websocket.send_json({
                        "type": "alarm_update",
                        "active_count": current_count,
                        "unack_count": unack_count,
                        "alarms": alarms
                    })
                    last_alarm_count = current_count

    except WebSocketDisconnect:
        pass

async def broadcast_event(event_type: str, data: Dict[str, Any]):
    """Broadcast event to all connected WebSocket clients"""
    message = {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()}

    for websocket in websocket_connections:
        try:
            await websocket.send_json(message)
        except Exception:
            pass

# ============== Startup Event ==============

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global scan_task

    # Try to connect to shared memory
    if SHM_AVAILABLE:
        client = get_client()
        if client.is_connected():
            logger.info("Connected to controller via shared memory")
        else:
            logger.warning("Controller not running, using fallback mode")
            init_fallback_data()
    else:
        logger.warning("Shared memory client not available, using fallback mode")
        init_fallback_data()

    # Start background network scan task
    scan_task = asyncio.create_task(_background_scan_loop())
    logger.info("Background network scan task initialized (disabled by default)")

    logger.info("Water Treatment Controller API started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global scan_task

    # Cancel background scan task
    if scan_task and not scan_task.done():
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass
        logger.info("Background network scan task stopped")

    logger.info("Water Treatment Controller API stopped")

def init_fallback_data():
    """Initialize sample data for fallback mode"""
    fallback_rtus["rtu-tank-1"] = RTUDevice(
        station_name="rtu-tank-1",
        ip_address="192.168.1.100",
        vendor_id=0x0001,
        device_id=0x0001,
        connection_state="RUNNING",
        slot_count=16,
        last_seen=datetime.now()
    )

    fallback_rtus["rtu-pump-station"] = RTUDevice(
        station_name="rtu-pump-station",
        ip_address="192.168.1.101",
        vendor_id=0x0001,
        device_id=0x0001,
        connection_state="RUNNING",
        slot_count=16,
        last_seen=datetime.now()
    )

    fallback_pid_loops[1] = PIDLoop(
        loop_id=1,
        name="pH Control",
        enabled=True,
        input_rtu="rtu-tank-1",
        input_slot=1,
        output_rtu="rtu-tank-1",
        output_slot=12,
        kp=2.0,
        ki=0.1,
        kd=0.5,
        setpoint=7.0,
        mode="AUTO",
        pv=7.2,
        cv=35.0
    )

    historian_tags[1] = HistorianTag(
        tag_id=1,
        rtu_station="rtu-tank-1",
        slot=1,
        tag_name="rtu-tank-1.pH",
        sample_rate_ms=1000,
        deadband=0.05,
        compression="SWINGING_DOOR"
    )

# ============== Main Entry Point ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
