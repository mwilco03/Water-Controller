"""
Water Treatment Controller - Configuration Template Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.exceptions import RtuNotFoundError, ValidationError
from ...models.alarm import AlarmRule
from ...models.base import get_db
from ...models.pid import PidLoop
from ...models.rtu import RTU, Control, Sensor, Slot
from ...models.template import ConfigTemplate
from ...schemas.template import (
    TemplateCreate,
    TemplateResponse,
)

router = APIRouter()


def template_not_found(template_id: int):
    """Raise 404 for template not found."""
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "TEMPLATE_NOT_FOUND",
                "message": f"Template {template_id} not found",
            }
        }
    )


@router.get("")
async def list_templates(
    category: str | None = None,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List all configuration templates.
    """
    query = db.query(ConfigTemplate)
    if category:
        query = query.filter(ConfigTemplate.category == category)

    templates = query.order_by(ConfigTemplate.name).all()

    result = []
    for tpl in templates:
        config = tpl.config_data or {}
        result.append(TemplateResponse(
            id=tpl.id,
            name=tpl.name,
            description=tpl.description,
            category=tpl.category,
            vendor_id=tpl.vendor_id,
            device_id=tpl.device_id,
            slot_count=tpl.slot_count,
            slots=config.get("slots", []),
            sensors=config.get("sensors", []),
            controls=config.get("controls", []),
            alarms=config.get("alarms", []),
            pid_loops=config.get("pid_loops", []),
            created_at=tpl.created_at,
            updated_at=tpl.updated_at,
        ).model_dump())

    return build_success_response(result)


@router.post("", status_code=201)
async def create_template(
    request: TemplateCreate,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Create a new configuration template.
    """
    # Check for duplicate name
    existing = db.query(ConfigTemplate).filter(
        ConfigTemplate.name == request.name
    ).first()
    if existing:
        raise ValidationError(
            f"Template with name '{request.name}' already exists",
            details={"field": "name"}
        )

    # Build config data
    config_data = {
        "slots": [s.model_dump() for s in request.slots],
        "sensors": [s.model_dump() for s in request.sensors],
        "controls": [c.model_dump() for c in request.controls],
        "alarms": [a.model_dump() for a in request.alarms],
        "pid_loops": [p.model_dump() for p in request.pid_loops],
    }

    template = ConfigTemplate(
        name=request.name,
        description=request.description,
        category=request.category,
        vendor_id=request.vendor_id,
        device_id=request.device_id,
        slot_count=request.slot_count,
        config_data=config_data,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    return build_success_response(TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        vendor_id=template.vendor_id,
        device_id=template.device_id,
        slot_count=template.slot_count,
        slots=config_data["slots"],
        sensors=config_data["sensors"],
        controls=config_data["controls"],
        alarms=config_data["alarms"],
        pid_loops=config_data["pid_loops"],
        created_at=template.created_at,
        updated_at=template.updated_at,
    ).model_dump())


@router.get("/{template_id}")
async def get_template(
    template_id: int = Path(..., description="Template ID"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get a specific template.
    """
    template = db.query(ConfigTemplate).filter(
        ConfigTemplate.id == template_id
    ).first()
    if not template:
        template_not_found(template_id)

    config = template.config_data or {}

    return build_success_response(TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        vendor_id=template.vendor_id,
        device_id=template.device_id,
        slot_count=template.slot_count,
        slots=config.get("slots", []),
        sensors=config.get("sensors", []),
        controls=config.get("controls", []),
        alarms=config.get("alarms", []),
        pid_loops=config.get("pid_loops", []),
        created_at=template.created_at,
        updated_at=template.updated_at,
    ).model_dump())


@router.delete("/{template_id}")
async def delete_template(
    template_id: int = Path(..., description="Template ID"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Delete a template.
    """
    template = db.query(ConfigTemplate).filter(
        ConfigTemplate.id == template_id
    ).first()
    if not template:
        template_not_found(template_id)

    db.delete(template)
    db.commit()

    return build_success_response({"id": template_id, "deleted": True})


@router.post("/{template_id}/apply/{rtu_name}")
async def apply_template(
    template_id: int = Path(..., description="Template ID"),
    rtu_name: str = Path(..., description="RTU station name"),
    overwrite: bool = False,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Apply a template to an RTU.

    If overwrite=True, existing configuration is replaced.
    Otherwise, only new items are added.
    """
    # Get template
    template = db.query(ConfigTemplate).filter(
        ConfigTemplate.id == template_id
    ).first()
    if not template:
        template_not_found(template_id)

    # Get RTU
    rtu = db.query(RTU).filter(RTU.station_name == rtu_name).first()
    if not rtu:
        raise RtuNotFoundError(rtu_name)

    config = template.config_data or {}
    applied = {
        "slots": 0,
        "sensors": 0,
        "controls": 0,
        "alarms": 0,
        "pid_loops": 0,
    }

    # Pre-fetch all existing items to avoid N+1 queries
    existing_slots = {s.slot_number: s for s in db.query(Slot).filter(Slot.rtu_id == rtu.id).all()}
    existing_sensors = {s.tag: s for s in db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()}
    existing_controls = {c.tag: c for c in db.query(Control).filter(Control.rtu_id == rtu.id).all()}
    existing_alarms = {
        (a.tag, a.alarm_type): a
        for a in db.query(AlarmRule).filter(AlarmRule.rtu_id == rtu.id).all()
    }
    existing_pids = {p.name: p for p in db.query(PidLoop).filter(PidLoop.rtu_id == rtu.id).all()}

    # Apply slots
    for slot_data in config.get("slots", []):
        existing = existing_slots.get(slot_data["slot_number"])

        if existing:
            if overwrite:
                existing.module_type = slot_data.get("module_type")
                existing.module_id = slot_data.get("module_id")
                applied["slots"] += 1
        else:
            slot = Slot(
                rtu_id=rtu.id,
                slot_number=slot_data["slot_number"],
                module_type=slot_data.get("module_type"),
                module_id=slot_data.get("module_id"),
            )
            db.add(slot)
            existing_slots[slot_data["slot_number"]] = slot
            applied["slots"] += 1

    db.flush()

    # Refresh slot lookup after flush to get IDs for new slots
    slot_by_number = {s.slot_number: s for s in db.query(Slot).filter(Slot.rtu_id == rtu.id).all()}

    # Apply sensors
    for sensor_data in config.get("sensors", []):
        existing = existing_sensors.get(sensor_data["tag"])

        if existing and not overwrite:
            continue

        slot = slot_by_number.get(sensor_data["slot_number"])

        if existing:
            existing.slot_id = slot.id if slot else None
            existing.channel = sensor_data["channel"]
            existing.sensor_type = sensor_data["sensor_type"]
            existing.unit = sensor_data.get("unit")
            existing.scale_min = sensor_data.get("scale_min", 0)
            existing.scale_max = sensor_data.get("scale_max", 4095)
            existing.eng_min = sensor_data.get("eng_min", 0)
            existing.eng_max = sensor_data.get("eng_max", 100)
        else:
            sensor = Sensor(
                rtu_id=rtu.id,
                slot_id=slot.id if slot else None,
                tag=sensor_data["tag"],
                channel=sensor_data["channel"],
                sensor_type=sensor_data["sensor_type"],
                unit=sensor_data.get("unit"),
                scale_min=sensor_data.get("scale_min", 0),
                scale_max=sensor_data.get("scale_max", 4095),
                eng_min=sensor_data.get("eng_min", 0),
                eng_max=sensor_data.get("eng_max", 100),
            )
            db.add(sensor)
        applied["sensors"] += 1

    # Apply controls
    for control_data in config.get("controls", []):
        existing = existing_controls.get(control_data["tag"])

        if existing and not overwrite:
            continue

        slot = slot_by_number.get(control_data["slot_number"])

        if existing:
            existing.slot_id = slot.id if slot else None
            existing.channel = control_data["channel"]
            existing.control_type = control_data["control_type"]
            existing.equipment_type = control_data.get("equipment_type")
            existing.min_value = control_data.get("min_value")
            existing.max_value = control_data.get("max_value")
        else:
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
        applied["controls"] += 1

    # Apply alarms
    for alarm_data in config.get("alarms", []):
        existing = existing_alarms.get((alarm_data["tag"], alarm_data["alarm_type"]))

        if existing and not overwrite:
            continue

        if existing:
            existing.priority = alarm_data.get("priority", "MEDIUM")
            existing.setpoint = alarm_data["setpoint"]
            existing.deadband = alarm_data.get("deadband", 0)
            existing.message_template = alarm_data.get("message_template")
        else:
            alarm = AlarmRule(
                rtu_id=rtu.id,
                tag=alarm_data["tag"],
                alarm_type=alarm_data["alarm_type"],
                priority=alarm_data.get("priority", "MEDIUM"),
                setpoint=alarm_data["setpoint"],
                deadband=alarm_data.get("deadband", 0),
                message_template=alarm_data.get("message_template"),
                enabled=True,
            )
            db.add(alarm)
        applied["alarms"] += 1

    # Apply PID loops
    for pid_data in config.get("pid_loops", []):
        existing = existing_pids.get(pid_data["name"])

        if existing and not overwrite:
            continue

        if existing:
            existing.pv_sensor_tag = pid_data["pv_sensor_tag"]
            existing.cv_control_tag = pid_data["cv_control_tag"]
            existing.kp = pid_data.get("kp", 1.0)
            existing.ki = pid_data.get("ki", 0.0)
            existing.kd = pid_data.get("kd", 0.0)
            existing.setpoint = pid_data["setpoint"]
            existing.output_min = pid_data.get("output_min", 0.0)
            existing.output_max = pid_data.get("output_max", 100.0)
        else:
            pid = PidLoop(
                rtu_id=rtu.id,
                name=pid_data["name"],
                pv_sensor_tag=pid_data["pv_sensor_tag"],
                cv_control_tag=pid_data["cv_control_tag"],
                kp=pid_data.get("kp", 1.0),
                ki=pid_data.get("ki", 0.0),
                kd=pid_data.get("kd", 0.0),
                setpoint=pid_data["setpoint"],
                output_min=pid_data.get("output_min", 0.0),
                output_max=pid_data.get("output_max", 100.0),
                mode="AUTO",
                enabled=True,
            )
            db.add(pid)
        applied["pid_loops"] += 1

    db.commit()

    return build_success_response({
        "template_id": template_id,
        "rtu": rtu_name,
        "applied": applied,
        "overwrite": overwrite,
    })


@router.post("/from-rtu/{rtu_name}")
async def create_template_from_rtu(
    rtu_name: str = Path(..., description="RTU station name"),
    name: str | None = None,
    description: str | None = None,
    category: str = "custom",
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Create a template from an existing RTU configuration.
    """
    # Get RTU
    rtu = db.query(RTU).filter(RTU.station_name == rtu_name).first()
    if not rtu:
        raise RtuNotFoundError(rtu_name)

    template_name = name or f"Template from {rtu_name}"

    # Check for duplicate name
    existing = db.query(ConfigTemplate).filter(
        ConfigTemplate.name == template_name
    ).first()
    if existing:
        raise ValidationError(
            f"Template with name '{template_name}' already exists",
            details={"field": "name"}
        )

    # Extract configuration - pre-fetch all related data to avoid N+1 queries
    all_slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).all()
    all_sensors = db.query(Sensor).filter(Sensor.rtu_id == rtu.id).all()
    all_controls = db.query(Control).filter(Control.rtu_id == rtu.id).all()

    # Build slot lookup dict for O(1) access
    slot_by_id = {slot.id: slot for slot in all_slots}

    slots = []
    for slot in all_slots:
        slots.append({
            "slot_number": slot.slot_number,
            "module_type": slot.module_type,
            "module_id": slot.module_id,
        })

    sensors = []
    for sensor in all_sensors:
        slot = slot_by_id.get(sensor.slot_id)
        sensors.append({
            "tag": sensor.tag,
            "slot_number": slot.slot_number if slot else 0,
            "channel": sensor.channel,
            "sensor_type": sensor.sensor_type,
            "unit": sensor.unit,
            "scale_min": sensor.scale_min,
            "scale_max": sensor.scale_max,
            "eng_min": sensor.eng_min,
            "eng_max": sensor.eng_max,
        })

    controls = []
    for control in all_controls:
        slot = slot_by_id.get(control.slot_id)
        controls.append({
            "tag": control.tag,
            "slot_number": slot.slot_number if slot else 0,
            "channel": control.channel,
            "control_type": control.control_type,
            "equipment_type": control.equipment_type,
            "min_value": control.min_value,
            "max_value": control.max_value,
        })

    alarms = []
    for alarm in db.query(AlarmRule).filter(AlarmRule.rtu_id == rtu.id).all():
        alarms.append({
            "tag": alarm.tag,
            "alarm_type": alarm.alarm_type,
            "priority": alarm.priority,
            "setpoint": alarm.setpoint,
            "deadband": alarm.deadband,
            "message_template": alarm.message_template,
        })

    pid_loops = []
    for pid in db.query(PidLoop).filter(PidLoop.rtu_id == rtu.id).all():
        pid_loops.append({
            "name": pid.name,
            "pv_sensor_tag": pid.pv_sensor_tag,
            "cv_control_tag": pid.cv_control_tag,
            "kp": pid.kp,
            "ki": pid.ki,
            "kd": pid.kd,
            "setpoint": pid.setpoint,
            "output_min": pid.output_min,
            "output_max": pid.output_max,
        })

    config_data = {
        "slots": slots,
        "sensors": sensors,
        "controls": controls,
        "alarms": alarms,
        "pid_loops": pid_loops,
    }

    template = ConfigTemplate(
        name=template_name,
        description=description or f"Configuration captured from {rtu_name}",
        category=category,
        vendor_id=rtu.vendor_id,
        device_id=rtu.device_id,
        slot_count=rtu.slot_count,
        config_data=config_data,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    return build_success_response(TemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        vendor_id=template.vendor_id,
        device_id=template.device_id,
        slot_count=template.slot_count,
        slots=slots,
        sensors=sensors,
        controls=controls,
        alarms=alarms,
        pid_loops=pid_loops,
        created_at=template.created_at,
        updated_at=template.updated_at,
    ).model_dump())
