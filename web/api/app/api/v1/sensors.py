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
from ...services.profinet_client import get_profinet_client

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

    # Get live sensor values from controller via shared memory
    profinet = get_profinet_client()
    live_sensors = profinet.get_sensor_values(rtu.station_name)

    # Build lookup by slot for efficient matching
    live_by_slot = {s["slot"]: s for s in live_sensors}

    result = []
    for sensor in sensors:
        # Try to get live value from controller
        live = live_by_slot.get(sensor.slot)

        if live and quality == DataQuality.GOOD:
            value = live.get("value")
            raw_value = int(live.get("value", 0) * 655.35) if live.get("value") is not None else None
            # Use quality from controller if available
            live_quality_code = live.get("quality_code", 0)
            if live_quality_code == 0:
                sensor_quality = DataQuality.GOOD
            elif live_quality_code == 0x40:
                sensor_quality = DataQuality.UNCERTAIN
            else:
                sensor_quality = DataQuality.NOT_CONNECTED
            quality_reason = None if sensor_quality == DataQuality.GOOD else live.get("quality", "unknown")
        elif quality == DataQuality.GOOD:
            # Controller connected but no data for this sensor yet
            value = None
            raw_value = None
            sensor_quality = DataQuality.UNCERTAIN
            quality_reason = "No data from controller"
        else:
            value = None
            raw_value = None
            sensor_quality = quality
            quality_reason = f"RTU state: {rtu.state}"

        sensor_value = SensorValue(
            tag=sensor.tag,
            value=value,
            unit=sensor.unit,
            quality=sensor_quality,
            quality_reason=quality_reason,
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
