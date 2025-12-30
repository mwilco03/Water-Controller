"""
Water Treatment Controller - Sensor Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from ...core.rtu_utils import get_data_quality, get_rtu_or_404
from ...models.base import get_db
from ...models.rtu import RtuState, Sensor
from ...schemas.common import DataQuality
from ...schemas.sensor import SensorListMeta, SensorValue

router = APIRouter()


@router.get("")
async def get_sensors(
    name: str = Path(..., description="RTU station name"),
    tags: str | None = Query(None, description="Comma-separated list of tags"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get current sensor values with quality.

    Always includes quality field - never return value without quality.
    """
    rtu = get_rtu_or_404(db, name)

    query = db.query(Sensor).filter(Sensor.rtu_id == rtu.id)

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        query = query.filter(Sensor.tag.in_(tag_list))

    sensors = query.order_by(Sensor.tag).all()

    # Determine data quality based on RTU state
    quality = get_data_quality(rtu.state)
    now = datetime.now(UTC)

    result = []
    for sensor in sensors:
        # In a real implementation, values would come from shared memory
        # For now, return placeholder values based on RTU state
        if quality == DataQuality.GOOD:
            value = 50.0  # Placeholder - would come from real I/O
            raw_value = 32768
        else:
            value = None
            raw_value = None

        sensor_value = SensorValue(
            tag=sensor.tag,
            value=value,
            unit=sensor.unit,
            quality=quality,
            quality_reason=None if quality == DataQuality.GOOD else f"RTU state: {rtu.state}",
            timestamp=now,
            raw_value=raw_value,
        )
        result.append(sensor_value.model_dump())

    meta = SensorListMeta(
        rtu_state=rtu.state,
        last_io_update=now if rtu.state == RtuState.RUNNING else None,
    )

    return {
        "data": result,
        "meta": meta.model_dump(),
    }
