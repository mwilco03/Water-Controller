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

# ============== Simulated Data Store ==============
# In production, this would connect to the C controller via shared memory or sockets

rtus: Dict[str, RTUDevice] = {}
alarms: Dict[int, Alarm] = {}
alarm_rules: Dict[int, AlarmRule] = {}
pid_loops: Dict[int, PIDLoop] = {}
historian_tags: Dict[int, HistorianTag] = {}

# WebSocket connections
websocket_connections: List[WebSocket] = []

# ============== RTU Endpoints ==============

@app.get("/api/v1/rtus", response_model=List[RTUDevice])
async def list_rtus():
    """List all registered RTUs"""
    return list(rtus.values())

@app.get("/api/v1/rtus/{station_name}", response_model=RTUDevice)
async def get_rtu(station_name: str):
    """Get RTU details by station name"""
    if station_name not in rtus:
        raise HTTPException(status_code=404, detail="RTU not found")
    return rtus[station_name]

@app.get("/api/v1/rtus/{station_name}/sensors", response_model=List[SensorData])
async def get_rtu_sensors(station_name: str):
    """Get all sensor values for an RTU"""
    if station_name not in rtus:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Simulated sensor data
    sensors = []
    sensor_types = [
        ("pH", "pH", 7.2),
        ("Temperature", "°C", 25.5),
        ("Turbidity", "NTU", 1.2),
        ("TDS", "ppm", 350),
        ("Dissolved Oxygen", "mg/L", 6.8),
        ("Flow Rate", "L/min", 120.5),
        ("Level", "%", 65.0),
        ("Pressure", "bar", 3.2),
    ]

    for i, (name, unit, value) in enumerate(sensor_types, start=1):
        sensors.append(SensorData(
            slot=i,
            name=name,
            value=value,
            unit=unit,
            status="GOOD",
            timestamp=datetime.now()
        ))

    return sensors

@app.get("/api/v1/rtus/{station_name}/actuators", response_model=List[ActuatorState])
async def get_rtu_actuators(station_name: str):
    """Get all actuator states for an RTU"""
    if station_name not in rtus:
        raise HTTPException(status_code=404, detail="RTU not found")

    # Simulated actuator data
    actuators = []
    actuator_types = [
        ("Main Pump", "ON", 0),
        ("Inlet Valve", "ON", 0),
        ("Outlet Valve", "ON", 0),
        ("Dosing Pump", "PWM", 50),
        ("Aerator", "OFF", 0),
        ("Heater", "OFF", 0),
        ("Mixer", "ON", 0),
        ("Spare", "OFF", 0),
    ]

    for i, (name, cmd, duty) in enumerate(actuator_types, start=9):
        actuators.append(ActuatorState(
            slot=i,
            name=name,
            command=cmd,
            pwm_duty=duty,
            forced=False
        ))

    return actuators

@app.post("/api/v1/rtus/{station_name}/actuators/{slot}")
async def command_actuator(station_name: str, slot: int, command: ActuatorCommand):
    """Send command to actuator"""
    if station_name not in rtus:
        raise HTTPException(status_code=404, detail="RTU not found")

    if slot < 9 or slot > 16:
        raise HTTPException(status_code=400, detail="Invalid actuator slot")

    logger.info(f"Actuator command: {station_name} slot {slot} -> {command.command} duty={command.pwm_duty}")

    # Broadcast to WebSocket clients
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
    active = [a for a in alarms.values() if a.state in ["ACTIVE_UNACK", "ACTIVE_ACK"]]
    return active

@app.get("/api/v1/alarms/history", response_model=List[Alarm])
async def get_alarm_history(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100
):
    """Get alarm history"""
    return list(alarms.values())[:limit]

@app.post("/api/v1/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(alarm_id: int, request: AcknowledgeRequest):
    """Acknowledge an alarm"""
    if alarm_id not in alarms:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm = alarms[alarm_id]
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
    return list(pid_loops.values())

@app.get("/api/v1/control/pid/{loop_id}", response_model=PIDLoop)
async def get_pid_loop(loop_id: int):
    """Get PID loop details"""
    if loop_id not in pid_loops:
        raise HTTPException(status_code=404, detail="PID loop not found")
    return pid_loops[loop_id]

@app.put("/api/v1/control/pid/{loop_id}/setpoint")
async def update_pid_setpoint(loop_id: int, update: SetpointUpdate):
    """Update PID loop setpoint"""
    if loop_id not in pid_loops:
        raise HTTPException(status_code=404, detail="PID loop not found")

    pid_loops[loop_id].setpoint = update.setpoint
    logger.info(f"PID loop {loop_id} setpoint changed to {update.setpoint}")

    return {"status": "ok"}

@app.put("/api/v1/control/pid/{loop_id}/tuning")
async def update_pid_tuning(loop_id: int, tuning: TuningUpdate):
    """Update PID loop tuning parameters"""
    if loop_id not in pid_loops:
        raise HTTPException(status_code=404, detail="PID loop not found")

    pid_loops[loop_id].kp = tuning.kp
    pid_loops[loop_id].ki = tuning.ki
    pid_loops[loop_id].kd = tuning.kd

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

    # Generate simulated trend data
    import random
    samples = []
    current = start_time
    while current < end_time:
        samples.append({
            "timestamp": current.isoformat(),
            "value": random.uniform(5, 10),
            "quality": 192
        })
        current = datetime.fromtimestamp(current.timestamp() + 60)  # 1 minute intervals

    return {"tag_id": tag_id, "samples": samples}

# ============== System Endpoints ==============

@app.get("/api/v1/system/health", response_model=SystemHealth)
async def get_system_health():
    """Get system health status"""
    return SystemHealth(
        status="running",
        uptime_seconds=12345,
        connected_rtus=len([r for r in rtus.values() if r.connection_state == "RUNNING"]),
        total_rtus=len(rtus),
        active_alarms=len([a for a in alarms.values() if a.state.startswith("ACTIVE")]),
        cpu_percent=25.5,
        memory_percent=45.2
    )

@app.get("/api/v1/system/config")
async def export_config():
    """Export system configuration"""
    return {
        "rtus": [r.dict() for r in rtus.values()],
        "alarm_rules": [r.dict() for r in alarm_rules.values()],
        "pid_loops": [p.dict() for p in pid_loops.values()],
        "historian_tags": [t.dict() for t in historian_tags.values()]
    }

@app.post("/api/v1/system/config")
async def import_config(config: Dict[str, Any]):
    """Import system configuration"""
    # Configuration import logic would go here
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
            # Send periodic updates
            await asyncio.sleep(1)

            # Send simulated real-time data
            data = {
                "type": "sensor_update",
                "timestamp": datetime.now().isoformat(),
                "data": {}
            }

            for station_name in rtus:
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
        while True:
            # Wait for alarm events
            await asyncio.sleep(5)

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
    """Initialize sample data on startup"""
    # Add sample RTU
    rtus["rtu-tank-1"] = RTUDevice(
        station_name="rtu-tank-1",
        ip_address="192.168.1.100",
        vendor_id=0x0001,
        device_id=0x0001,
        connection_state="RUNNING",
        slot_count=16,
        last_seen=datetime.now()
    )

    rtus["rtu-pump-station"] = RTUDevice(
        station_name="rtu-pump-station",
        ip_address="192.168.1.101",
        vendor_id=0x0001,
        device_id=0x0001,
        connection_state="RUNNING",
        slot_count=16,
        last_seen=datetime.now()
    )

    # Add sample PID loop
    pid_loops[1] = PIDLoop(
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

    # Add sample historian tag
    historian_tags[1] = HistorianTag(
        tag_id=1,
        rtu_station="rtu-tank-1",
        slot=1,
        tag_name="rtu-tank-1.pH",
        sample_rate_ms=1000,
        deadband=0.05,
        compression="SWINGING_DOOR"
    )

    logger.info("Water Treatment Controller API started")

# ============== Main Entry Point ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
