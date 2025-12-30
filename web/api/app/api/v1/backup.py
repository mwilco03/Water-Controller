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

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.alarm import AlarmRule
from ...models.base import get_db
from ...models.pid import PidLoop
from ...models.rtu import RTU, Control, Sensor, Slot

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

    rtus = db.query(RTU).all()
    for rtu in rtus:
        rtu_data = {
            "station_name": rtu.station_name,
            "ip_address": rtu.ip_address,
            "vendor_id": rtu.vendor_id,
            "device_id": rtu.device_id,
            "slot_count": rtu.slot_count,
            "slots": [],
            "sensors": [],
            "controls": [],
            "alarms": [],
            "pid_loops": [],
        }

        # Export slots
        slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).all()
        for slot in slots:
            rtu_data["slots"].append({
                "slot_number": slot.slot_number,
                "module_id": slot.module_id,
                "module_type": slot.module_type,
            })

        # Export sensors
        sensors = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()
        for sensor in sensors:
            rtu_data["sensors"].append({
                "tag": sensor.tag,
                "channel": sensor.channel,
                "sensor_type": sensor.sensor_type,
                "unit": sensor.unit,
                "scale_min": sensor.scale_min,
                "scale_max": sensor.scale_max,
                "eng_min": sensor.eng_min,
                "eng_max": sensor.eng_max,
            })

        # Export controls
        controls = db.query(Control).filter(Control.rtu_id == rtu.id).all()
        for control in controls:
            rtu_data["controls"].append({
                "tag": control.tag,
                "channel": control.channel,
                "control_type": control.control_type,
                "equipment_type": control.equipment_type,
                "min_value": control.min_value,
                "max_value": control.max_value,
            })

        # Export alarm rules
        alarms = db.query(AlarmRule).filter(AlarmRule.rtu_id == rtu.id).all()
        for alarm in alarms:
            rtu_data["alarms"].append({
                "tag": alarm.tag,
                "alarm_type": alarm.alarm_type,
                "priority": alarm.priority,
                "setpoint": alarm.setpoint,
                "deadband": alarm.deadband,
                "message_template": alarm.message_template,
                "enabled": alarm.enabled,
            })

        # Export PID loops
        pid_loops = db.query(PidLoop).filter(PidLoop.rtu_id == rtu.id).all()
        for loop in pid_loops:
            rtu_data["pid_loops"].append({
                "name": loop.name,
                "pv_sensor_tag": loop.pv_sensor_tag,
                "cv_control_tag": loop.cv_control_tag,
                "kp": loop.kp,
                "ki": loop.ki,
                "kd": loop.kd,
                "setpoint": loop.setpoint,
                "output_min": loop.output_min,
                "output_max": loop.output_max,
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
    except Exception as e:
        return build_success_response({
            "success": False,
            "error": f"Invalid backup file: {e!s}",
        })

    # Validate version
    version = config_data.get("version", "1.0.0")
    if not version.startswith("2."):
        return build_success_response({
            "success": False,
            "error": f"Incompatible backup version: {version}",
        })

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
            slot_count=rtu_data["slot_count"],
        )
        db.add(rtu)
        db.flush()
        restored["rtus"] += 1

        # Create slots
        for slot_data in rtu_data.get("slots", []):
            slot = Slot(
                rtu_id=rtu.id,
                slot_number=slot_data["slot_number"],
                module_id=slot_data.get("module_id"),
                module_type=slot_data.get("module_type"),
            )
            db.add(slot)

        db.flush()

        # Create sensors
        for sensor_data in rtu_data.get("sensors", []):
            # Find slot
            slot = db.query(Slot).filter(
                Slot.rtu_id == rtu.id,
                Slot.slot_number == 1  # Default to slot 1
            ).first()

            sensor = Sensor(
                rtu_id=rtu.id,
                slot_id=slot.id if slot else None,
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

        # Create controls
        for control_data in rtu_data.get("controls", []):
            slot = db.query(Slot).filter(
                Slot.rtu_id == rtu.id,
                Slot.slot_number == 1
            ).first()

            control = Control(
                rtu_id=rtu.id,
                slot_id=slot.id if slot else None,
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
                rtu_id=rtu.id,
                tag=alarm_data["tag"],
                alarm_type=alarm_data["alarm_type"],
                priority=alarm_data["priority"],
                setpoint=alarm_data["setpoint"],
                deadband=alarm_data.get("deadband", 0),
                message_template=alarm_data.get("message_template"),
                enabled=alarm_data.get("enabled", True),
            )
            db.add(alarm)
            restored["alarms"] += 1

        # Create PID loops
        for loop_data in rtu_data.get("pid_loops", []):
            loop = PidLoop(
                rtu_id=rtu.id,
                name=loop_data["name"],
                pv_sensor_tag=loop_data["pv_sensor_tag"],
                cv_control_tag=loop_data["cv_control_tag"],
                kp=loop_data["kp"],
                ki=loop_data["ki"],
                kd=loop_data["kd"],
                setpoint=loop_data["setpoint"],
                output_min=loop_data["output_min"],
                output_max=loop_data["output_max"],
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
