"""
Water Treatment Controller - Backup/Restore Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from ...core.errors import build_success_response
from ...models.alarm import AlarmRule
from ...models.base import get_db
from ...models.pid import PidLoop
from ...models.rtu import RTU, Control, Sensor

router = APIRouter()


class BackupInfo(BaseModel):
    """Backup metadata."""

    id: str = Field(description="Backup identifier")
    created_at: datetime = Field(description="Creation timestamp")
    version: str = Field(description="Backup version")
    rtus: int = Field(description="Number of RTUs")
    sensors: int = Field(description="Number of sensors")
    controls: int = Field(description="Number of controls")
    alarms: int = Field(description="Number of alarm rules")
    pid_loops: int = Field(description="Number of PID loops")


@router.post("")
async def create_backup(
    db: Session = Depends(get_db)
):
    """
    Create a configuration backup.

    Returns a downloadable ZIP file containing all configuration.
    """
    now = datetime.now(UTC)
    backup_id = now.strftime("%Y%m%d_%H%M%S")

    # Collect all configuration
    backup_data = {
        "version": "2.0.0",
        "created_at": now.isoformat(),
        "backup_id": backup_id,
        "rtus": [],
    }

    # Use eager loading to fetch all related data in minimal queries
    rtus = db.query(RTU).options(
        joinedload(RTU.sensors),
        joinedload(RTU.controls),
    ).all()

    # Fetch alarm rules and PID loops separately (not defined as relationships)
    # AlarmRule uses rtu_station (string), not rtu_id (FK)
    all_alarms = db.query(AlarmRule).all()
    alarms_by_rtu = {}
    for alarm in all_alarms:
        alarms_by_rtu.setdefault(alarm.rtu_station, []).append(alarm)

    # PidLoop has input_rtu and output_rtu, group by input_rtu for export
    all_pid_loops = db.query(PidLoop).all()
    pid_loops_by_rtu = {}
    for loop in all_pid_loops:
        pid_loops_by_rtu.setdefault(loop.input_rtu, []).append(loop)

    for rtu in rtus:
        rtu_data = {
            "station_name": rtu.station_name,
            "ip_address": rtu.ip_address,
            "vendor_id": rtu.vendor_id,
            "device_id": rtu.device_id,
            "slot_count": rtu.slot_count or 0,
            "sensors": [],
            "controls": [],
            "alarms": [],
            "pid_loops": [],
        }

        # Export sensors (slot_number is metadata on sensor, not a separate table)
        for sensor in rtu.sensors:
            rtu_data["sensors"].append({
                "tag": sensor.tag,
                "slot_number": sensor.slot_number,
                "channel": sensor.channel,
                "sensor_type": sensor.sensor_type,
                "unit": sensor.unit,
                "scale_min": sensor.scale_min,
                "scale_max": sensor.scale_max,
                "eng_min": sensor.eng_min,
                "eng_max": sensor.eng_max,
            })

        # Export controls (slot_number is metadata on control, not a separate table)
        for control in rtu.controls:
            rtu_data["controls"].append({
                "tag": control.tag,
                "slot_number": control.slot_number,
                "channel": control.channel,
                "control_type": control.control_type,
                "equipment_type": control.equipment_type,
                "min_value": control.min_value,
                "max_value": control.max_value,
            })

        # Export alarm rules (from pre-fetched dict, keyed by rtu_station)
        for alarm in alarms_by_rtu.get(rtu.station_name, []):
            rtu_data["alarms"].append({
                "name": alarm.name,
                "slot": alarm.slot,
                "condition": alarm.condition,
                "threshold": alarm.threshold,
                "severity": alarm.severity,
                "delay_ms": alarm.delay_ms,
                "message": alarm.message,
                "enabled": alarm.enabled,
            })

        # Export PID loops (from pre-fetched dict, keyed by input_rtu)
        for loop in pid_loops_by_rtu.get(rtu.station_name, []):
            rtu_data["pid_loops"].append({
                "name": loop.name,
                "input_rtu": loop.input_rtu,
                "input_slot": loop.input_slot,
                "output_rtu": loop.output_rtu,
                "output_slot": loop.output_slot,
                "kp": loop.kp,
                "ki": loop.ki,
                "kd": loop.kd,
                "setpoint": loop.setpoint,
                "output_min": loop.output_min,
                "output_max": loop.output_max,
                "deadband": loop.deadband,
                "integral_limit": loop.integral_limit,
                "derivative_filter": loop.derivative_filter,
                "mode": loop.mode,
                "enabled": loop.enabled,
            })

        backup_data["rtus"].append(rtu_data)

    # Create ZIP file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add main configuration
        zf.writestr("config.json", json.dumps(backup_data, indent=2))

        # Add metadata
        metadata = BackupInfo(
            id=backup_id,
            created_at=now,
            version="2.0.0",
            rtus=len(backup_data["rtus"]),
            sensors=sum(len(r["sensors"]) for r in backup_data["rtus"]),
            controls=sum(len(r["controls"]) for r in backup_data["rtus"]),
            alarms=sum(len(r["alarms"]) for r in backup_data["rtus"]),
            pid_loops=sum(len(r["pid_loops"]) for r in backup_data["rtus"]),
        )
        zf.writestr("metadata.json", metadata.model_dump_json(indent=2))

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=wtc_backup_{backup_id}.zip"
        }
    )


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    merge: bool = False,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Restore configuration from backup.

    If merge=False (default), existing configuration is replaced.
    If merge=True, new items are added without deleting existing.
    """
    contents = await file.read()

    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            config_data = json.loads(zf.read("config.json"))
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail=f"Invalid backup file: not a valid zip archive - {e}")
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid backup file: missing config.json")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid backup file: malformed config.json - {e}")

    # Validate version
    version = config_data.get("version", "1.0.0")
    if not version.startswith("2."):
        raise HTTPException(
            status_code=400,
            detail=f"Incompatible backup version: {version}. Expected version 2.x"
        )

    restored = {
        "rtus": 0,
        "sensors": 0,
        "controls": 0,
        "alarms": 0,
        "pid_loops": 0,
    }

    for rtu_data in config_data.get("rtus", []):
        station_name = rtu_data["station_name"]

        # Check if RTU exists
        existing = db.query(RTU).filter(RTU.station_name == station_name).first()

        if existing:
            if merge:
                # Skip existing RTUs in merge mode
                continue
            else:
                # Delete existing RTU
                db.delete(existing)
                db.flush()

        # Create RTU
        rtu = RTU(
            station_name=station_name,
            ip_address=rtu_data["ip_address"],
            vendor_id=rtu_data["vendor_id"],
            device_id=rtu_data["device_id"],
            slot_count=rtu_data.get("slot_count"),
        )
        db.add(rtu)
        db.flush()
        restored["rtus"] += 1

        # Create sensors (slot_number is metadata, not FK)
        for sensor_data in rtu_data.get("sensors", []):
            sensor = Sensor(
                rtu_id=rtu.id,
                slot_number=sensor_data.get("slot_number"),
                tag=sensor_data["tag"],
                channel=sensor_data["channel"],
                sensor_type=sensor_data["sensor_type"],
                unit=sensor_data.get("unit"),
                scale_min=sensor_data.get("scale_min", 0),
                scale_max=sensor_data.get("scale_max", 100),
                eng_min=sensor_data.get("eng_min", 0),
                eng_max=sensor_data.get("eng_max", 100),
            )
            db.add(sensor)
            restored["sensors"] += 1

        # Create controls (slot_number is metadata, not FK)
        for control_data in rtu_data.get("controls", []):
            control = Control(
                rtu_id=rtu.id,
                slot_number=control_data.get("slot_number"),
                tag=control_data["tag"],
                channel=control_data["channel"],
                control_type=control_data["control_type"],
                equipment_type=control_data.get("equipment_type"),
                min_value=control_data.get("min_value"),
                max_value=control_data.get("max_value"),
            )
            db.add(control)
            restored["controls"] += 1

        # Create alarm rules
        for alarm_data in rtu_data.get("alarms", []):
            alarm = AlarmRule(
                rtu_station=station_name,
                name=alarm_data["name"],
                slot=alarm_data["slot"],
                condition=alarm_data["condition"],
                threshold=alarm_data["threshold"],
                severity=alarm_data["severity"],
                delay_ms=alarm_data.get("delay_ms", 0),
                message=alarm_data.get("message"),
                enabled=alarm_data.get("enabled", True),
            )
            db.add(alarm)
            restored["alarms"] += 1

        # Create PID loops
        for loop_data in rtu_data.get("pid_loops", []):
            loop = PidLoop(
                name=loop_data["name"],
                input_rtu=loop_data.get("input_rtu", station_name),
                input_slot=loop_data["input_slot"],
                output_rtu=loop_data.get("output_rtu", station_name),
                output_slot=loop_data["output_slot"],
                kp=loop_data["kp"],
                ki=loop_data["ki"],
                kd=loop_data["kd"],
                setpoint=loop_data["setpoint"],
                output_min=loop_data["output_min"],
                output_max=loop_data["output_max"],
                deadband=loop_data.get("deadband", 0),
                integral_limit=loop_data.get("integral_limit", 100),
                derivative_filter=loop_data.get("derivative_filter", 0.1),
                mode=loop_data["mode"],
                enabled=loop_data.get("enabled", True),
            )
            db.add(loop)
            restored["pid_loops"] += 1

    db.commit()

    return build_success_response({
        "success": True,
        "restored": restored,
        "backup_id": config_data.get("backup_id"),
        "backup_date": config_data.get("created_at"),
    })
