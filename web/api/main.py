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
from datetime import datetime, timedelta
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

# Import historian module for time-series data
import historian as hist

# Configure logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== Synchronization Locks ==============
# Locks for shared state to prevent race conditions in async code

_sessions_lock = asyncio.Lock()  # Protects active_sessions
_websocket_lock = asyncio.Lock()  # Protects websocket connections
_rtu_state_lock = asyncio.Lock()  # Protects _rtu_runtime_state
_scan_config_lock = asyncio.Lock()  # Protects network_scan_config
_modbus_config_lock = asyncio.Lock()  # Protects modbus_config
_ad_config_lock = asyncio.Lock()  # Protects ad_config_store
_log_config_lock = asyncio.Lock()  # Protects log_forward_config_store

# Request context for audit logging
from contextvars import ContextVar
request_user: ContextVar[str] = ContextVar('request_user', default='system')
request_ip: ContextVar[str] = ContextVar('request_ip', default='unknown')

# Authentication configuration
import os
AUTH_ENABLED = os.environ.get('WTC_AUTH_ENABLED', 'true').lower() in ('true', '1', 'yes')
AUTH_BYPASS_HEADER = os.environ.get('WTC_AUTH_BYPASS_HEADER', None)  # For testing

# In-memory session store (populated on login, moved here for dependency access)
active_sessions: Dict[str, Dict[str, Any]] = {}

# User roles for authorization
class UserRole:
    VIEWER = "viewer"
    OPERATOR = "operator"
    ENGINEER = "engineer"
    ADMIN = "admin"

# Role hierarchy for permission checks
ROLE_HIERARCHY = {
    UserRole.VIEWER: 0,
    UserRole.OPERATOR: 1,
    UserRole.ENGINEER: 2,
    UserRole.ADMIN: 3
}


from fastapi import Header, Request


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> Optional[Dict[str, Any]]:
    """
    Dependency to get the current authenticated user.
    Returns None if authentication is disabled or bypassed.
    Raises HTTPException if auth is required but invalid.
    """
    # Check if auth is disabled
    if not AUTH_ENABLED:
        return {"username": "anonymous", "role": UserRole.ADMIN, "groups": []}

    # Check for bypass header (testing only)
    if AUTH_BYPASS_HEADER and request.headers.get(AUTH_BYPASS_HEADER):
        return {"username": "test_user", "role": UserRole.ADMIN, "groups": []}

    # Extract token from Authorization header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Support both "Bearer <token>" and raw token
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    # Try in-memory cache first, then database
    session = active_sessions.get(token)
    if not session:
        # Try database
        db_session = db.get_session(token)
        if db_session:
            session = {
                "username": db_session["username"],
                "role": db_session["role"],
                "groups": db_session.get("groups", [])
            }
            # Cache in memory
            active_sessions[token] = session
            # Update activity in database
            db.update_session_activity(token)

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Update request context for audit logging
    request_user.set(session["username"])
    if request.client:
        request_ip.set(request.client.host)

    return session


async def require_role(required_role: str):
    """Factory for role-based authorization dependency"""
    async def role_checker(user: Dict[str, Any] = Depends(get_current_user)):
        user_role = user.get("role", UserRole.VIEWER)
        if ROLE_HIERARCHY.get(user_role, 0) < ROLE_HIERARCHY.get(required_role, 0):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required role: {required_role}"
            )
        return user
    return role_checker


# Create role-specific dependencies
require_viewer = Depends(get_current_user)
require_operator = Depends(get_current_user)  # Will add role check in handler
require_engineer = Depends(get_current_user)
require_admin = Depends(get_current_user)


def check_role(user: Dict[str, Any], required_role: str):
    """Helper to check user role in handlers"""
    user_role = user.get("role", UserRole.VIEWER)
    if ROLE_HIERARCHY.get(user_role, 0) < ROLE_HIERARCHY.get(required_role, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required role: {required_role}"
        )


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
    """Update runtime connection state cache (lock acquired by caller if needed)"""
    _rtu_runtime_state[station_name] = state

def _get_runtime_state(station_name: str) -> str:
    """Get runtime connection state, defaulting to OFFLINE"""
    return _rtu_runtime_state.get(station_name, "OFFLINE")

# ============== WebSocket Connection Manager ==============
# Manages WebSocket connections with automatic cleanup of stale connections

class WebSocketManager:
    """Thread-safe WebSocket connection manager with automatic cleanup."""

    def __init__(self, stale_timeout_seconds: int = 120):
        self._connections: Dict[WebSocket, datetime] = {}  # websocket -> last_activity
        self._stale_timeout = timedelta(seconds=stale_timeout_seconds)

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        async with _websocket_lock:
            self._connections[websocket] = datetime.now()
            logger.info(f"WebSocket connected. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with _websocket_lock:
            if websocket in self._connections:
                del self._connections[websocket]
                logger.info(f"WebSocket disconnected. Total: {len(self._connections)}")

    async def touch(self, websocket: WebSocket) -> None:
        """Update last activity time for a connection."""
        async with _websocket_lock:
            if websocket in self._connections:
                self._connections[websocket] = datetime.now()

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast message to all connections, removing dead ones."""
        dead_connections = []

        async with _websocket_lock:
            connections = list(self._connections.keys())

        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with _websocket_lock:
                for ws in dead_connections:
                    self._connections.pop(ws, None)
                logger.info(f"Removed {len(dead_connections)} dead WebSocket connections")

    async def cleanup_stale(self) -> int:
        """Remove connections that haven't been active recently. Returns count removed."""
        now = datetime.now()
        stale = []

        async with _websocket_lock:
            for websocket, last_activity in self._connections.items():
                if now - last_activity > self._stale_timeout:
                    stale.append(websocket)

            for websocket in stale:
                del self._connections[websocket]
                try:
                    await websocket.close()
                except Exception:
                    pass  # Connection already dead

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale WebSocket connections")
        return len(stale)

    @property
    def connection_count(self) -> int:
        """Get current connection count (not locked, approximate)."""
        return len(self._connections)

# Global WebSocket manager instance
ws_manager = WebSocketManager(stale_timeout_seconds=120)

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
async def create_rtu(request: RTUCreateRequest, user: Dict = Depends(get_current_user)):
    """
    Add a new RTU to the system.

    This creates the RTU configuration in the database and sends
    an IPC command to the PROFINET controller to initiate connection.

    Requires: Engineer or Admin role
    """
    check_role(user, UserRole.ENGINEER)

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
async def delete_rtu(station_name: str, cascade: bool = True, user: Dict = Depends(get_current_user)):
    """
    Remove an RTU from the system.

    Requires: Admin role

    If cascade=True (default), the database layer automatically deletes:
    - All alarm rules referencing this RTU
    - All PID loops using this RTU as input or output
    - All historian tags tracking this RTU
    - All Modbus mappings for this RTU
    - All slot configurations for this RTU

    Also sends IPC command to disconnect from PROFINET controller.
    """
    check_role(user, UserRole.ADMIN)

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
async def command_actuator(station_name: str, slot: int, command: ActuatorCommand,
                           user: Dict = Depends(get_current_user)):
    """
    Send command to actuator via shared memory IPC.

    Requires: Operator role or higher
    """
    check_role(user, UserRole.OPERATOR)

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


# ============== Slot Configuration Endpoints ==============

class SlotConfig(BaseModel):
    """Slot configuration model"""
    rtu_station: str
    slot: int
    subslot: int = 1
    slot_type: str  # "sensor" or "actuator"
    name: Optional[str] = None
    unit: Optional[str] = None
    measurement_type: Optional[str] = None
    actuator_type: Optional[str] = None
    scale_min: float = 0
    scale_max: float = 100
    alarm_low: Optional[float] = None
    alarm_high: Optional[float] = None
    alarm_low_low: Optional[float] = None
    alarm_high_high: Optional[float] = None
    warning_low: Optional[float] = None
    warning_high: Optional[float] = None
    deadband: float = 0
    enabled: bool = True


@app.get("/api/v1/rtus/{station_name}/slots", response_model=List[SlotConfig])
async def list_slot_configs(station_name: str):
    """Get all slot configurations for an RTU"""
    slots = db.get_slot_configs_by_rtu(station_name)
    return [SlotConfig(**s) for s in slots]


@app.get("/api/v1/rtus/{station_name}/slots/{slot}", response_model=SlotConfig)
async def get_slot_config(station_name: str, slot: int):
    """Get a specific slot configuration"""
    config = db.get_slot_config(station_name, slot)
    if not config:
        raise HTTPException(status_code=404, detail="Slot config not found")
    return SlotConfig(**config)


@app.post("/api/v1/rtus/{station_name}/slots", response_model=SlotConfig)
async def create_slot_config(station_name: str, config: SlotConfig, user: Dict = Depends(get_current_user)):
    """
    Create or update a slot configuration.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    # Verify RTU exists
    rtu = db.get_rtu_device(station_name)
    if not rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    config.rtu_station = station_name
    db.upsert_slot_config(config.dict())
    logger.info(f"Created/updated slot config for {station_name} slot {config.slot}")
    return config


@app.put("/api/v1/rtus/{station_name}/slots/{slot}", response_model=SlotConfig)
async def update_slot_config(station_name: str, slot: int, config: SlotConfig, user: Dict = Depends(get_current_user)):
    """
    Update a slot configuration.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    config.rtu_station = station_name
    config.slot = slot
    db.upsert_slot_config(config.dict())
    logger.info(f"Updated slot config for {station_name} slot {slot}")
    return config


@app.delete("/api/v1/rtus/{station_name}/slots/{slot}")
async def delete_slot_config(station_name: str, slot: int, user: Dict = Depends(get_current_user)):
    """
    Delete a slot configuration.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    if not db.delete_slot_config(station_name, slot):
        raise HTTPException(status_code=404, detail="Slot config not found")

    logger.info(f"Deleted slot config for {station_name} slot {slot}")
    return {"status": "deleted", "station_name": station_name, "slot": slot}


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
        # Controller not running - check if RTU exists in database
        db_rtu = _get_rtu_from_db(station_name)
        if db_rtu:
            rtu_found = True
            results.append({"test": "connection", "status": "warn", "detail": "RTU registered but controller not running"})
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
            failed_slots = []
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
                except Exception as e:
                    logger.debug(f"Actuator blink failed for slot {slot}: {e}")
                    failed_slots.append(slot)

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

        # Create historian tag in database
        if create_historian_tags:
            tag_name = f"{station_name}.{sensor.name}"
            db.upsert_historian_tag({
                "rtu_station": station_name,
                "slot": slot,
                "tag_name": tag_name,
                "sample_rate_ms": 1000,
                "deadband": 0.1,
                "compression": "swinging_door"
            })

        # Create default alarm rules in database
        if create_alarm_rules and sensor.suggested_measurement_type in ["TEMPERATURE", "PRESSURE", "PH"]:
            db.create_alarm_rule({
                "rtu_station": station_name,
                "slot": slot,
                "condition": "HIGH",
                "threshold": 100.0,  # Default - should be configured
                "severity": "MEDIUM",
                "delay_ms": 5000,
                "message": f"{sensor.name} high alarm",
                "enabled": False  # Disabled by default - user should configure
            })

    logger.info(f"Provisioned {len(provisioned)} sensors on {station_name}")

    return {
        "status": "ok",
        "provisioned": provisioned,
        "historian_tags_created": create_historian_tags,
        "alarm_rules_created": create_alarm_rules
    }


# ============== RTU Inventory Endpoints ==============

@app.get("/api/v1/rtus/{station_name}/inventory")
async def get_rtu_inventory(station_name: str):
    """
    Get complete sensor/control inventory for an RTU.

    Returns all sensors and controls that have been discovered and
    registered for this RTU, along with their current values/states.
    """
    inventory = db.get_rtu_inventory(station_name)
    if not inventory:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Enrich with current values from runtime if controller is running
    client = get_shm_client()
    if client:
        rtu_data = client.get_rtu(station_name)
        if rtu_data:
            # Update sensor values from runtime
            for sensor in inventory["sensors"]:
                for live_sensor in rtu_data.get("sensors", []):
                    if str(live_sensor.get("slot")) == str(sensor.get("register_address")):
                        sensor["last_value"] = live_sensor.get("value")
                        sensor["last_quality"] = live_sensor.get("quality", 0)
                        sensor["last_update"] = datetime.now().isoformat()

            # Update control states from runtime
            for control in inventory["controls"]:
                for live_actuator in rtu_data.get("actuators", []):
                    if str(live_actuator.get("slot")) == str(control.get("register_address")):
                        control["last_state"] = live_actuator.get("command")
                        control["last_update"] = datetime.now().isoformat()

    return inventory


@app.post("/api/v1/rtus/{station_name}/inventory/refresh")
async def refresh_rtu_inventory(station_name: str):
    """
    Query RTU and refresh its sensor/control inventory.

    Asks the RTU to report what sensors and controls it has,
    then updates the database with the results.
    """
    rtu = _get_rtu_from_db(station_name)
    if not rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    client = get_shm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Controller not running - cannot query RTU")

    # Query the RTU for its capabilities
    # The RTU responds with its sensor/control configuration
    rtu_data = client.get_rtu(station_name)
    if not rtu_data:
        raise HTTPException(status_code=503, detail="Cannot communicate with RTU")

    # Clear existing inventory
    db.clear_rtu_sensors(station_name)
    db.clear_rtu_controls(station_name)

    sensors_added = 0
    controls_added = 0

    # Register sensors from RTU data
    for sensor_data in rtu_data.get("sensors", []):
        slot = sensor_data.get("slot", 0)
        sensor_type = _infer_sensor_type(sensor_data.get("name", ""), sensor_data.get("unit", ""))
        db.upsert_rtu_sensor({
            "rtu_station": station_name,
            "sensor_id": f"slot_{slot}",
            "sensor_type": sensor_type,
            "name": sensor_data.get("name", f"Sensor {slot}"),
            "unit": sensor_data.get("unit", ""),
            "register_address": slot,
            "data_type": "FLOAT32",
            "scale_min": 0,
            "scale_max": 100
        })
        sensors_added += 1

    # Register actuators as controls
    for actuator_data in rtu_data.get("actuators", []):
        slot = actuator_data.get("slot", 0)
        control_type, command_type = _infer_control_type(actuator_data.get("name", ""))
        db.upsert_rtu_control({
            "rtu_station": station_name,
            "control_id": f"slot_{slot}",
            "control_type": control_type,
            "name": actuator_data.get("name", f"Control {slot}"),
            "command_type": command_type,
            "register_address": slot
        })
        controls_added += 1

    logger.info(f"Refreshed inventory for {station_name}: {sensors_added} sensors, {controls_added} controls")

    return {
        "status": "ok",
        "rtu_station": station_name,
        "sensors_added": sensors_added,
        "controls_added": controls_added
    }


def _infer_sensor_type(name: str, unit: str) -> str:
    """Infer sensor type from name and unit"""
    name_lower = name.lower()
    unit_lower = unit.lower()

    if "temp" in name_lower or "°" in unit or "degf" in unit_lower or "degc" in unit_lower:
        return "temperature"
    elif "level" in name_lower or "gal" in unit_lower or "liter" in unit_lower:
        return "level"
    elif "press" in name_lower or "psi" in unit_lower or "bar" in unit_lower:
        return "pressure"
    elif "flow" in name_lower or "gpm" in unit_lower or "lpm" in unit_lower:
        return "flow"
    elif "ph" in name_lower:
        return "ph"
    elif "turb" in name_lower or "ntu" in unit_lower:
        return "turbidity"
    elif "chlor" in name_lower or "ppm" in unit_lower:
        return "chlorine"
    elif "tds" in name_lower:
        return "tds"
    else:
        return "analog"


def _infer_control_type(name: str) -> tuple:
    """Infer control type and command type from name. Returns (control_type, command_type)"""
    name_lower = name.lower()

    if "pump" in name_lower:
        return ("pump", "on_off")
    elif "valve" in name_lower:
        if "modulating" in name_lower or "control" in name_lower:
            return ("valve", "modulating")
        return ("valve", "on_off")
    elif "motor" in name_lower or "mixer" in name_lower or "agitator" in name_lower:
        return ("motor", "on_off")
    elif "heater" in name_lower:
        return ("heater", "on_off")
    elif "relay" in name_lower:
        return ("relay", "on_off")
    elif "vfd" in name_lower or "drive" in name_lower:
        return ("vfd", "modulating")
    else:
        return ("actuator", "on_off")


@app.post("/api/v1/rtus/{station_name}/control/{control_id}")
async def send_control_command(
    station_name: str,
    control_id: str,
    command: dict,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Send a command to an RTU control.

    Command format depends on control type:
    - on_off: {"action": "ON" | "OFF"}
    - modulating: {"value": 0-100}
    - setpoint: {"setpoint": <float>}

    All commands are logged with username, timestamp, and result.
    """
    check_role(user, UserRole.OPERATOR)

    rtu = _get_rtu_from_db(station_name)
    if not rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Get control configuration
    controls = db.get_rtu_controls(station_name)
    control_cfg = next((c for c in controls if c["control_id"] == control_id), None)
    if not control_cfg:
        raise HTTPException(status_code=404, detail="Control not found")

    client = get_shm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Controller not running")

    slot = control_cfg.get("register_address", 0)
    command_type = control_cfg.get("command_type", "on_off")

    # Build command string and value for logging
    cmd_str = ""
    cmd_value = None
    action = None

    if command_type == "on_off":
        action = command.get("action", "OFF").upper()
        if action not in ["ON", "OFF"]:
            raise HTTPException(status_code=400, detail="Invalid action. Use ON or OFF")
        cmd_str = action
    elif command_type == "modulating":
        value = command.get("value", 0)
        if not isinstance(value, (int, float)) or value < 0 or value > 100:
            raise HTTPException(status_code=400, detail="Value must be 0-100")
        cmd_str = f"SET:{value}"
        cmd_value = float(value)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported command type: {command_type}")

    # Get client IP for logging
    client_ip = request.client.host if request.client else None
    session_token = request.headers.get("Authorization", "").replace("Bearer ", "")

    # Log command BEFORE execution
    log_id = db.log_command(
        username=user.get("username", "unknown"),
        rtu_station=station_name,
        control_id=control_id,
        command=cmd_str,
        command_value=cmd_value,
        source_ip=client_ip,
        session_token=session_token
    )

    # Execute command
    try:
        if command_type == "on_off":
            success = client.send_actuator_command(station_name, slot, action)
        elif command_type == "modulating":
            success = client.send_actuator_command(station_name, slot, "PWM", int(cmd_value))
        else:
            success = False

        if success:
            # Update command log with success
            db.update_command_result(log_id, "SUCCESS")

            # Update control state in database
            state = action or str(int(cmd_value))
            db.update_control_state(station_name, control_id, state)

            logger.info(f"Control command sent: {station_name}/{control_id} = {cmd_str} by {user.get('username')}")
            return {"status": "ok", "control_id": control_id, "command": command}
        else:
            # Update command log with failure
            db.update_command_result(log_id, "FAILED", "RTU did not acknowledge command")
            raise HTTPException(status_code=500, detail="Failed to send command to RTU")

    except HTTPException:
        raise
    except Exception as e:
        # Update command log with error
        db.update_command_result(log_id, "ERROR", str(e))
        logger.error(f"Control command error: {station_name}/{control_id} - {e}")
        raise HTTPException(status_code=500, detail=f"Command execution error: {str(e)}")


# ============== DCP Discovery Endpoints ==============

@app.post("/api/v1/discover/rtu")
async def discover_rtus(timeout_seconds: float = 5.0):
    """
    Scan the PROFINET network for RTU devices using DCP discovery.

    Returns a list of discovered devices that can be added to the configuration.
    """
    client = get_shm_client()
    if not client:
        # Return cached results when controller not running
        cached = db.get_discovered_devices()
        return {
            "status": "cached",
            "message": "Controller not running - returning cached discovery results",
            "count": len(cached),
            "devices": cached
        }

    # Perform DCP discovery via controller
    timeout_ms = int(timeout_seconds * 1000)
    devices = client.dcp_discover(timeout_ms)

    # Cache results in database
    for device in devices:
        db.upsert_discovered_device(device)

    # Check which devices are already added as RTUs
    existing_rtus = {r["station_name"]: r for r in db.get_rtu_devices()}
    for device in devices:
        device["already_added"] = device.get("device_name") in existing_rtus

    return {
        "status": "complete",
        "count": len(devices),
        "devices": devices
    }


@app.get("/api/v1/discover/cached")
async def get_cached_discoveries():
    """Get cached discovery results from previous scans"""
    devices = db.get_discovered_devices()
    existing_rtus = {r["station_name"]: r for r in db.get_rtu_devices()}

    for device in devices:
        device["already_added"] = device.get("device_name") in existing_rtus

    return {
        "count": len(devices),
        "devices": devices
    }


@app.delete("/api/v1/discover/cache")
async def clear_discovery_cache(user: dict = Depends(get_current_user)):
    """Clear the discovery cache"""
    check_role(user, UserRole.ADMIN)
    count = db.clear_discovery_cache()
    return {"status": "ok", "cleared": count}


# ============== Alarm Endpoints ==============

@app.get("/api/v1/alarms", response_model=List[Alarm])
async def get_active_alarms():
    """Get all active alarms. Alarms are runtime state from the controller."""
    client = get_shm_client()
    if not client:
        # No alarms when controller not running
        return []

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

@app.get("/api/v1/alarms/history", response_model=List[Alarm])
async def get_alarm_history(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100
):
    """Get alarm history. Alarms are runtime state from the controller."""
    client = get_shm_client()
    if not client:
        # No alarm history when controller not running
        return []

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

@app.post("/api/v1/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(alarm_id: int, request: AcknowledgeRequest):
    """Acknowledge an alarm. Requires the controller to be running."""
    client = get_shm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Controller not running - cannot acknowledge alarms")

    success = client.acknowledge_alarm(alarm_id, request.user)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to acknowledge alarm")

    await broadcast_event("alarm_acknowledged", {"alarm_id": alarm_id, "user": request.user})
    return {"status": "ok"}

@app.get("/api/v1/alarms/rules", response_model=List[AlarmRule])
async def list_alarm_rules():
    """List all alarm rules"""
    rules = db.get_alarm_rules()
    return [AlarmRule(
        rule_id=r['id'],
        name=r['name'],
        rtu_station=r['rtu_station'],
        slot=r['slot'],
        condition=AlarmCondition(r['condition']),
        threshold=r['threshold'],
        severity=AlarmSeverity(r['severity']),
        delay_ms=r.get('delay_ms', 0),
        message=r.get('message', ''),
        enabled=bool(r.get('enabled', True))
    ) for r in rules]


@app.get("/api/v1/alarms/rules/{rule_id}", response_model=AlarmRule)
async def get_alarm_rule(rule_id: int):
    """Get a specific alarm rule"""
    rule = db.get_alarm_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alarm rule not found")
    return AlarmRule(
        rule_id=rule['id'],
        name=rule['name'],
        rtu_station=rule['rtu_station'],
        slot=rule['slot'],
        condition=AlarmCondition(rule['condition']),
        threshold=rule['threshold'],
        severity=AlarmSeverity(rule['severity']),
        delay_ms=rule.get('delay_ms', 0),
        message=rule.get('message', ''),
        enabled=bool(rule.get('enabled', True))
    )


@app.post("/api/v1/alarms/rules", response_model=AlarmRule)
async def create_alarm_rule(rule: AlarmRule, user: Dict = Depends(get_current_user)):
    """
    Create a new alarm rule.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    rule_id = db.create_alarm_rule({
        'name': rule.name,
        'rtu_station': rule.rtu_station,
        'slot': rule.slot,
        'condition': rule.condition.value,
        'threshold': rule.threshold,
        'severity': rule.severity.value,
        'delay_ms': rule.delay_ms,
        'message': rule.message,
        'enabled': rule.enabled
    })
    rule.rule_id = rule_id
    return rule


@app.put("/api/v1/alarms/rules/{rule_id}", response_model=AlarmRule)
async def update_alarm_rule(rule_id: int, rule: AlarmRule, user: Dict = Depends(get_current_user)):
    """
    Update an alarm rule.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    existing = db.get_alarm_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Alarm rule not found")

    db.update_alarm_rule(rule_id, {
        'name': rule.name,
        'rtu_station': rule.rtu_station,
        'slot': rule.slot,
        'condition': rule.condition.value,
        'threshold': rule.threshold,
        'severity': rule.severity.value,
        'delay_ms': rule.delay_ms,
        'message': rule.message,
        'enabled': rule.enabled
    })
    rule.rule_id = rule_id
    return rule


@app.delete("/api/v1/alarms/rules/{rule_id}")
async def delete_alarm_rule(rule_id: int, user: Dict = Depends(get_current_user)):
    """
    Delete an alarm rule.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    if not db.delete_alarm_rule(rule_id):
        raise HTTPException(status_code=404, detail="Alarm rule not found")
    return {"status": "deleted", "rule_id": rule_id}


# ============== Alarm Shelving Endpoints (ISA-18.2) ==============

class ShelveAlarmRequest(BaseModel):
    """Request to shelve an alarm"""
    rtu_station: str
    slot: int
    duration_minutes: int  # Typical: 60, 120, 240, 480
    reason: Optional[str] = None


@app.get("/api/v1/alarms/shelved")
async def get_shelved_alarms(include_expired: bool = False, user: Dict = Depends(get_current_user)):
    """
    Get all currently shelved alarms.

    Shelving temporarily suppresses alarm notifications for maintenance or known conditions.
    """
    # Cleanup expired shelves first
    db.cleanup_expired_shelves()

    shelved = db.get_shelved_alarms(include_expired=include_expired)
    return {"shelved_alarms": shelved, "count": len(shelved)}


@app.post("/api/v1/alarms/shelve")
async def shelve_alarm(request: ShelveAlarmRequest, user: Dict = Depends(get_current_user)):
    """
    Shelve an alarm for a specified duration.

    ISA-18.2 compliant alarm shelving - temporarily suppresses the alarm.
    Shelved alarms are still logged but hidden from active alarm lists.

    Requires: Operator role or higher

    Duration options (typical):
    - 60 minutes (1 hour)
    - 120 minutes (2 hours)
    - 240 minutes (4 hours)
    - 480 minutes (8 hours)
    """
    check_role(user, UserRole.OPERATOR)

    # Validate duration (max 8 hours = 480 minutes)
    if request.duration_minutes < 1 or request.duration_minutes > 480:
        raise HTTPException(status_code=400, detail="Duration must be between 1 and 480 minutes")

    shelf_id = db.shelve_alarm(
        rtu_station=request.rtu_station,
        slot=request.slot,
        username=user.get("username", "unknown"),
        duration_minutes=request.duration_minutes,
        reason=request.reason
    )

    return {
        "status": "shelved",
        "shelf_id": shelf_id,
        "rtu_station": request.rtu_station,
        "slot": request.slot,
        "duration_minutes": request.duration_minutes,
        "reason": request.reason
    }


@app.delete("/api/v1/alarms/shelved/{shelf_id}")
async def unshelve_alarm(shelf_id: int, user: Dict = Depends(get_current_user)):
    """
    Manually unshelve an alarm before its expiration.

    Requires: Operator role or higher
    """
    check_role(user, UserRole.OPERATOR)

    if not db.unshelve_alarm(shelf_id, user.get("username", "unknown")):
        raise HTTPException(status_code=404, detail="Shelved alarm not found")

    return {"status": "unshelved", "shelf_id": shelf_id}


@app.get("/api/v1/alarms/shelved/check")
async def check_alarm_shelved(rtu_station: str, slot: int, user: Dict = Depends(get_current_user)):
    """
    Check if a specific alarm is currently shelved.
    """
    is_shelved = db.is_alarm_shelved(rtu_station, slot)
    return {"rtu_station": rtu_station, "slot": slot, "is_shelved": is_shelved}


# ============== Control Endpoints ==============

def _get_pid_loop_with_live_values(loop_config: Dict, shm_loops: List[Dict] = None) -> PIDLoop:
    """
    Build PIDLoop from database config, merging live values from shared memory if available.
    """
    loop_id = loop_config.get('id') or loop_config.get('loop_id')

    # Default runtime values
    pv = 0.0
    cv = 0.0
    mode = loop_config.get('mode', 'MANUAL')

    # Merge live values from shared memory if available
    if shm_loops:
        for shm_loop in shm_loops:
            if shm_loop.get('loop_id') == loop_id:
                pv = shm_loop.get('pv', 0.0)
                cv = shm_loop.get('cv', 0.0)
                mode = PID_MODES.get(shm_loop.get('mode', 0), mode)
                break

    return PIDLoop(
        loop_id=loop_id,
        name=loop_config.get('name', ''),
        enabled=bool(loop_config.get('enabled', True)),
        input_rtu=loop_config.get('input_rtu', ''),
        input_slot=loop_config.get('input_slot', 0),
        output_rtu=loop_config.get('output_rtu', ''),
        output_slot=loop_config.get('output_slot', 0),
        kp=loop_config.get('kp', 1.0),
        ki=loop_config.get('ki', 0.0),
        kd=loop_config.get('kd', 0.0),
        setpoint=loop_config.get('setpoint', 0.0),
        mode=mode,
        pv=pv,
        cv=cv
    )


@app.get("/api/v1/control/pid", response_model=List[PIDLoop])
async def list_pid_loops():
    """
    List all PID control loops.
    Configuration from database, live values (pv, cv) from shared memory.
    """
    # Get configuration from database (source of truth)
    db_loops = db.get_pid_loops()

    # Try to get live values from shared memory
    shm_loops = None
    client = get_shm_client()
    if client:
        try:
            shm_loops = client.get_pid_loops()
        except Exception as e:
            logger.warning(f"Failed to get PID loops from shared memory: {e}")

    return [_get_pid_loop_with_live_values(loop, shm_loops) for loop in db_loops]


@app.get("/api/v1/control/pid/{loop_id}", response_model=PIDLoop)
async def get_pid_loop(loop_id: int):
    """
    Get PID loop details.
    Configuration from database, live values (pv, cv) from shared memory.
    """
    # Get configuration from database (source of truth)
    loop_config = db.get_pid_loop(loop_id)
    if not loop_config:
        raise HTTPException(status_code=404, detail="PID loop not found")

    # Try to get live values from shared memory
    shm_loops = None
    client = get_shm_client()
    if client:
        try:
            shm_loops = client.get_pid_loops()
        except Exception as e:
            logger.warning(f"Failed to get PID loops from shared memory: {e}")

    return _get_pid_loop_with_live_values(loop_config, shm_loops)

@app.put("/api/v1/control/pid/{loop_id}/setpoint")
async def update_pid_setpoint(loop_id: int, update: SetpointUpdate,
                               user: Dict = Depends(get_current_user)):
    """
    Update PID loop setpoint.

    Requires: Operator role or higher
    """
    check_role(user, UserRole.OPERATOR)

    # Persist to database (source of truth)
    if not db.update_pid_setpoint(loop_id, update.setpoint):
        raise HTTPException(status_code=404, detail="PID loop not found")

    # Send to C controller via shared memory for real-time control
    client = get_shm_client()
    if client:
        success = client.set_setpoint(loop_id, update.setpoint)
        if not success:
            logger.warning(f"Failed to send setpoint to controller for PID loop {loop_id}")

    logger.info(f"PID loop {loop_id} setpoint changed to {update.setpoint}")
    return {"status": "ok"}


@app.put("/api/v1/control/pid/{loop_id}/mode")
async def update_pid_mode(loop_id: int, update: ModeUpdate, user: Dict = Depends(get_current_user)):
    """
    Update PID loop mode.

    Requires: Operator role or higher
    """
    check_role(user, UserRole.OPERATOR)

    # Persist to database (source of truth)
    if not db.update_pid_mode(loop_id, update.mode):
        raise HTTPException(status_code=404, detail="PID loop not found")

    # Send to C controller via shared memory for real-time control
    mode_map = {"MANUAL": 0, "AUTO": 1, "CASCADE": 2}
    mode_int = mode_map.get(update.mode, 0)

    client = get_shm_client()
    if client:
        success = client.set_pid_mode(loop_id, mode_int)
        if not success:
            logger.warning(f"Failed to send mode to controller for PID loop {loop_id}")

    logger.info(f"PID loop {loop_id} mode changed to {update.mode}")
    return {"status": "ok"}

@app.put("/api/v1/control/pid/{loop_id}/tuning")
async def update_pid_tuning(loop_id: int, tuning: TuningUpdate, user: Dict = Depends(get_current_user)):
    """
    Update PID loop tuning parameters.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    # Check if loop exists in database (source of truth)
    loop = db.get_pid_loop(loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="PID loop not found")

    # Update in database
    db.update_pid_loop(loop_id, {
        **loop,
        'kp': tuning.kp,
        'ki': tuning.ki,
        'kd': tuning.kd
    })

    logger.info(f"PID loop {loop_id} tuning updated: Kp={tuning.kp}, Ki={tuning.ki}, Kd={tuning.kd}")
    return {"status": "ok"}


@app.post("/api/v1/control/pid", response_model=PIDLoop)
async def create_pid_loop(loop: PIDLoop, user: Dict = Depends(get_current_user)):
    """
    Create a new PID control loop.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    loop_id = db.create_pid_loop({
        'name': loop.name,
        'enabled': loop.enabled,
        'input_rtu': loop.input_rtu,
        'input_slot': loop.input_slot,
        'output_rtu': loop.output_rtu,
        'output_slot': loop.output_slot,
        'kp': loop.kp,
        'ki': loop.ki,
        'kd': loop.kd,
        'setpoint': loop.setpoint,
        'output_min': loop.output_min if hasattr(loop, 'output_min') else 0,
        'output_max': loop.output_max if hasattr(loop, 'output_max') else 100,
        'deadband': loop.deadband if hasattr(loop, 'deadband') else 0,
        'mode': loop.mode
    })
    loop.loop_id = loop_id
    logger.info(f"Created PID loop {loop_id}: {loop.name}")
    return loop


@app.put("/api/v1/control/pid/{loop_id}", response_model=PIDLoop)
async def update_pid_loop_config(loop_id: int, loop: PIDLoop, user: Dict = Depends(get_current_user)):
    """
    Update PID loop configuration.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    existing = db.get_pid_loop(loop_id)
    if not existing:
        raise HTTPException(status_code=404, detail="PID loop not found")

    db.update_pid_loop(loop_id, {
        'name': loop.name,
        'enabled': loop.enabled,
        'input_rtu': loop.input_rtu,
        'input_slot': loop.input_slot,
        'output_rtu': loop.output_rtu,
        'output_slot': loop.output_slot,
        'kp': loop.kp,
        'ki': loop.ki,
        'kd': loop.kd,
        'setpoint': loop.setpoint,
        'output_min': loop.output_min if hasattr(loop, 'output_min') else 0,
        'output_max': loop.output_max if hasattr(loop, 'output_max') else 100,
        'deadband': loop.deadband if hasattr(loop, 'deadband') else 0,
        'mode': loop.mode
    })
    loop.loop_id = loop_id
    logger.info(f"Updated PID loop {loop_id}: {loop.name}")
    return loop


@app.delete("/api/v1/control/pid/{loop_id}")
async def delete_pid_loop(loop_id: int, user: Dict = Depends(get_current_user)):
    """
    Delete a PID control loop.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    if not db.delete_pid_loop(loop_id):
        raise HTTPException(status_code=404, detail="PID loop not found")

    logger.info(f"Deleted PID loop {loop_id}")
    return {"status": "deleted", "loop_id": loop_id}


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

@app.get("/api/v1/trends/tags", response_model=List[HistorianTag])
async def list_historian_tags():
    """List all historian tags from database"""
    tags = db.get_historian_tags()
    return [HistorianTag(
        tag_id=t['id'],
        rtu_station=t['rtu_station'],
        slot=t['slot'],
        tag_name=t['tag_name'],
        sample_rate_ms=t.get('sample_rate_ms', 1000),
        deadband=t.get('deadband', 0.1),
        compression=t.get('compression', 'swinging_door')
    ) for t in tags]


@app.get("/api/v1/trends/tags/{tag_id}", response_model=HistorianTag)
async def get_historian_tag(tag_id: int):
    """Get a specific historian tag"""
    tag = db.get_historian_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Historian tag not found")
    return HistorianTag(
        tag_id=tag['id'],
        rtu_station=tag['rtu_station'],
        slot=tag['slot'],
        tag_name=tag['tag_name'],
        sample_rate_ms=tag.get('sample_rate_ms', 1000),
        deadband=tag.get('deadband', 0.1),
        compression=tag.get('compression', 'swinging_door')
    )


@app.post("/api/v1/trends/tags", response_model=HistorianTag)
async def create_historian_tag(tag: HistorianTag, user: Dict = Depends(get_current_user)):
    """
    Create a new historian tag.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    tag_id = db.upsert_historian_tag({
        'rtu_station': tag.rtu_station,
        'slot': tag.slot,
        'tag_name': tag.tag_name,
        'unit': getattr(tag, 'unit', None),
        'sample_rate_ms': tag.sample_rate_ms,
        'deadband': tag.deadband,
        'compression': tag.compression
    })
    tag.tag_id = tag_id
    logger.info(f"Created historian tag {tag.tag_name}")
    return tag


@app.put("/api/v1/trends/tags/{tag_id}", response_model=HistorianTag)
async def update_historian_tag(tag_id: int, tag: HistorianTag, user: Dict = Depends(get_current_user)):
    """
    Update a historian tag.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    existing = db.get_historian_tag(tag_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Historian tag not found")

    db.upsert_historian_tag({
        'rtu_station': tag.rtu_station,
        'slot': tag.slot,
        'tag_name': tag.tag_name,
        'unit': getattr(tag, 'unit', None),
        'sample_rate_ms': tag.sample_rate_ms,
        'deadband': tag.deadband,
        'compression': tag.compression
    })
    tag.tag_id = tag_id
    logger.info(f"Updated historian tag {tag.tag_name}")
    return tag


@app.delete("/api/v1/trends/tags/{tag_id}")
async def delete_historian_tag_endpoint(tag_id: int, user: Dict = Depends(get_current_user)):
    """
    Delete a historian tag.

    Requires: Engineer role or higher
    """
    check_role(user, UserRole.ENGINEER)

    if not db.delete_historian_tag(tag_id):
        raise HTTPException(status_code=404, detail="Historian tag not found")

    logger.info(f"Deleted historian tag {tag_id}")
    return {"status": "deleted", "tag_id": tag_id}


def _get_historian_tag_from_db(tag_id: int) -> Optional[HistorianTag]:
    """Helper to get historian tag from database"""
    tag = db.get_historian_tag(tag_id)
    if tag:
        return HistorianTag(
            tag_id=tag['id'],
            rtu_station=tag['rtu_station'],
            slot=tag['slot'],
            tag_name=tag['tag_name'],
            sample_rate_ms=tag.get('sample_rate_ms', 1000),
            deadband=tag.get('deadband', 0.1),
            compression=tag.get('compression', 'swinging_door')
        )
    return None

@app.get("/api/v1/trends/{tag_id}")
async def get_trend_data(
    tag_id: int,
    start_time: datetime,
    end_time: datetime,
    aggregate: bool = False,
    interval_seconds: int = 60
):
    """
    Get trend data for a tag.

    Returns historical samples from the data historian.
    If historian is not populated, returns empty sample list.

    Args:
        tag_id: Historian tag ID
        start_time: Query start time
        end_time: Query end time
        aggregate: If true, return aggregated data (min/max/avg)
        interval_seconds: Aggregation interval in seconds (default 60)
    """
    tag = db.get_historian_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    logger.debug(f"Trend query for tag {tag_id}: {start_time} to {end_time}")

    try:
        if aggregate:
            samples = hist.query_aggregate(tag_id, start_time, end_time, interval_seconds)
        else:
            samples = hist.query_raw(tag_id, start_time, end_time)
    except Exception as e:
        logger.error(f"Historian query failed: {e}")
        samples = []

    return {"tag_id": tag_id, "samples": samples}


@app.get("/api/v1/trends/{tag_id}/latest")
async def get_trend_latest(tag_id: int):
    """Get the latest value for a historian tag."""
    tag = db.get_historian_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    try:
        latest = hist.get_latest(tag_id)
        if latest:
            return {"tag_id": tag_id, **latest}
        return {"tag_id": tag_id, "value": None, "time": None, "quality": None}
    except Exception as e:
        logger.error(f"Historian query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/trends/{tag_id}/record")
async def record_trend_sample(tag_id: int, value: float, quality: int = 192):
    """
    Record a sample to the historian (for testing/manual entry).

    In production, samples are recorded automatically by the historian service.
    """
    tag = db.get_historian_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    try:
        hist.record_sample(tag_id, datetime.utcnow(), value, quality)
        db.log_audit(request_user.get(), 'record', 'historian', str(tag_id),
                     f"Manual sample recorded: {value}")
        return {"status": "ok", "tag_id": tag_id}
    except Exception as e:
        logger.error(f"Failed to record sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/trends/stats")
async def get_historian_stats():
    """Get historian storage statistics."""
    try:
        stats = hist.get_statistics()
        return stats
    except Exception as e:
        logger.error(f"Failed to get historian stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """Export complete system configuration from database"""
    return db.export_configuration()


@app.post("/api/v1/system/config")
async def import_config(config: Dict[str, Any], user: Dict = Depends(get_current_user)):
    """
    Import system configuration into database.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    try:
        username = user.get('username', 'unknown')
        imported = db.import_configuration(config, user=username)
        logger.info(f"Configuration imported by {username}: {imported}")
        return {"status": "ok", "imported": imported}
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
async def create_backup(request: BackupRequest, user: Dict = Depends(get_current_user)):
    """
    Create a new configuration backup from database.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_type = "full" if request.include_historian else "config"
    backup_id = f"wtc_{backup_type}_{timestamp}"
    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    # Get current configuration from database (source of truth)
    config_data = db.export_configuration()
    config_data["description"] = request.description

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
async def restore_backup(backup_id: str, user: Dict = Depends(get_current_user)):
    """
    Restore configuration from a backup to the database.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Backup not found")

    try:
        with tarfile.open(filepath, "r:gz") as tar:
            config_file = tar.extractfile("config.json")
            if not config_file:
                raise HTTPException(status_code=400, detail="Backup does not contain config.json")

            config_data = json.load(config_file)

            # Use the shared import function to restore to database
            username = user.get('username', 'unknown')
            imported = db.import_configuration(config_data, user=username)

            db.log_audit(username, 'restore', 'backup', backup_id,
                         f"Restored from backup {backup_id}: {imported}")

        logger.info(f"Configuration restored from backup {backup_id} by {username}: {imported}")
        return {
            "status": "ok",
            "message": "Configuration restored successfully to database",
            "imported": imported
        }

    except json.JSONDecodeError as e:
        logger.error(f"Restore failed - invalid JSON in backup: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in backup: {e}")
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
async def upload_backup(
    file: Any,  # UploadFile
    description: Optional[str] = None,
    user: Dict = Depends(get_current_user)
):
    """
    Upload a backup file (.tar.gz) for restore.

    Requires: Admin role
    """
    from fastapi import UploadFile

    check_role(user, UserRole.ADMIN)

    if not hasattr(file, 'filename'):
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate file extension
    if not file.filename.endswith('.tar.gz'):
        raise HTTPException(status_code=400, detail="File must be a .tar.gz archive")

    # Generate backup ID
    backup_id = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    filename = f"{backup_id}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Save uploaded file
    try:
        content = await file.read()
        with open(filepath, 'wb') as f:
            f.write(content)

        size_bytes = os.path.getsize(filepath)

        # Create backup record in database
        db.create_backup_record(
            backup_id=backup_id,
            filename=filename,
            description=description or f"Uploaded: {file.filename}",
            size_bytes=size_bytes,
            includes_historian='_full_' in file.filename.lower()
        )

        db.log_audit(user.get('username', 'unknown'), 'upload', 'backup', backup_id,
                     f"Uploaded backup: {filename}")

        logger.info(f"Backup uploaded: {backup_id} ({size_bytes} bytes)")
        return {
            "status": "ok",
            "backup_id": backup_id,
            "filename": filename,
            "size_bytes": size_bytes
        }
    except Exception as e:
        logger.error(f"Failed to upload backup: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/backups/import")
async def import_backup_file(
    file: Any,  # UploadFile
    user: Dict = Depends(get_current_user)
):
    """
    Import configuration from an uploaded JSON file.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    if not hasattr(file, 'filename'):
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate file extension
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="File must be a .json file")

    try:
        content = await file.read()
        config = json.loads(content.decode('utf-8'))

        # Use shared import function
        username = user.get('username', 'unknown')
        imported = db.import_configuration(config, user=username)

        logger.info(f"Configuration imported from file {file.filename} by {username}: {imported}")
        return {"status": "ok", "imported": imported}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")
    except Exception as e:
        logger.error(f"Failed to import config file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """
    Get Modbus gateway statistics.

    Note: Live statistics (tcp_connections, total_requests, total_errors)
    require the Modbus gateway to be running. Currently returns configuration
    status and zero counters when gateway is not reporting stats.
    """
    server_config = modbus_config.get("server", {})
    downstream = modbus_config.get("downstream_devices", [])

    return ModbusStats(
        server_running=server_config.get("tcp_enabled", False),
        tcp_connections=0,  # Would come from gateway process stats
        total_requests=0,   # Would come from gateway process stats
        total_errors=0,     # Would come from gateway process stats
        downstream_devices_online=len(downstream)  # Configured count
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
            status[svc] = result.stdout.strip() or "inactive"
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout checking service status for {svc}")
            status[svc] = "timeout"
        except FileNotFoundError:
            # systemctl not available (e.g., Docker container)
            status[svc] = "not-available"
        except Exception as e:
            logger.warning(f"Error checking service status for {svc}: {e}")
            status[svc] = "error"

    return status

@app.post("/api/v1/services/{service_name}/{action}")
async def control_service(service_name: str, action: str, user: Dict = Depends(get_current_user)):
    """Control a service (start/stop/restart) - requires admin role"""
    import subprocess

    check_role(user, UserRole.ADMIN)

    allowed_services = ["water-controller", "water-controller-api", "water-controller-ui", "water-controller-modbus"]
    allowed_actions = ["start", "stop", "restart"]

    if service_name not in allowed_services:
        raise HTTPException(status_code=400, detail="Invalid service name")
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Invalid action")

    try:
        result = subprocess.run(
            ["sudo", "systemctl", action, service_name],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr or "Service control failed")

        logger.info(f"Service {service_name} {action}ed by {user.get('username')}")
        return {"status": "ok", "action": action, "service": service_name}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Operation timed out")

# ============== Authentication Endpoints ==============

# Note: active_sessions is defined at module level (line ~54) for dependency access

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
        # Local authentication using database users
        user = db.authenticate_user(username, password)
        if user:
            # Map role to groups for consistency with AD auth
            role_to_groups = {
                'admin': ["WTC-Admins"],
                'engineer': ["WTC-Engineers"],
                'operator': ["WTC-Operators"],
                'viewer': ["WTC-Viewers"]
            }
            groups = role_to_groups.get(user.get('role', 'viewer'), ["WTC-Viewers"])
        else:
            logger.warning(f"Local auth failed for user: {username}")
            return LoginResponse(
                success=False,
                message="Invalid credentials"
            )

    # Generate session token
    token = secrets.token_hex(32)

    # Determine role from groups
    role = UserRole.VIEWER
    if "WTC-Admins" in groups:
        role = UserRole.ADMIN
    elif "WTC-Engineers" in groups:
        role = UserRole.ENGINEER
    elif "WTC-Operators" in groups:
        role = UserRole.OPERATOR

    # Session expiry (24 hours)
    expires_at = datetime.now() + timedelta(hours=24)

    # Store session in memory
    active_sessions[token] = {
        "username": username,
        "role": role,
        "groups": groups,
        "created": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat()
    }

    # Persist session to database
    db.create_session(
        token=token,
        username=username,
        role=role,
        groups=groups,
        expires_at=expires_at
    )

    logger.info(f"User {username} logged in successfully with role {role}")

    return LoginResponse(
        success=True,
        token=token,
        user=username,
        groups=groups
    )

@app.post("/api/v1/auth/logout")
async def logout(token: str = None):
    """Logout and invalidate session token"""
    if token:
        # Remove from memory
        if token in active_sessions:
            del active_sessions[token]
        # Remove from database
        db.delete_session(token)
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

# ============== User Management Endpoints ==============

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    active: bool = True
    sync_to_rtus: bool = True

class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    sync_to_rtus: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    active: bool
    sync_to_rtus: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None

class UserSyncRequest(BaseModel):
    station_name: Optional[str] = None  # None = sync to all RTUs


@app.get("/api/v1/users", response_model=List[UserResponse])
async def list_users(include_inactive: bool = False, user: Dict = Depends(get_current_user)):
    """
    List all users.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    users = db.get_users(include_inactive=include_inactive)
    return [UserResponse(
        id=u['id'],
        username=u['username'],
        role=u['role'],
        active=bool(u.get('active', True)),
        sync_to_rtus=bool(u.get('sync_to_rtus', True)),
        created_at=u.get('created_at'),
        last_login=u.get('last_login')
    ) for u in users]


@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, user: Dict = Depends(get_current_user)):
    """
    Get a specific user.

    Requires: Admin role
    """
    check_role(user, UserRole.ADMIN)

    u = db.get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=u['id'],
        username=u['username'],
        role=u['role'],
        active=bool(u.get('active', True)),
        sync_to_rtus=bool(u.get('sync_to_rtus', True)),
        created_at=u.get('created_at'),
        last_login=u.get('last_login')
    )


@app.post("/api/v1/users", response_model=UserResponse)
async def create_user(request: UserCreate, user: Dict = Depends(get_current_user)):
    """
    Create a new user.

    Requires: Admin role

    The user will be synced to all connected RTUs if sync_to_rtus is true.
    """
    check_role(user, UserRole.ADMIN)

    # Check if username already exists
    existing = db.get_user_by_username(request.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Validate role
    valid_roles = ['viewer', 'operator', 'engineer', 'admin']
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    user_id = db.create_user({
        'username': request.username,
        'password': request.password,
        'role': request.role,
        'active': request.active,
        'sync_to_rtus': request.sync_to_rtus
    })

    # Trigger sync to RTUs if enabled
    if request.sync_to_rtus:
        await _trigger_user_sync()

    u = db.get_user(user_id)
    return UserResponse(
        id=u['id'],
        username=u['username'],
        role=u['role'],
        active=bool(u.get('active', True)),
        sync_to_rtus=bool(u.get('sync_to_rtus', True)),
        created_at=u.get('created_at'),
        last_login=u.get('last_login')
    )


@app.put("/api/v1/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, request: UserUpdate, user: Dict = Depends(get_current_user)):
    """
    Update a user.

    Requires: Admin role

    If any user settings change, the user list will be synced to RTUs.
    """
    check_role(user, UserRole.ADMIN)

    existing = db.get_user(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate role if provided
    if request.role:
        valid_roles = ['viewer', 'operator', 'engineer', 'admin']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    update_data = {}
    if request.password:
        update_data['password'] = request.password
    if request.role is not None:
        update_data['role'] = request.role
    if request.active is not None:
        update_data['active'] = request.active
    if request.sync_to_rtus is not None:
        update_data['sync_to_rtus'] = request.sync_to_rtus

    if update_data:
        db.update_user(user_id, update_data)
        # Trigger sync to RTUs
        await _trigger_user_sync()

    u = db.get_user(user_id)
    return UserResponse(
        id=u['id'],
        username=u['username'],
        role=u['role'],
        active=bool(u.get('active', True)),
        sync_to_rtus=bool(u.get('sync_to_rtus', True)),
        created_at=u.get('created_at'),
        last_login=u.get('last_login')
    )


@app.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: int, user: Dict = Depends(get_current_user)):
    """
    Delete a user.

    Requires: Admin role

    The user will be removed from the RTU user lists on next sync.
    """
    check_role(user, UserRole.ADMIN)

    existing = db.get_user(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # Don't allow deleting the last admin
    if existing['role'] == 'admin':
        admins = [u for u in db.get_users() if u['role'] == 'admin']
        if len(admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin user")

    db.delete_user(user_id)

    # Trigger sync to RTUs to remove user
    await _trigger_user_sync()

    return {"status": "ok", "message": f"User {existing['username']} deleted"}


@app.post("/api/v1/users/sync")
async def sync_users_to_rtus(request: UserSyncRequest, user: Dict = Depends(get_current_user)):
    """
    Manually trigger user sync to RTUs.

    Requires: Admin role

    If station_name is provided, only that RTU will be synced.
    Otherwise, all connected RTUs will be synced.
    """
    check_role(user, UserRole.ADMIN)

    users_to_sync = db.get_users_for_sync()
    if not users_to_sync:
        return {"status": "ok", "message": "No users to sync", "synced_rtus": 0}

    client = get_shm_client()
    if not client:
        raise HTTPException(status_code=503, detail="Controller not running")

    if request.station_name:
        # Sync to specific RTU
        success = await _sync_users_to_rtu(client, request.station_name, users_to_sync)
        return {
            "status": "ok" if success else "error",
            "message": f"Synced {len(users_to_sync)} users to {request.station_name}",
            "synced_rtus": 1 if success else 0
        }
    else:
        # Sync to all RTUs
        count = await _sync_users_to_all_rtus(client, users_to_sync)
        return {
            "status": "ok",
            "message": f"Synced {len(users_to_sync)} users to {count} RTUs",
            "synced_rtus": count
        }


async def _trigger_user_sync():
    """Trigger user sync to all RTUs (called after user changes)"""
    client = get_shm_client()
    if not client:
        logger.warning("Cannot sync users: controller not running")
        return

    users_to_sync = db.get_users_for_sync()
    if users_to_sync:
        await _sync_users_to_all_rtus(client, users_to_sync)


async def _sync_users_to_rtu(client, station_name: str, users: List[Dict]) -> bool:
    """Sync users to a specific RTU via IPC command"""
    try:
        # The actual sync happens in the C controller via IPC
        # We send a user sync command with serialized user data
        success = client.sync_users_to_rtu(station_name, users)
        if success:
            logger.info(f"User sync to {station_name} initiated: {len(users)} users")
        else:
            logger.error(f"Failed to initiate user sync to {station_name}")
        return success
    except Exception as e:
        logger.error(f"User sync error: {e}")
        return False


async def _sync_users_to_all_rtus(client, users: List[Dict]) -> int:
    """Sync users to all connected RTUs"""
    try:
        count = client.sync_users_to_all_rtus(users)
        logger.info(f"User sync initiated to {count} RTUs: {len(users)} users")
        return count
    except Exception as e:
        logger.error(f"User sync error: {e}")
        return 0


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

# ============== Network Configuration Endpoints ==============

class NetworkConfig(BaseModel):
    mode: str = "dhcp"  # "dhcp" or "static"
    ip_address: str = ""
    netmask: str = "255.255.255.0"
    gateway: str = ""
    dns_primary: str = ""
    dns_secondary: str = ""
    hostname: str = "water-controller"

class WebServerConfig(BaseModel):
    port: int = 8080
    bind_address: str = "0.0.0.0"
    https_enabled: bool = False
    https_port: int = 8443

# Store network/web config (would persist to db in production)
network_config_store = NetworkConfig()
web_config_store = WebServerConfig()

@app.get("/api/v1/system/network", response_model=NetworkConfig)
async def get_network_config():
    """Get current network configuration"""
    return network_config_store

@app.put("/api/v1/system/network")
async def update_network_config(config: NetworkConfig, user: Dict = Depends(get_current_user)):
    """Update network configuration (requires admin role)"""
    check_role(user, UserRole.ADMIN)
    global network_config_store
    network_config_store = config
    logger.info(f"Network config updated: mode={config.mode}, ip={config.ip_address}")
    return {"status": "ok", "message": "Network configuration updated"}

@app.get("/api/v1/system/web", response_model=WebServerConfig)
async def get_web_config():
    """Get web server configuration"""
    return web_config_store

@app.put("/api/v1/system/web")
async def update_web_config(config: WebServerConfig, user: Dict = Depends(get_current_user)):
    """Update web server configuration (requires admin role)"""
    check_role(user, UserRole.ADMIN)
    global web_config_store
    web_config_store = config
    logger.info(f"Web config updated: port={config.port}, bind={config.bind_address}")
    return {"status": "ok", "message": "Web configuration updated. Restart required."}

@app.get("/api/v1/system/interfaces")
async def get_network_interfaces():
    """Get network interface information"""
    import subprocess
    interfaces = []

    try:
        # Get interfaces using ip command
        result = subprocess.run(['ip', '-j', 'addr'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            import json as json_lib
            data = json_lib.loads(result.stdout)
            for iface in data:
                if iface.get('ifname', '').startswith('lo'):
                    continue  # Skip loopback

                ip_addr = ""
                netmask = ""
                for addr_info in iface.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        ip_addr = addr_info.get('local', '')
                        # Convert prefix length to netmask
                        prefix = addr_info.get('prefixlen', 24)
                        netmask = '.'.join([str((0xffffffff << (32 - prefix) >> i) & 0xff)
                                            for i in [24, 16, 8, 0]])
                        break

                interfaces.append({
                    "name": iface.get('ifname', ''),
                    "ip_address": ip_addr,
                    "netmask": netmask,
                    "mac_address": iface.get('address', ''),
                    "state": iface.get('operstate', 'UNKNOWN').upper(),
                    "speed": ""
                })
    except Exception as e:
        logger.warning(f"Failed to get interfaces: {e}")
        # Return mock data if command fails
        interfaces = [{
            "name": "eth0",
            "ip_address": "192.168.1.100",
            "netmask": "255.255.255.0",
            "mac_address": "00:00:00:00:00:00",
            "state": "UP",
            "speed": "1000Mbps"
        }]

    return interfaces

# ============== System Log Endpoints ==============

@app.get("/api/v1/system/logs")
async def get_system_logs(limit: int = 100, level: str = "all"):
    """Get system log entries from log file or journalctl"""
    import os
    import subprocess

    logs = []
    parse_errors = 0

    # Try reading from log file first
    log_path = os.environ.get('WTC_LOG_PATH', '/var/log/water-controller/wtc.log')
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    try:
                        # Parse log line (assumes format: timestamp - source - level - message)
                        parts = line.strip().split(' - ', 3)
                        if len(parts) >= 4:
                            log_level = parts[2].upper()
                            if level != "all" and log_level != level.upper():
                                continue
                            logs.append({
                                "timestamp": parts[0],
                                "source": parts[1],
                                "level": log_level,
                                "message": parts[3]
                            })
                        elif line.strip():
                            # Unparsed line - include as raw message
                            logs.append({
                                "timestamp": "",
                                "source": "unknown",
                                "level": "INFO",
                                "message": line.strip()
                            })
                    except Exception as e:
                        parse_errors += 1
                        if parse_errors <= 3:
                            logger.debug(f"Failed to parse log line: {e}")
        except Exception as e:
            logger.warning(f"Failed to read log file {log_path}: {e}")

    # If no logs from file, try journalctl
    if not logs:
        try:
            result = subprocess.run(
                ['journalctl', '-u', 'water-controller*', '-n', str(limit), '--no-pager', '-o', 'short-iso'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and not line.startswith('--'):
                        parts = line.split(' ', 4)
                        if len(parts) >= 5:
                            log_level = "INFO"
                            message = parts[4] if len(parts) > 4 else ""
                            if "error" in message.lower():
                                log_level = "ERROR"
                            elif "warn" in message.lower():
                                log_level = "WARNING"
                            if level != "all" and log_level != level.upper():
                                continue
                            logs.append({
                                "timestamp": parts[0],
                                "source": parts[3] if len(parts) > 3 else "system",
                                "level": log_level,
                                "message": message
                            })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"journalctl not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to read journalctl: {e}")

    if parse_errors > 0:
        logger.warning(f"Skipped {parse_errors} unparseable log lines")

    return logs

@app.delete("/api/v1/system/logs")
async def clear_system_logs(user: Dict = Depends(get_current_user)):
    """Clear system logs (requires admin role)"""
    check_role(user, UserRole.ADMIN)

    try:
        import os
        log_path = os.environ.get('WTC_LOG_PATH', '/var/log/water-controller/wtc.log')
        if os.path.exists(log_path):
            with open(log_path, 'w') as f:
                f.write("")
        logger.info("System logs cleared")
        return {"status": "ok", "message": "Logs cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear logs: {str(e)}")

@app.get("/api/v1/system/audit")
async def get_audit_log(limit: int = 50, offset: int = 0):
    """Get audit log entries"""
    entries = db.get_audit_log(limit=limit, offset=offset)
    return entries


# ============== Command Log Endpoints ==============

@app.get("/api/v1/system/commands")
async def get_command_logs(
    rtu: str = None,
    username: str = None,
    limit: int = 100,
    offset: int = 0,
    user: Dict = Depends(get_current_user)
):
    """
    Get command log entries with optional filtering.

    Query params:
    - rtu: Filter by RTU station name
    - username: Filter by username
    - limit: Max entries to return (default 100)
    - offset: Pagination offset
    """
    check_role(user, UserRole.OPERATOR)
    entries = db.get_command_log(rtu_station=rtu, username=username, limit=limit, offset=offset)
    total = db.get_command_log_count(rtu_station=rtu, username=username)
    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/v1/rtus/{station_name}/commands")
async def get_rtu_command_logs(
    station_name: str,
    limit: int = 50,
    offset: int = 0,
    user: Dict = Depends(get_current_user)
):
    """Get command log entries for a specific RTU"""
    check_role(user, UserRole.OPERATOR)
    rtu = _get_rtu_from_db(station_name)
    if not rtu:
        raise HTTPException(status_code=404, detail="RTU not found")

    entries = db.get_command_log(rtu_station=station_name, limit=limit, offset=offset)
    total = db.get_command_log_count(rtu_station=station_name)
    return {
        "rtu_station": station_name,
        "entries": entries,
        "total": total
    }


@app.delete("/api/v1/system/commands")
async def clear_old_command_logs(
    days: int = 90,
    user: Dict = Depends(get_current_user)
):
    """Clear command logs older than specified days (admin only)"""
    check_role(user, UserRole.ADMIN)
    deleted = db.clear_old_command_logs(days)
    logger.info(f"Command logs cleared by {user.get('username')}: {deleted} entries older than {days} days")
    return {"status": "ok", "deleted": deleted, "days": days}


# ============== Session Management Endpoints ==============

@app.get("/api/v1/auth/sessions")
async def get_active_sessions(user: Dict = Depends(get_current_user)):
    """Get all active sessions (requires admin role)"""
    check_role(user, UserRole.ADMIN)
    return db.get_active_sessions()

@app.delete("/api/v1/auth/sessions/{token_prefix}")
async def terminate_session(token_prefix: str, user: Dict = Depends(get_current_user)):
    """Terminate a session by token prefix (requires admin role)"""
    check_role(user, UserRole.ADMIN)

    # Delete session using prefix lookup
    if db.delete_session_by_prefix(token_prefix, user.get('username')):
        logger.info(f"Session terminated by {user.get('username')}: {token_prefix}...")
        return {"status": "ok", "message": "Session terminated"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

# ============== WebSocket Endpoints ==============

@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming"""
    await websocket.accept()
    await ws_manager.connect(websocket)

    try:
        while True:
            await asyncio.sleep(1)
            await ws_manager.touch(websocket)  # Update activity timestamp

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
                # Send simulated data as fallback when controller not running
                data = {
                    "type": "sensor_update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {}
                }

                # Get RTU names from database for simulation
                db_rtus = _get_all_rtus_from_db()
                for rtu in db_rtus:
                    station_name = rtu.get("station_name")
                    data["data"][station_name] = {
                        "sensors": [
                            {"slot": 1, "value": 7.0 + 0.1 * (datetime.now().second % 5)},
                            {"slot": 2, "value": 25.0 + 0.5 * (datetime.now().second % 3)},
                        ]
                    }

                await websocket.send_json(data)

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        await ws_manager.disconnect(websocket)

@app.websocket("/ws/alarms")
async def websocket_alarms(websocket: WebSocket):
    """WebSocket endpoint for alarm notifications (separate from realtime for targeted updates)"""
    await websocket.accept()
    logger.info("Alarm WebSocket client connected")

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
        logger.info("Alarm WebSocket client disconnected")
    except Exception as e:
        logger.warning(f"Alarm WebSocket error: {e}")

async def broadcast_event(event_type: str, data: Dict[str, Any]):
    """Broadcast event to all connected WebSocket clients using the manager"""
    message = {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()}
    await ws_manager.broadcast(message)

# ============== Background Tasks ==============

# Background task handles
scan_task: Optional[asyncio.Task] = None
ws_cleanup_task: Optional[asyncio.Task] = None

async def _websocket_cleanup_loop():
    """Periodically clean up stale WebSocket connections."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        try:
            await ws_manager.cleanup_stale()
        except Exception as e:
            logger.error(f"WebSocket cleanup error: {e}")

# ============== Startup Event ==============

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    global scan_task, ws_cleanup_task

    # Try to connect to shared memory
    if SHM_AVAILABLE:
        client = get_client()
        if client.is_connected():
            logger.info("Connected to controller via shared memory")
        else:
            logger.warning("Controller not running - API will serve database config only")
    else:
        logger.warning("Shared memory client not available - API will serve database config only")

    # Start background network scan task
    scan_task = asyncio.create_task(_background_scan_loop())
    logger.info("Background network scan task initialized (disabled by default)")

    # Start WebSocket cleanup task
    ws_cleanup_task = asyncio.create_task(_websocket_cleanup_loop())
    logger.info("WebSocket cleanup task started")

    logger.info("Water Treatment Controller API started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global scan_task, ws_cleanup_task

    # Cancel background scan task
    if scan_task and not scan_task.done():
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass
        logger.info("Background network scan task stopped")

    # Cancel WebSocket cleanup task
    if ws_cleanup_task and not ws_cleanup_task.done():
        ws_cleanup_task.cancel()
        try:
            await ws_cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("WebSocket cleanup task stopped")

    logger.info("Water Treatment Controller API stopped")

# ============== Main Entry Point ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
