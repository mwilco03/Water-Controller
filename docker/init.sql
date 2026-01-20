-- Water Treatment Controller - Database Initialization
-- Copyright (C) 2024
-- SPDX-License-Identifier: GPL-3.0-or-later

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- RTU Devices table
CREATE TABLE IF NOT EXISTS rtu_devices (
    id SERIAL PRIMARY KEY,
    station_name VARCHAR(64) UNIQUE NOT NULL,
    ip_address INET NOT NULL,
    vendor_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    slot_count INTEGER DEFAULT NULL,  -- Reported by RTU, NULL until connected
    connection_state VARCHAR(32) NOT NULL DEFAULT 'OFFLINE',
    last_seen TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- NOTE: No slot_configs table. Slots are PROFINET frame positions, not database entities.
-- Sensors/controls store slot_number as optional metadata (nullable integer).
-- See CLAUDE.md "Slots Architecture Decision" for rationale.

-- Historian Tags table
CREATE TABLE IF NOT EXISTS historian_tags (
    id SERIAL PRIMARY KEY,
    rtu_station VARCHAR(64) NOT NULL,
    slot INTEGER NOT NULL,
    tag_name VARCHAR(128) UNIQUE NOT NULL,
    sample_rate_ms INTEGER NOT NULL DEFAULT 1000,
    deadband REAL NOT NULL DEFAULT 0.0,
    compression VARCHAR(32) NOT NULL DEFAULT 'DEADBAND',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Time-series data table (hypertable)
CREATE TABLE IF NOT EXISTS historian_data (
    time TIMESTAMPTZ NOT NULL,
    tag_id INTEGER NOT NULL REFERENCES historian_tags(id),
    value REAL NOT NULL,
    quality INTEGER NOT NULL DEFAULT 192
);

-- Convert to hypertable
SELECT create_hypertable('historian_data', 'time', if_not_exists => TRUE);

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_historian_data_tag_time ON historian_data (tag_id, time DESC);

-- Alarm Rules table
CREATE TABLE IF NOT EXISTS alarm_rules (
    id SERIAL PRIMARY KEY,
    rtu_station VARCHAR(64) NOT NULL,
    slot INTEGER NOT NULL,
    condition VARCHAR(16) NOT NULL CHECK (condition IN ('HIGH_HIGH', 'HIGH', 'LOW', 'LOW_LOW', 'RATE_OF_CHANGE', 'DEVIATION')),
    threshold REAL NOT NULL,
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL', 'EMERGENCY')),
    delay_ms INTEGER NOT NULL DEFAULT 0,
    message VARCHAR(256) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Alarm History table (hypertable)
CREATE TABLE IF NOT EXISTS alarm_history (
    time TIMESTAMPTZ NOT NULL,
    alarm_id SERIAL,
    rule_id INTEGER REFERENCES alarm_rules(id),
    rtu_station VARCHAR(64) NOT NULL,
    slot INTEGER NOT NULL,
    severity VARCHAR(16) NOT NULL,
    state VARCHAR(16) NOT NULL CHECK (state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'CLEARED_UNACK', 'CLEARED')),
    message VARCHAR(256) NOT NULL,
    value REAL NOT NULL,
    threshold REAL NOT NULL,
    ack_time TIMESTAMPTZ,
    ack_user VARCHAR(64),
    clear_time TIMESTAMPTZ
);

-- Convert to hypertable
SELECT create_hypertable('alarm_history', 'time', if_not_exists => TRUE);

-- PID Loops table
CREATE TABLE IF NOT EXISTS pid_loops (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    input_rtu VARCHAR(64) NOT NULL,
    input_slot INTEGER NOT NULL,
    output_rtu VARCHAR(64) NOT NULL,
    output_slot INTEGER NOT NULL,
    kp REAL NOT NULL DEFAULT 1.0,
    ki REAL NOT NULL DEFAULT 0.0,
    kd REAL NOT NULL DEFAULT 0.0,
    setpoint REAL NOT NULL DEFAULT 0.0,
    output_min REAL NOT NULL DEFAULT 0.0,
    output_max REAL NOT NULL DEFAULT 100.0,
    mode VARCHAR(16) NOT NULL DEFAULT 'AUTO' CHECK (mode IN ('AUTO', 'MANUAL', 'CASCADE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Interlocks table
CREATE TABLE IF NOT EXISTS interlocks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    input_rtu VARCHAR(64) NOT NULL,
    input_slot INTEGER NOT NULL,
    output_rtu VARCHAR(64) NOT NULL,
    output_slot INTEGER NOT NULL,
    condition VARCHAR(16) NOT NULL CHECK (condition IN ('ABOVE', 'BELOW', 'EQUAL', 'NOT_EQUAL')),
    threshold REAL NOT NULL,
    action VARCHAR(16) NOT NULL DEFAULT 'OFF' CHECK (action IN ('OFF', 'ON')),
    delay_ms INTEGER NOT NULL DEFAULT 0,
    latching BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users table (for authentication)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'operator' CHECK (role IN ('viewer', 'operator', 'engineer', 'admin')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sync_to_rtus BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    -- Password policy fields
    password_changed_at TIMESTAMPTZ DEFAULT NOW(),
    password_expires_at TIMESTAMPTZ,  -- NULL means never expires
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ  -- NULL means not locked
);

-- User sessions table (for authentication tokens)
CREATE TABLE IF NOT EXISTS user_sessions (
    token VARCHAR(256) PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'viewer',
    groups TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(256)
);

CREATE INDEX IF NOT EXISTS ix_user_sessions_expires ON user_sessions (expires_at);
CREATE INDEX IF NOT EXISTS ix_user_sessions_username ON user_sessions (username);

-- Audit Log table (hypertable)
-- Schema matches SQLAlchemy model in web/api/app/models/user.py
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "user" VARCHAR(64),
    action VARCHAR(32) NOT NULL,
    resource_type VARCHAR(32),
    resource_id VARCHAR(64),
    details TEXT,
    ip_address VARCHAR(45)
);

-- Convert to hypertable (partitioned by timestamp)
SELECT create_hypertable('audit_log', 'timestamp', if_not_exists => TRUE);

-- Index for SQLAlchemy ORM lookups and efficient queries
CREATE INDEX IF NOT EXISTS ix_audit_log_id ON audit_log (id);
CREATE INDEX IF NOT EXISTS ix_audit_log_user ON audit_log ("user");
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action);
CREATE INDEX IF NOT EXISTS ix_audit_log_resource ON audit_log (resource_type, resource_id);

-- Default admin user is created automatically by the API on startup via ensure_default_admin()

-- RTU Registration/Enrollment columns (2026-01 protocol addition)
-- These support RTU self-registration and device binding
ALTER TABLE rtu_devices ADD COLUMN IF NOT EXISTS enrollment_token VARCHAR(64) UNIQUE;
ALTER TABLE rtu_devices ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE rtu_devices ADD COLUMN IF NOT EXISTS serial_number VARCHAR(32);
ALTER TABLE rtu_devices ADD COLUMN IF NOT EXISTS mac_address VARCHAR(17);
ALTER TABLE rtu_devices ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(32);

-- Index for enrollment token lookups during registration
CREATE INDEX IF NOT EXISTS idx_rtu_devices_enrollment_token ON rtu_devices (enrollment_token) WHERE enrollment_token IS NOT NULL;

-- Insert sample RTU devices
INSERT INTO rtu_devices (station_name, ip_address, vendor_id, device_id, slot_count, connection_state)
VALUES
    ('rtu-tank-1', '192.168.1.100', 1, 1, 16, 'OFFLINE'),
    ('rtu-pump-station', '192.168.1.101', 1, 1, 16, 'OFFLINE'),
    ('rtu-filter-1', '192.168.1.102', 1, 1, 16, 'OFFLINE')
ON CONFLICT (station_name) DO NOTHING;

-- Insert sample historian tags
INSERT INTO historian_tags (rtu_station, slot, tag_name, sample_rate_ms, deadband, compression)
VALUES
    ('rtu-tank-1', 1, 'rtu-tank-1.pH', 1000, 0.05, 'SWINGING_DOOR'),
    ('rtu-tank-1', 2, 'rtu-tank-1.Temperature', 1000, 0.5, 'DEADBAND'),
    ('rtu-tank-1', 3, 'rtu-tank-1.Turbidity', 1000, 0.1, 'DEADBAND'),
    ('rtu-tank-1', 7, 'rtu-tank-1.Level', 1000, 0.5, 'SWINGING_DOOR'),
    ('rtu-tank-1', 8, 'rtu-tank-1.Pressure', 1000, 0.1, 'DEADBAND')
ON CONFLICT (tag_name) DO NOTHING;

-- Insert sample alarm rules
INSERT INTO alarm_rules (rtu_station, slot, condition, threshold, severity, delay_ms, message)
VALUES
    ('rtu-tank-1', 1, 'HIGH', 8.5, 'WARNING', 5000, 'pH High'),
    ('rtu-tank-1', 1, 'HIGH_HIGH', 9.0, 'CRITICAL', 0, 'pH Very High'),
    ('rtu-tank-1', 1, 'LOW', 6.5, 'WARNING', 5000, 'pH Low'),
    ('rtu-tank-1', 1, 'LOW_LOW', 6.0, 'CRITICAL', 0, 'pH Very Low'),
    ('rtu-tank-1', 7, 'LOW', 10.0, 'WARNING', 3000, 'Tank Level Low'),
    ('rtu-tank-1', 7, 'LOW_LOW', 5.0, 'CRITICAL', 0, 'Tank Level Critical'),
    ('rtu-tank-1', 8, 'HIGH', 8.0, 'WARNING', 2000, 'Pressure High'),
    ('rtu-tank-1', 8, 'HIGH_HIGH', 10.0, 'EMERGENCY', 0, 'Pressure Very High - Emergency');

-- Insert sample PID loop
INSERT INTO pid_loops (name, input_rtu, input_slot, output_rtu, output_slot, kp, ki, kd, setpoint, output_min, output_max, mode)
VALUES
    ('pH Control', 'rtu-tank-1', 1, 'rtu-tank-1', 12, 2.0, 0.1, 0.5, 7.0, 0.0, 100.0, 'AUTO'),
    ('Level Control', 'rtu-tank-1', 7, 'rtu-tank-1', 10, 1.5, 0.05, 0.2, 75.0, 0.0, 100.0, 'AUTO')
ON CONFLICT (name) DO NOTHING;

-- Insert sample interlocks
INSERT INTO interlocks (name, input_rtu, input_slot, output_rtu, output_slot, condition, threshold, action, delay_ms, latching)
VALUES
    ('Low Level Pump Protect', 'rtu-tank-1', 7, 'rtu-pump-station', 9, 'BELOW', 10.0, 'OFF', 0, TRUE),
    ('High Pressure Relief', 'rtu-tank-1', 8, 'rtu-tank-1', 11, 'ABOVE', 9.0, 'ON', 0, FALSE)
ON CONFLICT (name) DO NOTHING;

-- Create continuous aggregate for hourly averages
CREATE MATERIALIZED VIEW IF NOT EXISTS historian_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    tag_id,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM historian_data
GROUP BY bucket, tag_id;

-- Add refresh policy
SELECT add_continuous_aggregate_policy('historian_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- Add data retention policy (keep raw data for 30 days)
SELECT add_retention_policy('historian_data', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('alarm_history', INTERVAL '365 days', if_not_exists => TRUE);
SELECT add_retention_policy('audit_log', INTERVAL '365 days', if_not_exists => TRUE);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO wtc;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO wtc;

-- =============================================================================
-- TimescaleDB Native Compression (replaces custom C-level compression)
-- =============================================================================

-- Enable compression on historian_data hypertable
-- Provides 80-95% compression ratio for industrial time-series data
ALTER TABLE historian_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'time DESC'
);

-- Add compression policy: compress chunks older than 7 days
SELECT add_compression_policy('historian_data',
    INTERVAL '7 days',
    if_not_exists => TRUE);

-- Create daily continuous aggregate
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

-- Enable compression on continuous aggregates
ALTER MATERIALIZED VIEW historian_hourly SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'bucket DESC'
);

SELECT add_compression_policy('historian_hourly',
    INTERVAL '30 days',
    if_not_exists => TRUE);

ALTER MATERIALIZED VIEW historian_daily SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'tag_id',
  timescaledb.compress_orderby = 'bucket DESC'
);

SELECT add_compression_policy('historian_daily',
    INTERVAL '90 days',
    if_not_exists => TRUE);

-- Update retention policies for aggregates
SELECT add_retention_policy('historian_hourly',
    INTERVAL '365 days',
    if_not_exists => TRUE);

SELECT add_retention_policy('historian_daily',
    INTERVAL '1825 days',
    if_not_exists => TRUE);

-- Query helper views
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

-- Create compression stats view using hypertable_compression_stats() function
-- (The old compressed_hypertable_stats view was removed in TimescaleDB 2.10+)
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

GRANT SELECT ON historian_recent TO wtc;
GRANT SELECT ON historian_compression_stats TO wtc;
GRANT SELECT ON historian_daily TO wtc;
