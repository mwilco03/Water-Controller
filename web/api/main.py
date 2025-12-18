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
    global fallback_rtus, alarm_rules, fallback_pid_loops, historian_tags

    try:
        # Import RTUs
        if "rtus" in config:
            for rtu_data in config["rtus"]:
                rtu = RTUDevice(**rtu_data)
                fallback_rtus[rtu.station_name] = rtu

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
