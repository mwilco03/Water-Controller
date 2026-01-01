"""
Water Treatment Controller - Slot Configuration Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...core.exceptions import ValidationError
from ...core.rtu_utils import get_rtu_or_404, get_slot_or_404
from ...models.base import get_db
from ...models.rtu import Control, Sensor, Slot, SlotStatus
from ...schemas.slot import (
    SlotConfig,
    SlotConfigUpdate,
    SlotResponse,
    SlotSensorSummary,
)

router = APIRouter()


@router.get("")
async def list_slots(
    name: str = Path(..., description="RTU station name"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    List all slots for an RTU.
    """
    rtu = get_rtu_or_404(db, name)

    # Single query with eager loading - eliminates N+1 problem
    # Previously: 1 + 2*N queries (1 for slots, N for sensors, N for controls)
    # Now: 3 queries total (1 for slots, 1 for all sensors, 1 for all controls)
    slots = db.query(Slot).filter(Slot.rtu_id == rtu.id).order_by(Slot.slot_number).all()

    # Batch load sensors and controls for all slots at once
    slot_ids = [slot.id for slot in slots]
    all_sensors = db.query(Sensor).filter(Sensor.slot_id.in_(slot_ids)).all() if slot_ids else []
    all_controls = db.query(Control).filter(Control.slot_id.in_(slot_ids)).all() if slot_ids else []

    # Group by slot_id for O(1) lookup
    sensors_by_slot = {}
    for s in all_sensors:
        sensors_by_slot.setdefault(s.slot_id, []).append(s)

    controls_by_slot = {}
    for c in all_controls:
        controls_by_slot.setdefault(c.slot_id, []).append(c)

    result = []
    for slot in slots:
        sensors = sensors_by_slot.get(slot.id, [])
        sensor_summaries = [
            SlotSensorSummary(
                id=s.id,
                tag=s.tag,
                type=s.sensor_type,
            ).model_dump()
            for s in sensors
        ]

        controls = controls_by_slot.get(slot.id, [])
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
) -> dict[str, Any]:
    """
    Configure a slot (module type, sensor mappings).
    """
    rtu = get_rtu_or_404(db, name)
    slot_obj = get_slot_or_404(db, rtu, slot)

    # Update slot configuration
    slot_obj.module_type = config.module_type
    slot_obj.status = SlotStatus.OK
    slot_obj.updated_at = datetime.now(UTC)

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
