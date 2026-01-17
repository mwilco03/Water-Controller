-- Migration: Enable TimescaleDB Native Compression
-- Copyright (C) 2024
-- SPDX-License-Identifier: GPL-3.0-or-later
--
-- This migration replaces custom C-level compression with TimescaleDB native
-- compression, which provides superior compression ratios and query performance.
--
-- Benefits:
-- - Removes need for custom deadband/swinging-door algorithms in C code
-- - Better compression ratios (TimescaleDB uses gorilla+delta-of-delta)
-- - Faster queries on compressed data
-- - Automatic compression via policy

-- =============================================================================
-- Enable compression on historian_data hypertable
-- =============================================================================

-- Enable compression with optimal settings for industrial time-series data
-- segmentby: tag_id - compresses each tag separately for better ratios
-- orderby: time DESC - optimizes for recent data queries (most common pattern)
ALTER TABLE historian_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'time DESC'
);

-- Add compression policy: compress chunks older than 7 days
-- Keeps recent data uncompressed for fast writes, older data compressed for storage
SELECT add_compression_policy('historian_data',
    INTERVAL '7 days',
    if_not_exists => TRUE);

-- =============================================================================
-- Create daily continuous aggregate
-- =============================================================================

-- Daily aggregate for long-term trending and reports
CREATE MATERIALIZED VIEW IF NOT EXISTS historian_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    tag_id,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    STDDEV(value) AS stddev_value,
    COUNT(*) AS sample_count,
    -- Quality statistics (percentage of good samples)
    COUNT(*) FILTER (WHERE quality = 192) AS good_count,
    COUNT(*) FILTER (WHERE quality = 128) AS bad_count,
    COUNT(*) FILTER (WHERE quality = 64) AS uncertain_count
FROM historian_data
GROUP BY bucket, tag_id;

-- Add refresh policy for daily aggregate
SELECT add_continuous_aggregate_policy('historian_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- =============================================================================
-- Compression on continuous aggregates
-- =============================================================================

-- Enable compression on hourly aggregate (already exists)
ALTER MATERIALIZED VIEW historian_hourly SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'bucket DESC'
);

SELECT add_compression_policy('historian_hourly',
    INTERVAL '30 days',
    if_not_exists => TRUE);

-- Enable compression on daily aggregate
ALTER MATERIALIZED VIEW historian_daily SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'bucket DESC'
);

SELECT add_compression_policy('historian_daily',
    INTERVAL '90 days',
    if_not_exists => TRUE);

-- =============================================================================
-- Update retention policies for aggregates
-- =============================================================================

-- Keep hourly data for 1 year
SELECT add_retention_policy('historian_hourly',
    INTERVAL '365 days',
    if_not_exists => TRUE);

-- Keep daily data for 5 years (matches audit report recommendation)
SELECT add_retention_policy('historian_daily',
    INTERVAL '1825 days',
    if_not_exists => TRUE);

-- =============================================================================
-- Query helper views
-- =============================================================================

-- View to get latest uncompressed data (last 7 days)
CREATE OR REPLACE VIEW historian_recent AS
SELECT
    h.time,
    h.tag_id,
    t.tag_name,
    h.value,
    h.quality,
    CASE h.quality
        WHEN 192 THEN 'GOOD'
        WHEN 128 THEN 'BAD'
        WHEN 64 THEN 'UNCERTAIN'
        WHEN 0 THEN 'NOT_CONNECTED'
        ELSE 'UNKNOWN'
    END AS quality_text
FROM historian_data h
JOIN historian_tags t ON h.tag_id = t.id
WHERE h.time > NOW() - INTERVAL '7 days';

-- View to get compressed statistics
-- Uses hypertable_compression_stats() function (compressed_hypertable_stats view was removed in TimescaleDB 2.10+)
CREATE OR REPLACE VIEW historian_compression_stats AS
SELECT
    hypertable_name,
    total_chunks,
    number_compressed_chunks AS compressed_chunks,
    before_compression_total_bytes AS uncompressed_heap_size,
    after_compression_total_bytes AS compressed_heap_size,
    CASE WHEN before_compression_total_bytes > 0 THEN
        ROUND(
            (1 - after_compression_total_bytes::numeric / before_compression_total_bytes) * 100,
            2
        )
    ELSE 0
    END AS compression_ratio_pct
FROM (
    SELECT 'historian_data'::text AS hypertable_name, * FROM hypertable_compression_stats('historian_data')
    UNION ALL
    SELECT 'historian_hourly'::text AS hypertable_name, * FROM hypertable_compression_stats('historian_hourly')
    UNION ALL
    SELECT 'historian_daily'::text AS hypertable_name, * FROM hypertable_compression_stats('historian_daily')
) stats;

COMMENT ON VIEW historian_compression_stats IS
'Shows compression statistics for historian tables. Typical compression ratios: 80-95%';

-- Grant permissions
GRANT SELECT ON historian_recent TO wtc;
GRANT SELECT ON historian_compression_stats TO wtc;
GRANT SELECT ON historian_daily TO wtc;
