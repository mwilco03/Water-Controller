"""
Water Treatment Controller - Historian/Trends Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later
"""

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.historian import DataQuality, HistorianSample
from ...models.rtu import Sensor
from ...schemas.common import DataQuality as DataQualityEnum
from ...schemas.trends import (
    ExportFormat,
    TrendAggregate,
    TrendData,
    TrendExportRequest,
    TrendInterval,
    TrendMeta,
    TrendPoint,
    TrendPointValue,
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
) -> dict[str, Any]:
    """
    Get historical data for trending.

    Performance: Uses single bulk query per tag + in-memory aggregation
    instead of per-interval queries (O(tags) instead of O(tags x intervals)).
    """
    tag_list = [t.strip() for t in tags.split(",")]

    # Get sensor IDs for the tags
    sensors = db.query(Sensor).filter(Sensor.tag.in_(tag_list)).all()
    sensor_map = {s.tag: s for s in sensors}

    # Get interval in seconds
    interval_seconds = get_interval_seconds(interval)

    # Pre-fetch ALL samples for ALL tags in the time range (single query per tag)
    # This converts O(intervals x tags) queries to O(tags) queries
    samples_by_sensor = {}
    for tag in tag_list:
        sensor = sensor_map.get(tag)
        if sensor:
            samples = db.query(HistorianSample).filter(
                HistorianSample.sensor_id == sensor.id,
                HistorianSample.timestamp >= start,
                HistorianSample.timestamp < end
            ).order_by(HistorianSample.timestamp).all()
            samples_by_sensor[sensor.id] = samples

    # Build index for O(1) bucket assignment
    # bucket_key = floor(timestamp / interval_seconds) * interval_seconds
    def get_bucket_start(ts: datetime) -> datetime:
        ts_epoch = ts.timestamp()
        bucket_epoch = (int(ts_epoch) // interval_seconds) * interval_seconds
        return datetime.fromtimestamp(bucket_epoch, tz=ts.tzinfo or UTC)

    # Pre-aggregate samples into buckets (O(n) where n = total samples)
    bucket_samples = {}  # (tag, bucket_start) -> list of samples
    for tag in tag_list:
        sensor = sensor_map.get(tag)
        if not sensor:
            continue
        for sample in samples_by_sensor.get(sensor.id, []):
            bucket = get_bucket_start(sample.timestamp)
            key = (tag, bucket)
            if key not in bucket_samples:
                bucket_samples[key] = []
            bucket_samples[key].append(sample)

    # Build result points using pre-aggregated buckets
    points = []
    current = start

    while current < end:
        values = {}
        for tag in tag_list:
            sensor = sensor_map.get(tag)
            if not sensor:
                values[tag] = TrendPointValue(
                    value=None,
                    quality=DataQualityEnum.BAD,
                ).model_dump()
                continue

            # O(1) lookup for bucket samples
            samples = bucket_samples.get((tag, current), [])

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

        current = current + timedelta(seconds=interval_seconds)

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
        header = ["Timestamp", *request.tags]
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
        # PDF export requires additional library (reportlab, etc.)
        raise HTTPException(
            status_code=501,
            detail="PDF export not implemented. Use CSV format instead."
        )
