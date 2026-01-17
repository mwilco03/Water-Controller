"""
Water Treatment Controller - Optimized Historian/Trends Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

This module uses TimescaleDB continuous aggregates for improved query performance.
Automatically selects the appropriate aggregate based on time range:
- < 7 days: Raw data (historian_data)
- 7-30 days: Hourly aggregates (historian_hourly)
- > 30 days: Daily aggregates (historian_daily)

Performance improvements over raw queries:
- 10-100x faster for long time ranges
- Reduced database load
- Pre-computed aggregations
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...schemas.common import DataQuality as DataQualityEnum
from ...schemas.trends import (
    TrendAggregate,
    TrendData,
    TrendInterval,
    TrendMeta,
    TrendPoint,
    TrendPointValue,
)

router = APIRouter()


def select_optimal_aggregate_table(start: datetime, end: datetime) -> tuple[str, str]:
    """
    Select the optimal TimescaleDB table/view based on time range.

    Returns:
        (table_name, bucket_column_name)
    """
    duration = end - start

    # For queries < 7 days, use raw data (uncompressed, most recent)
    if duration < timedelta(days=7):
        return ("historian_data", "time")

    # For queries 7-30 days, use hourly aggregates
    elif duration < timedelta(days=30):
        return ("historian_hourly", "bucket")

    # For queries > 30 days, use daily aggregates
    else:
        return ("historian_daily", "bucket")


def get_interval_for_range(start: datetime, end: datetime) -> str:
    """
    Automatically determine appropriate aggregation interval based on time range.

    ISA-101 HMI Guidelines:
    - Aim for 200-1000 points for optimal chart rendering
    - Too many points = sluggish UI
    - Too few points = missing detail
    """
    duration = end - start

    # < 1 hour: 1 second intervals (max 3600 points)
    if duration < timedelta(hours=1):
        return "1 second"

    # 1-4 hours: 10 second intervals (max 1440 points)
    elif duration < timedelta(hours=4):
        return "10 seconds"

    # 4-24 hours: 1 minute intervals (max 1440 points)
    elif duration < timedelta(days=1):
        return "1 minute"

    # 1-7 days: 5 minute intervals (max 2016 points)
    elif duration < timedelta(days=7):
        return "5 minutes"

    # 7-30 days: 1 hour intervals (max 720 points)
    elif duration < timedelta(days=30):
        return "1 hour"

    # > 30 days: 1 day intervals
    else:
        return "1 day"


@router.get("/optimized")
async def get_trends_optimized(
    tags: str = Query(..., description="Comma-separated historian tag IDs"),
    start: datetime = Query(..., description="Start time"),
    end: datetime = Query(..., description="End time"),
    interval: str | None = Query(None, description="Aggregation interval (auto-detected if not provided)"),
    aggregate: TrendAggregate = Query(TrendAggregate.AVG, description="Aggregation function"),
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get historical data using TimescaleDB continuous aggregates for optimal performance.

    This endpoint automatically selects the best data source:
    - Recent data (< 7 days): Raw uncompressed data
    - Medium range (7-30 days): Hourly pre-aggregated data
    - Long range (> 30 days): Daily pre-aggregated data

    Performance:
    - Up to 100x faster than raw queries for long ranges
    - Reduced database load
    - Automatic interval selection for optimal chart rendering
    """
    # Parse tag IDs
    tag_ids = [int(t.strip()) for t in tags.split(",")]

    # Auto-detect interval if not provided
    if interval is None:
        interval = get_interval_for_range(start, end)

    # Select optimal data source
    table_name, time_column = select_optimal_aggregate_table(start, end)

    # Map aggregate function to SQL
    agg_func_map = {
        TrendAggregate.AVG: "AVG",
        TrendAggregate.MIN: "MIN",
        TrendAggregate.MAX: "MAX",
        TrendAggregate.FIRST: "FIRST",  # TimescaleDB extension
        TrendAggregate.LAST: "LAST",    # TimescaleDB extension
    }
    agg_sql = agg_func_map.get(aggregate, "AVG")

    # Build query based on data source
    if table_name == "historian_data":
        # Raw data query with time_bucket aggregation
        query = text("""
            SELECT
                time_bucket(:interval, time) AS bucket,
                tag_id,
                {agg_func}(value) AS value,
                -- Quality: Use worst quality in bucket
                CASE
                    WHEN COUNT(*) FILTER (WHERE quality = 128) > 0 THEN 128  -- BAD
                    WHEN COUNT(*) FILTER (WHERE quality = 64) > 0 THEN 64    -- UNCERTAIN
                    WHEN COUNT(*) FILTER (WHERE quality = 192) > 0 THEN 192  -- GOOD
                    ELSE 0  -- NOT_CONNECTED
                END AS quality,
                COUNT(*) AS sample_count
            FROM historian_data
            WHERE
                tag_id = ANY(:tag_ids)
                AND time >= :start
                AND time < :end
            GROUP BY bucket, tag_id
            ORDER BY bucket, tag_id
        """.format(agg_func=agg_sql))

    else:
        # Use pre-computed continuous aggregate
        # Note: Continuous aggregates already have AVG/MIN/MAX computed
        if aggregate == TrendAggregate.AVG:
            value_column = "avg_value"
        elif aggregate == TrendAggregate.MIN:
            value_column = "min_value"
        elif aggregate == TrendAggregate.MAX:
            value_column = "max_value"
        else:
            value_column = "avg_value"  # Default to average

        query = text(f"""
            SELECT
                bucket,
                tag_id,
                {value_column} AS value,
                -- Estimate quality based on sample_count
                -- If we have samples, assume GOOD (quality tracking in aggregates would require schema change)
                CASE
                    WHEN sample_count > 0 THEN 192  -- GOOD
                    ELSE 0  -- NOT_CONNECTED
                END AS quality,
                sample_count
            FROM {table_name}
            WHERE
                tag_id = ANY(:tag_ids)
                AND bucket >= :start
                AND bucket < :end
            ORDER BY bucket, tag_id
        """)

    # Execute query
    result = db.execute(query, {
        "tag_ids": tag_ids,
        "start": start,
        "end": end,
        "interval": interval,
    })

    # Transform results into point format
    points_by_time = {}
    for row in result:
        timestamp = row[0]  # bucket
        tag_id = row[1]
        value = row[2]
        quality = row[3]

        if timestamp not in points_by_time:
            points_by_time[timestamp] = {}

        # Map quality integer to enum
        quality_map = {
            192: DataQualityEnum.GOOD,
            128: DataQualityEnum.BAD,
            64: DataQualityEnum.UNCERTAIN,
            0: DataQualityEnum.NOT_CONNECTED,
        }
        quality_enum = quality_map.get(quality, DataQualityEnum.UNCERTAIN)

        points_by_time[timestamp][str(tag_id)] = TrendPointValue(
            value=round(value, 4) if value is not None else None,
            quality=quality_enum,
        ).model_dump()

    # Build points array
    points = [
        TrendPoint(
            timestamp=ts,
            values=values,
        ).model_dump()
        for ts, values in sorted(points_by_time.items())
    ]

    # Get tag names for response
    tag_names = [str(tid) for tid in tag_ids]

    data = TrendData(
        tags=tag_names,
        interval=TrendInterval.ONE_MINUTE,  # Placeholder, actual interval is variable
        points=points,
    )

    meta = TrendMeta(
        point_count=len(points),
        start=start,
        end=end,
        data_source=table_name,  # Extra metadata for debugging
        actual_interval=interval,  # Extra metadata
    )

    return {
        "data": data.model_dump(),
        "meta": meta.model_dump(),
    }


@router.get("/compression-stats")
async def get_compression_stats(
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get TimescaleDB compression statistics for historian tables.

    Shows compression ratios and storage savings from native compression.
    Typical compression ratios: 80-95% for industrial time-series data.
    """
    # Use hypertable_compression_stats() function (compressed_hypertable_stats view was removed in TimescaleDB 2.10+)
    query = text("""
        SELECT
            hypertable_name,
            CASE
                WHEN total_chunks > 0 THEN
                    ROUND((compressed_chunks::numeric / total_chunks * 100), 1)
                ELSE 0
            END AS compression_pct,
            pg_size_pretty(uncompressed_heap_size) AS uncompressed_size,
            pg_size_pretty(compressed_heap_size) AS compressed_size,
            compression_ratio_pct
        FROM historian_compression_stats
    """)

    result = db.execute(query)
    stats = []
    for row in result:
        stats.append({
            "table": row[0],
            "chunks_compressed_pct": float(row[1]) if row[1] else 0,
            "uncompressed_size": row[2],
            "compressed_size": row[3],
            "compression_ratio_pct": float(row[4]) if row[4] else 0,
        })

    return build_success_response({
        "compression_stats": stats,
        "note": "Compression occurs automatically on chunks older than 7 days",
    })
