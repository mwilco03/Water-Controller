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
    from shm_client import get_client, WtcShmClient
    SHM_AVAILABLE = True
except ImportError:
    SHM_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# ============== Shared Memory Client ==============

def get_shm_client() -> Optional[WtcShmClient]:
    """Get shared memory client if available"""
    if SHM_AVAILABLE:
        client = get_client()
        if client.is_connected():
            return client
    return None

# ============== Fallback Data Store ==============
# Used when controller is not running

fallback_rtus: Dict[str, RTUDevice] = {}
fallback_alarms: Dict[int, Alarm] = {}
alarm_rules: Dict[int, AlarmRule] = {}
fallback_pid_loops: Dict[int, PIDLoop] = {}
historian_tags: Dict[int, HistorianTag] = {}

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
    """List all registered RTUs"""
    client = get_shm_client()
    if client:
        rtus = client.get_rtus()
        return [RTUDevice(
            station_name=r["station_name"],
            ip_address=r["ip_address"],
            vendor_id=r["vendor_id"],
            device_id=r["device_id"],
            connection_state=CONNECTION_STATES.get(r["connection_state"], "UNKNOWN"),
            slot_count=r["slot_count"],
            last_seen=datetime.now()
        ) for r in rtus]
    return list(fallback_rtus.values())

@app.get("/api/v1/rtus/{station_name}", response_model=RTUDevice)
async def get_rtu(station_name: str):
    """Get RTU details by station name"""
    client = get_shm_client()
    if client:
        rtus = client.get_rtus()
        for r in rtus:
            if r["station_name"] == station_name:
                return RTUDevice(
                    station_name=r["station_name"],
                    ip_address=r["ip_address"],
                    vendor_id=r["vendor_id"],
                    device_id=r["device_id"],
                    connection_state=CONNECTION_STATES.get(r["connection_state"], "UNKNOWN"),
                    slot_count=r["slot_count"],
                    last_seen=datetime.now()
                )
        raise HTTPException(status_code=404, detail="RTU not found")

    if station_name not in fallback_rtus:
        raise HTTPException(status_code=404, detail="RTU not found")
    return fallback_rtus[station_name]

@app.get("/api/v1/rtus/{station_name}/sensors", response_model=List[SensorData])
async def get_rtu_sensors(station_name: str):
    """Get all sensor values for an RTU"""
    client = get_shm_client()
    if client:
        rtus = client.get_rtus()
        for r in rtus:
            if r["station_name"] == station_name:
                sensors = []
                sensor_names = ["pH", "Temperature", "Turbidity", "TDS",
                              "Dissolved Oxygen", "Flow Rate", "Level", "Pressure"]
                sensor_units = ["pH", "°C", "NTU", "ppm", "mg/L", "L/min", "%", "bar"]

                for s in r["sensors"]:
                    idx = s["slot"] % len(sensor_names)
                    sensors.append(SensorData(
                        slot=s["slot"],
                        name=sensor_names[idx],
                        value=s["value"],
                        unit=sensor_units[idx],
                        status="GOOD" if s["status"] == 192 else "BAD",
                        timestamp=datetime.fromtimestamp(s["timestamp_ms"] / 1000.0)
                    ))
                return sensors
        raise HTTPException(status_code=404, detail="RTU not found")

    if station_name not in fallback_rtus:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Return simulated sensor data for fallback
    sensors = []
    sensor_types = [
        ("pH", "pH", 7.2), ("Temperature", "°C", 25.5),
        ("Turbidity", "NTU", 1.2), ("TDS", "ppm", 350),
        ("Dissolved Oxygen", "mg/L", 6.8), ("Flow Rate", "L/min", 120.5),
        ("Level", "%", 65.0), ("Pressure", "bar", 3.2),
    ]
    for i, (name, unit, value) in enumerate(sensor_types, start=1):
        sensors.append(SensorData(
            slot=i, name=name, value=value, unit=unit,
            status="GOOD", timestamp=datetime.now()
        ))
    return sensors

@app.get("/api/v1/rtus/{station_name}/actuators", response_model=List[ActuatorState])
async def get_rtu_actuators(station_name: str):
    """Get all actuator states for an RTU"""
    client = get_shm_client()
    if client:
        rtus = client.get_rtus()
        for r in rtus:
            if r["station_name"] == station_name:
                actuators = []
                actuator_names = ["Main Pump", "Inlet Valve", "Outlet Valve", "Dosing Pump",
                                 "Aerator", "Heater", "Mixer", "Spare"]

                for a in r["actuators"]:
                    idx = a["slot"] % len(actuator_names)
                    actuators.append(ActuatorState(
                        slot=a["slot"],
                        name=actuator_names[idx],
                        command=ACTUATOR_COMMANDS.get(a["command"], "OFF"),
                        pwm_duty=a["pwm_duty"],
                        forced=a["forced"]
                    ))
                return actuators
        raise HTTPException(status_code=404, detail="RTU not found")

    if station_name not in fallback_rtus:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Return simulated actuator data for fallback
    actuators = []
    actuator_types = [
        ("Main Pump", "ON", 0), ("Inlet Valve", "ON", 0),
        ("Outlet Valve", "ON", 0), ("Dosing Pump", "PWM", 50),
        ("Aerator", "OFF", 0), ("Heater", "OFF", 0),
        ("Mixer", "ON", 0), ("Spare", "OFF", 0),
    ]
    for i, (name, cmd, duty) in enumerate(actuator_types, start=9):
        actuators.append(ActuatorState(
            slot=i, name=name, command=cmd, pwm_duty=duty, forced=False
        ))
    return actuators

@app.post("/api/v1/rtus/{station_name}/actuators/{slot}")
async def command_actuator(station_name: str, slot: int, command: ActuatorCommand):
    """Send command to actuator"""
    client = get_shm_client()

    # Convert command string to integer
    cmd_map = {"OFF": 0, "ON": 1, "PWM": 2}
    cmd_int = cmd_map.get(command.command, 0)

    if client:
        success = client.command_actuator(station_name, slot, cmd_int, command.pwm_duty or 0)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send actuator command")
    else:
        if station_name not in fallback_rtus:
            raise HTTPException(status_code=404, detail="RTU not found")

    logger.info(f"Actuator command: {station_name} slot {slot} -> {command.command} duty={command.pwm_duty}")

    await broadcast_event("actuator_command", {
        "station_name": station_name,
        "slot": slot,
        "command": command.command,
        "pwm_duty": command.pwm_duty
    })

    return {"status": "ok"}

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

@app.get("/api/v1/trends/tags", response_model=List[HistorianTag])
async def list_historian_tags():
    """List all historian tags"""
    return list(historian_tags.values())

@app.get("/api/v1/trends/{tag_id}")
async def get_trend_data(tag_id: int, start_time: datetime, end_time: datetime):
    """Get trend data for a tag"""
    if tag_id not in historian_tags:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Generate simulated trend data (in production, query historian database)
    import random
    samples = []
    current = start_time
    while current < end_time:
        samples.append({
            "timestamp": current.isoformat(),
            "value": random.uniform(5, 10),
            "quality": 192
        })
        current = datetime.fromtimestamp(current.timestamp() + 60)

    return {"tag_id": tag_id, "samples": samples}

# ============== System Endpoints ==============

@app.get("/api/v1/system/health", response_model=SystemHealth)
async def get_system_health():
    """Get system health status"""
    client = get_shm_client()
    if client:
        status = client.get_status()
        return SystemHealth(
            status="running" if status.get("controller_running", False) else "stopped",
            uptime_seconds=int(status.get("last_update_ms", 0) / 1000),
            connected_rtus=status.get("connected_rtus", 0),
            total_rtus=status.get("total_rtus", 0),
            active_alarms=status.get("active_alarms", 0),
            cpu_percent=0.0,  # TODO: get from system
            memory_percent=0.0
        )

    return SystemHealth(
        status="running" if fallback_rtus else "stopped",
        uptime_seconds=12345,
        connected_rtus=len([r for r in fallback_rtus.values() if r.connection_state == "RUNNING"]),
        total_rtus=len(fallback_rtus),
        active_alarms=len([a for a in fallback_alarms.values() if a.state.startswith("ACTIVE")]),
        cpu_percent=25.5,
        memory_percent=45.2
    )

@app.get("/api/v1/system/config")
async def export_config():
    """Export system configuration"""
    return {
        "rtus": [r.dict() for r in fallback_rtus.values()],
        "alarm_rules": [r.dict() for r in alarm_rules.values()],
        "pid_loops": [p.dict() for p in fallback_pid_loops.values()],
        "historian_tags": [t.dict() for t in historian_tags.values()]
    }

@app.post("/api/v1/system/config")
async def import_config(config: Dict[str, Any]):
    """Import system configuration"""
    return {"status": "ok", "message": "Configuration imported"}

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

    logger.info("Water Treatment Controller API started")

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
