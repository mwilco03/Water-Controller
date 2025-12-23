"""
Water Treatment Controller - Historian/Trends Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import io
import csv

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import Sensor
from ...models.historian import HistorianSample, DataQuality
from ...schemas.common import DataQuality as DataQualityEnum
from ...schemas.trends import (
    TrendInterval,
    TrendAggregate,
    TrendPoint,
    TrendPointValue,
    TrendData,
    TrendMeta,
    TrendExportRequest,
    ExportFormat,
)

router = APIRouter()


def get_interval_seconds(interval: TrendInterval) -> int:
    """Convert interval enum to seconds."""
    mapping = {
        TrendInterval.ONE_SECOND: 1,
        TrendInterval.ONE_MINUTE: 60,
        TrendInterval.FIVE_MINUTES: 300,
        TrendInterval.ONE_HOUR: 3600,
        TrendInterval.ONE_DAY: 86400,
    }
    return mapping.get(interval, 60)


@router.get("")
async def get_trends(
    tags: str = Query(..., description="Comma-separated sensor tags"),
    start: datetime = Query(..., description="Start time"),
    end: datetime = Query(..., description="End time"),
    interval: TrendInterval = Query(TrendInterval.ONE_MINUTE, description="Aggregation interval"),
    aggregate: TrendAggregate = Query(TrendAggregate.AVG, description="Aggregation function"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get historical data for trending.
    """
    tag_list = [t.strip() for t in tags.split(",")]

    # Get sensor IDs for the tags
    sensors = db.query(Sensor).filter(Sensor.tag.in_(tag_list)).all()
    sensor_map = {s.tag: s for s in sensors}

    # Get interval in seconds
    interval_seconds = get_interval_seconds(interval)

    # Build result points
    points = []
    current = start

    while current < end:
        next_time = current + timedelta(seconds=interval_seconds)

        # Query for each tag
        values = {}
        for tag in tag_list:
            sensor = sensor_map.get(tag)
            if not sensor:
                values[tag] = TrendPointValue(
                    value=None,
                    quality=DataQualityEnum.BAD,
                ).model_dump()
                continue

            # Query samples in this interval
            query = db.query(HistorianSample).filter(
                HistorianSample.sensor_id == sensor.id,
                HistorianSample.timestamp >= current,
                HistorianSample.timestamp < next_time
            )

            samples = query.all()

            if samples:
                # Apply aggregation
                sample_values = [s.value for s in samples if s.value is not None]
                if sample_values:
                    if aggregate == TrendAggregate.MIN:
                        agg_value = min(sample_values)
                    elif aggregate == TrendAggregate.MAX:
                        agg_value = max(sample_values)
                    elif aggregate == TrendAggregate.FIRST:
                        agg_value = sample_values[0]
                    elif aggregate == TrendAggregate.LAST:
                        agg_value = sample_values[-1]
                    else:  # AVG
                        agg_value = sum(sample_values) / len(sample_values)

                    # Determine quality (use worst quality from samples)
                    qualities = [s.quality for s in samples]
                    if DataQuality.BAD in qualities:
                        quality = DataQualityEnum.BAD
                    elif DataQuality.UNCERTAIN in qualities:
                        quality = DataQualityEnum.UNCERTAIN
                    else:
                        quality = DataQualityEnum.GOOD

                    values[tag] = TrendPointValue(
                        value=round(agg_value, 4),
                        quality=quality,
                    ).model_dump()
                else:
                    values[tag] = TrendPointValue(
                        value=None,
                        quality=DataQualityEnum.BAD,
                    ).model_dump()
            else:
                values[tag] = TrendPointValue(
                    value=None,
                    quality=DataQualityEnum.NOT_CONNECTED,
                ).model_dump()

        points.append(TrendPoint(
            timestamp=current,
            values=values,
        ).model_dump())

        current = next_time

    data = TrendData(
        tags=tag_list,
        interval=interval,
        points=points,
    )

    meta = TrendMeta(
        point_count=len(points),
        start=start,
        end=end,
    )

    return {
        "data": data.model_dump(),
        "meta": meta.model_dump(),
    }


@router.post("/export")
async def export_trends(
    request: TrendExportRequest,
    db: Session = Depends(get_db)
):
    """
    Export trend data to file.

    Returns file download.
    """
    # Get sensor IDs for the tags
    sensors = db.query(Sensor).filter(Sensor.tag.in_(request.tags)).all()
    sensor_map = {s.tag: s for s in sensors}

    # Query all samples in range
    samples_by_tag = {}
    for tag in request.tags:
        sensor = sensor_map.get(tag)
        if sensor:
            samples = db.query(HistorianSample).filter(
                HistorianSample.sensor_id == sensor.id,
                HistorianSample.timestamp >= request.start,
                HistorianSample.timestamp <= request.end
            ).order_by(HistorianSample.timestamp).all()
            samples_by_tag[tag] = samples

    if request.format == ExportFormat.CSV:
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        header = ["Timestamp"] + request.tags
        if request.include_metadata:
            header += [f"{tag}_quality" for tag in request.tags]
        writer.writerow(header)

        # Pre-index samples by (tag, timestamp) for O(1) lookup instead of O(n) per row
        # This converts O(n²m) to O(nm) where n=timestamps, m=tags
        sample_index = {}
        all_timestamps = set()
        for tag, samples in samples_by_tag.items():
            for sample in samples:
                all_timestamps.add(sample.timestamp)
                sample_index[(tag, sample.timestamp)] = sample

        # Write rows with O(1) lookups
        for ts in sorted(all_timestamps):
            row = [ts.isoformat()]
            for tag in request.tags:
                sample = sample_index.get((tag, ts))
                row.append(sample.value if sample else "")
            if request.include_metadata:
                for tag in request.tags:
                    sample = sample_index.get((tag, ts))
                    row.append(sample.quality if sample else "")
            writer.writerow(row)

        output.seek(0)

        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=trends_{request.start.date()}_{request.end.date()}.csv"
            }
        )
    else:
        # PDF export would require additional library (reportlab, etc.)
        # For now, return error
        return build_success_response({
            "error": "PDF export not yet implemented",
            "format": request.format,
        })
