"""
Water Treatment Controller - Slot Configuration Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from ...core.exceptions import (
    RtuNotFoundError,
    SlotNotFoundError,
    ValidationError,
)
from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU, Slot, Sensor, Control, SlotStatus
from ...schemas.slot import (
    SlotConfig,
    SlotSensorSummary,
    SlotResponse,
    SlotConfigUpdate,
)

router = APIRouter()


def get_rtu_or_404(db: Session, name: str) -> RTU:
    """Get RTU by station name or raise 404."""
    rtu = db.query(RTU).filter(RTU.station_name == name).first()
    if not rtu:
        raise RtuNotFoundError(name)
    return rtu


def get_slot_or_404(db: Session, rtu: RTU, slot_number: int) -> Slot:
    """Get slot by number or raise 404."""
    slot = db.query(Slot).filter(
        Slot.rtu_id == rtu.id,
        Slot.slot_number == slot_number
    ).first()
    if not slot:
        raise SlotNotFoundError(rtu.station_name, slot_number, rtu.slot_count)
    return slot


@router.get("")
async def list_slots(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    List all slots for an RTU.
    """
    rtu = get_rtu_or_404(db, name)

    slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).order_by(Slot.slot_number).all()

    result = []
    for slot in slots:
        # Get sensors for this slot
        sensors = db.query(Sensor).filter(Sensor.slot_id == slot.id).all()
        sensor_summaries = [
            SlotSensorSummary(
                id=s.id,
                tag=s.tag,
                type=s.sensor_type,
            ).model_dump()
            for s in sensors
        ]

        # Get controls for this slot
        controls = db.query(Control).filter(Control.slot_id == slot.id).all()
        control_list = [
            {"id": c.id, "tag": c.tag, "type": c.equipment_type}
            for c in controls
        ]

        slot_config = SlotConfig(
            slot=slot.slot_number,
            module_id=slot.module_id,
            module_type=slot.module_type,
            status=slot.status or SlotStatus.EMPTY,
            configured=slot.module_type is not None,
            sensors=sensor_summaries,
            controls=control_list,
        )
        result.append(slot_config.model_dump())

    return build_success_response(result)


@router.put("/{slot}")
async def configure_slot(
    name: str = Path(..., description="RTU station name"),
    slot: int = Path(..., ge=1, description="Slot number"),
    config: SlotConfigUpdate = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Configure a slot (module type, sensor mappings).
    """
    rtu = get_rtu_or_404(db, name)
    slot_obj = get_slot_or_404(db, rtu, slot)

    # Update slot configuration
    slot_obj.module_type = config.module_type
    slot_obj.status = SlotStatus.OK
    slot_obj.updated_at = datetime.now(timezone.utc)

    # Clear existing sensors and controls for this slot
    db.query(Sensor).filter(Sensor.slot_id == slot_obj.id).delete()
    db.query(Control).filter(Control.slot_id == slot_obj.id).delete()

    # Add new sensors
    for sensor_config in config.sensors:
        # Check for duplicate tag
        existing_tag = db.query(Sensor).filter(Sensor.tag == sensor_config.tag).first()
        if existing_tag:
            raise ValidationError(
                f"Tag '{sensor_config.tag}' already in use",
                details={"field": "sensors.tag", "value": sensor_config.tag}
            )

        sensor = Sensor(
            rtu_id=rtu.id,
            slot_id=slot_obj.id,
            tag=sensor_config.tag,
            channel=sensor_config.channel,
            sensor_type=sensor_config.type,
            unit=sensor_config.unit,
            scale_min=sensor_config.scale_min,
            scale_max=sensor_config.scale_max,
            eng_min=sensor_config.eng_min,
            eng_max=sensor_config.eng_max,
        )
        db.add(sensor)

    # Add new controls
    for control_config in config.controls:
        # Check for duplicate tag
        existing_tag = db.query(Control).filter(Control.tag == control_config.tag).first()
        if existing_tag:
            raise ValidationError(
                f"Tag '{control_config.tag}' already in use",
                details={"field": "controls.tag", "value": control_config.tag}
            )

        control = Control(
            rtu_id=rtu.id,
            slot_id=slot_obj.id,
            tag=control_config.tag,
            channel=control_config.channel,
            control_type=control_config.control_type.value,
            equipment_type=control_config.type,
        )
        db.add(control)

    db.commit()

    response_data = SlotResponse(
        slot=slot,
        module_type=config.module_type,
        configured=True,
        sensors_configured=len(config.sensors),
        controls_configured=len(config.controls),
    )

    return build_success_response(response_data.model_dump())
