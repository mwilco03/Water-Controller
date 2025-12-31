<!--
  AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

  Generated from: schemas/config/*.schema.yaml
  Generated at: 2025-12-30 15:12:11 UTC
  Generator: scripts/generate_docs.py

  To update this file, modify the source schemas and run:
    python scripts/generate_docs.py
-->

# Water Treatment Controller Configuration Reference

This document is automatically generated from the configuration schemas.
It provides a complete reference for all configuration options.

## Table of Contents

- [Alarm Manager Configuration](#alarm-manager-configuration)
- [Water Treatment Controller Configuration](#water-treatment-controller-configuration)
- [Data Historian Configuration](#data-historian-configuration)
- [Modbus Gateway Configuration](#modbus-gateway-configuration)
- [PROFINET IO Controller Configuration](#profinet-io-controller-configuration)
- [Web API and HMI Configuration](#web-api-and-hmi-configuration)
- [Environment Variable Quick Reference](#environment-variable-quick-reference)
## Alarm Manager Configuration

ISA-18.2 compliant alarm management configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_path` | `string` | `""` | Alarm database path (uses main database if empty) |
| `enabled` | `boolean` | `true` | Enable alarm management (Env: `WTC_ALARMS_ENABLED`) |

### conditions

Available alarm conditions

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `conditions.types` | `array<string>` | `[...]` (7 items) | Available alarm condition types |

### flood_detection

Alarm flood detection (per ISA-18.2)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `flood_detection.enabled` | `boolean` | `true` | Enable alarm flood detection |
| `flood_detection.target_rate_per_10min` | `integer` (min: 1, max: 100) | `10` | Target sustainable alarm rate (ISA-18.2 benchmark) |
| `flood_detection.threshold_per_10min` | `integer` (min: 10, max: 1000) | `100` | Alarm count threshold to declare flood condition |

### isa_18_2

ISA-18.2 compliance settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `isa_18_2.max_shelve_duration_hours` | `integer` (min: 1, max: 168) | `24` | Maximum duration an alarm can be shelved (Unit: hours) |
| `isa_18_2.out_of_service_logging` | `boolean` | `true` | Log all out-of-service state changes |
| `isa_18_2.rationalization_required` | `boolean` | `false` | Require consequence and response for each alarm rule |
| `isa_18_2.require_acknowledgment` | `boolean` | `true` | Require operator acknowledgment for alarms |
| `isa_18_2.shelving_enabled` | `boolean` | `true` | Allow alarm shelving (temporary disable with audit) |

### limits

Alarm system limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.max_active_alarms` | `integer` (min: 10, max: 10000) | `256` | Maximum concurrent active alarms |
| `limits.max_history_entries` | `integer` (min: 100, max: 1000000) | `10000` | Maximum alarm history entries to retain |
| `limits.max_rules` | `integer` (min: 1, max: 10000) | `512` | Maximum alarm rules |

### notifications

Alarm notification settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `notifications.audible_alert` | `boolean` | `true` | Enable audible alerts on HMI |
| `notifications.enabled` | `boolean` | `true` | Enable alarm notifications |
| `notifications.websocket_broadcast` | `boolean` | `true` | Broadcast alarms to WebSocket clients |

#### notifications.email

Email notification settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `notifications.email.enabled` | `boolean` | `false` | Enable email notifications |
| `notifications.email.min_severity` | `integer` (min: 1, max: 4) | `3` | Minimum severity to trigger email |
| `notifications.email.recipients` | `array<string>` | `[]` | Email recipients for alarm notifications |
| `notifications.email.smtp_host` | `string` | `""` | SMTP server hostname (Env: `WTC_SMTP_HOST`) |
| `notifications.email.smtp_port` | `integer` (min: 1, max: 65535) | `587` | SMTP server port |

### severity

Severity level definitions

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `severity.levels` | `array<object>` | `[...]` (4 items) |  |

### suppression

Alarm suppression settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `suppression.audit_all` | `boolean` | `true` | Audit log all suppression actions |
| `suppression.max_duration_minutes` | `integer` (min: 1, max: 1440) | `60` | Maximum suppression duration (Unit: minutes) |
| `suppression.require_reason` | `boolean` | `true` | Require reason when suppressing alarms |

---

## Water Treatment Controller Configuration

Main configuration for the Water Treatment PROFINET IO Controller

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

### cycle

Main control cycle timing

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cycle.scan_rate_ms` | `integer` (min: 10, max: 10000) | `100` | Control engine scan rate for PID/interlock evaluation (Unit: milliseconds) |
| `cycle.time_ms` | `integer` (min: 100, max: 60000) | `1000` | Main cycle time for data collection and control (Env: `WTC_CYCLE_TIME`, CLI: ... |

### daemon

Daemon/service mode settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `daemon.enabled` | `boolean` | `false` | Run as a background daemon (CLI: `-d, --daemon`) |
| `daemon.pid_file` | `string` | `"/var/run/water-controller.pid"` | PID file location when running as daemon |

### database

PostgreSQL database configuration for persistent storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database.connection_timeout_ms` | `integer` (min: 1000, max: 60000) | `5000` | Connection timeout (Unit: milliseconds) |
| `database.enabled` | `boolean` | `true` | Enable database persistence (CLI: `--no-db (disables)`) |
| `database.host` | `string` | `"localhost"` | PostgreSQL server hostname (Env: `WTC_DB_HOST`, CLI: `--db-host`) |
| `database.max_connections` | `integer` (min: 1, max: 100) | `5` | Maximum database connection pool size |
| `database.name` | `string` | `"water_controller"` | Database name (Env: `WTC_DB_NAME`, CLI: `--db-name`) |
| `database.password` | `string` | `""` | Database password (Env: `WTC_DB_PASSWORD`, CLI: `--db-password`, **SENSITIVE**) |
| `database.port` | `integer` (min: 1, max: 65535) | `5432` | PostgreSQL server port (Env: `WTC_DB_PORT`, CLI: `--db-port`) |
| `database.use_ssl` | `boolean` | `false` | Use SSL for database connections |
| `database.user` | `string` | `"wtc"` | Database username (Env: `WTC_DB_USER`, CLI: `--db-user`) |

### debug

Debug and development settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `debug.enabled` | `boolean` | `false` | Enable debug mode (Env: `WTC_DEBUG`) |
| `debug.simulation_mode` | `boolean` | `false` | Run in simulation mode without real hardware (Env: `WTC_SIMULATION_MODE`) |
| `debug.startup_mode` | `string` (``, `development`, `testing`, `production`) | `""` | Startup mode override (Env: `WTC_STARTUP_MODE`) |

### failover

RTU failover and redundancy settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `failover.enabled` | `boolean` | `true` | Enable automatic failover handling (Env: `WTC_FAILOVER_ENABLED`) |
| `failover.heartbeat_interval_ms` | `integer` (min: 100, max: 10000) | `1000` | RTU health check interval (Unit: milliseconds) |
| `failover.max_retries` | `integer` (min: 0, max: 10) | `3` | Number of reconnection attempts before failover |
| `failover.mode` | `string` (`manual`, `auto`, `hot_standby`) | `"auto"` | Failover mode (Env: `WTC_FAILOVER_MODE`) |
| `failover.timeout_ms` | `integer` (min: 1000, max: 60000) | `5000` | Time to wait before declaring RTU failed (Env: `WTC_FAILOVER_TIMEOUT_MS`, Uni... |

### ipc

Inter-process communication settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ipc.shm_name` | `string` | `"/wtc_shared_memory"` | Shared memory segment name (Env: `WTC_SHM_NAME`) |
| `ipc.shm_read_timeout_ms` | `integer` (min: 10, max: 5000) | `100` | Timeout for reading shared memory (Env: `WTC_SHM_READ_TIMEOUT_MS`, Unit: mill... |

### limits

System limits and maximums

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.default_slots` | `integer` | `64` | Default slot count per RTU |
| `limits.max_alarm_rules` | `integer` | `512` | Maximum number of alarm rules |
| `limits.max_historian_tags` | `integer` | `1024` | Maximum number of historian tags |
| `limits.max_interlocks` | `integer` | `128` | Maximum number of interlocks |
| `limits.max_pid_loops` | `integer` | `64` | Maximum number of PID control loops |
| `limits.max_rtus` | `integer` | `256` | Maximum number of RTU devices |
| `limits.max_sequences` | `integer` | `32` | Maximum number of control sequences |
| `limits.max_slots` | `integer` | `256` | Maximum slots per RTU for fixed arrays |

### logging

Logging configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `logging.file` | `string` | `""` | Log file path (empty for stderr only) (Env: `WTC_LOG_FILE`, CLI: `-l, --log`) |
| `logging.level` | `string` (`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`) | `"INFO"` | Minimum log level to output (Env: `WTC_LOG_LEVEL`, CLI: `-v, --verbose (decre... |
| `logging.log_dir` | `string` | `"/var/log/water-controller"` | Directory for log files (Env: `WTC_LOG_DIR`) |
| `logging.structured` | `boolean` | `false` | Enable structured JSON logging for log aggregators (Env: `WTC_LOG_STRUCTURED`) |

#### logging.forward

Log forwarding to external systems (Elastic, Graylog, Syslog)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `logging.forward.enabled` | `boolean` | `false` | Enable log forwarding (Env: `WTC_LOG_FORWARD_ENABLED`) |
| `logging.forward.host` | `string` | `""` | Log forwarder hostname (Env: `WTC_LOG_FORWARD_HOST`, CLI: `--log-forward (hos... |
| `logging.forward.port` | `integer` (min: 1, max: 65535) | `0` | Log forwarder port (Env: `WTC_LOG_FORWARD_PORT`) |
| `logging.forward.type` | `string` (`elastic`, `graylog`, `syslog`, ``) | `""` | Log forwarder type (Env: `WTC_LOG_FORWARD_TYPE`, CLI: `--log-forward-type`) |

### sqlite

SQLite configuration for local-only deployments

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sqlite.auto_init` | `boolean` | `true` | Automatically initialize database schema (Env: `WTC_DB_AUTO_INIT`) |
| `sqlite.db_path` | `string` | `"/var/lib/water-controller/wtc.db"` | SQLite database file path (Env: `WTC_DB_PATH`) |
| `sqlite.echo` | `boolean` | `false` | Echo SQL queries for debugging (Env: `WTC_DB_ECHO`) |

### system

System-wide settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `system.config_dir` | `string` | `"/etc/water-controller"` | Directory for configuration files (Env: `WTC_CONFIG_DIR`, CLI: `--config-dir`) |
| `system.data_dir` | `string` | `"/var/lib/water-controller"` | Directory for persistent data storage (Env: `WTC_DATA_DIR`) |
| `system.install_dir` | `string` | `"/opt/water-controller"` | Installation directory (Env: `WTC_INSTALL_DIR`) |
| `system.name` | `string` (max 64 chars) | `"Water Treatment Controller"` | Human-readable system name (Env: `WTC_SYSTEM_NAME`) |
| `system.version` | `string` | `"0.0.1"` | Controller version string (*read-only*) |

---

## Data Historian Configuration

Configuration for time-series data collection, compression, and storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_path` | `string` | `"/var/lib/water-controller/historian.db"` | SQLite historian database path (for local storage) (Env: `WTC_HISTORIAN_DB`) |
| `enabled` | `boolean` | `true` | Enable historian data collection (Env: `WTC_HISTORIAN_ENABLED`) |

### compression

Data compression settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `compression.default_algorithm` | `string` (`none`, `swinging_door`, `boxcar`, `deadband`) | `"swinging_door"` | Default compression algorithm (SDT is industry standard) |
| `compression.swinging_door_deviation` | `number` (min: 0.0, max: 10.0) | `0.5` | Swinging door compression deviation percentage (Unit: percent) |

### limits

Historian limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.buffer_size` | `integer` (min: 100, max: 100000) | `1000` | In-memory buffer size per tag before flush |
| `limits.max_samples_per_tag` | `integer` (min: 1000, max: 100000000) | `1000000` | Maximum samples stored per tag (prevents unbounded growth) (Env: `WTC_HISTORI... |
| `limits.max_tags` | `integer` (min: 1, max: 100000) | `1024` | Maximum number of historian tags |

### performance

Performance tuning

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `performance.async_writes` | `boolean` | `true` | Use asynchronous database writes |
| `performance.batch_size` | `integer` (min: 1, max: 10000) | `100` | Number of samples to batch before writing |
| `performance.flush_interval_ms` | `integer` (min: 100, max: 60000) | `5000` | Maximum time between buffer flushes (Unit: milliseconds) |

### retention

Data retention settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retention.auto_purge` | `boolean` | `true` | Automatically purge data older than retention period |
| `retention.days` | `integer` (min: 1, max: 36500) | `365` | Number of days to retain historical data (Env: `WTC_HISTORIAN_RETENTION_DAYS`) |
| `retention.purge_interval_hours` | `integer` (min: 1, max: 168) | `24` | Interval between purge operations (Unit: hours) |

### sampling

Default sampling settings for new tags

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sampling.default_deadband` | `number` (min: 0.0, max: 100.0) | `0.1` | Default deadband percentage (change threshold to record) (Unit: percent) |
| `sampling.default_rate_ms` | `integer` (min: 100, max: 3600000) | `1000` | Default sample rate for new historian tags (Unit: milliseconds) |

### timescale

TimescaleDB configuration for scalable time-series storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timescale.database` | `string` | `"wtc_historian"` | TimescaleDB database name (Env: `WTC_TIMESCALE_DB`) |
| `timescale.enabled` | `boolean` | `false` | Use TimescaleDB instead of SQLite (Env: `WTC_TIMESCALE_ENABLED`) |
| `timescale.host` | `string` | `"localhost"` | TimescaleDB server hostname (Env: `WTC_TIMESCALE_HOST`) |
| `timescale.password` | `string` | `"wtc_password"` | TimescaleDB password (Env: `WTC_TIMESCALE_PASSWORD`, **SENSITIVE**) |
| `timescale.port` | `integer` (min: 1, max: 65535) | `5432` | TimescaleDB server port (Env: `WTC_TIMESCALE_PORT`) |
| `timescale.user` | `string` | `"wtc"` | TimescaleDB username (Env: `WTC_TIMESCALE_USER`) |

---

## Modbus Gateway Configuration

PROFINET to Modbus TCP/RTU protocol bridge configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable Modbus gateway (Env: `WTC_MODBUS_ENABLED`) |

### downstream

Downstream Modbus client configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `downstream.default_poll_interval_ms` | `integer` (min: 100, max: 60000) | `1000` | Default polling interval for downstream devices (Unit: milliseconds) |
| `downstream.default_timeout_ms` | `integer` (min: 100, max: 30000) | `1000` | Default timeout for downstream device communication (Unit: milliseconds) |
| `downstream.max_devices` | `integer` (min: 0, max: 16) | `16` | Maximum downstream devices |
| `downstream.retry_count` | `integer` (min: 0, max: 10) | `3` | Number of retries on communication failure |

### register_map

Register mapping configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `register_map.actuator_base_address` | `integer` (min: 0, max: 65535) | `1000` | Base address for actuator registers |
| `register_map.auto_generate` | `boolean` | `true` | Automatically generate register map from RTU data |
| `register_map.map_file` | `string` (max 256 chars) | `""` | Custom register map file (JSON) |
| `register_map.sensor_base_address` | `integer` (min: 0, max: 65535) | `0` | Base address for sensor registers |
| `register_map.status_base_address` | `integer` (min: 0, max: 65535) | `2000` | Base address for status registers |

### server

Modbus server configuration (exposes PROFINET data)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

#### server.tcp

Modbus TCP server settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server.tcp.bind_address` | `string` (ipv4) | `"0.0.0.0"` | TCP bind address |
| `server.tcp.enabled` | `boolean` | `true` | Enable Modbus TCP server (Env: `WTC_MODBUS_TCP_ENABLED`) |
| `server.tcp.max_connections` | `integer` (min: 1, max: 100) | `10` | Maximum concurrent TCP connections |
| `server.tcp.port` | `integer` (min: 1, max: 65535) | `502` | Modbus TCP listen port (Env: `WTC_MODBUS_TCP_PORT`) |

#### server.rtu

Modbus RTU server settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server.rtu.baud_rate` | `integer` (`1200`, `2400`, `4800`, `9600`, `19200`, `38400`, `57600`, `115200`) | `9600` | Serial baud rate (Env: `WTC_MODBUS_RTU_BAUD`) |
| `server.rtu.data_bits` | `integer` (`7`, `8`) | `8` | Serial data bits |
| `server.rtu.device` | `string` (max 64 chars) | `""` | Serial device path (e.g., /dev/ttyUSB0) (Env: `WTC_MODBUS_RTU_DEVICE`) |
| `server.rtu.enabled` | `boolean` | `false` | Enable Modbus RTU server (Env: `WTC_MODBUS_RTU_ENABLED`) |
| `server.rtu.parity` | `string` (`N`, `E`, `O`) | `"N"` | Serial parity (None, Even, Odd) |
| `server.rtu.slave_address` | `integer` (min: 1, max: 247) | `1` | RTU slave address (Env: `WTC_MODBUS_SLAVE_ADDR`) |
| `server.rtu.stop_bits` | `integer` (`1`, `2`) | `1` | Serial stop bits |

### timing

Modbus timing configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing.inter_frame_delay_ms` | `integer` (min: 0, max: 1000) | `5` | Delay between frames (for RTU compliance) (Unit: milliseconds) |
| `timing.response_timeout_ms` | `integer` (min: 50, max: 10000) | `500` | Response timeout for requests (Unit: milliseconds) |
| `timing.turnaround_delay_ms` | `integer` (min: 0, max: 1000) | `50` | Turnaround delay after response (Unit: milliseconds) |

---

## PROFINET IO Controller Configuration

Configuration for PROFINET RT Class 1 communication with RTU devices

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cycle_time_us` | `integer` (min: 31250, max: 4000000) | `1000000` | PROFINET cycle time (minimum 31.25us, typically 1ms for RT Class 1) (Unit: mi... |
| `interface` | `string` (max 32 chars) | `"eth0"` | Network interface for PROFINET communication (Env: `WTC_INTERFACE`, CLI: `-i,... |
| `reduction_ratio` | `integer` (min: 1, max: 512) | `1` | Reduction ratio for actual cycle time |
| `send_clock_factor` | `integer` (min: 1, max: 128) | `32` | Send clock factor (32 = 1ms base cycle) |
| `socket_priority` | `integer` (min: 0, max: 7) | `6` | Socket priority for QoS (0-7, 6 recommended for RT) |
| `use_raw_sockets` | `boolean` | `true` | Use raw sockets for RT frames (requires CAP_NET_RAW) |

### authority

Authority handoff protocol settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `authority.handoff_timeout_ms` | `integer` (min: 1000, max: 30000) | `5000` | Maximum time to wait for authority handoff acknowledgment (Unit: milliseconds) |
| `authority.stale_command_threshold_ms` | `integer` (min: 100, max: 10000) | `1000` | Commands older than this are rejected during authority transfer (Unit: millis... |

### controller

Controller identity settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `controller.device_id` | `integer` (min: 0, max: 65535) | `1` | PROFINET device ID |
| `controller.gateway` | `string` (ipv4) | `""` | Default gateway (optional) |
| `controller.ip_address` | `string` (ipv4) | `""` | Controller IP address (auto-detect if empty) |
| `controller.mac_address` | `string` | `""` | Controller MAC address (auto-detect if empty) |
| `controller.station_name` | `string` (max 64 chars) | `"wtc-controller"` | Controller station name (DNS compatible) (Env: `WTC_STATION_NAME`) |
| `controller.subnet_mask` | `string` (ipv4) | `"255.255.255.0"` | Network subnet mask |
| `controller.vendor_id` | `integer` (min: 0, max: 65535) | `4660` | PROFINET vendor ID (0x1234) |

### discovery

DCP discovery settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `discovery.auto_discover` | `boolean` | `true` | Automatically discover RTUs on startup |
| `discovery.periodic_scan` | `boolean` | `false` | Periodically scan for new devices |
| `discovery.scan_interval_sec` | `integer` (min: 60, max: 3600) | `300` | Interval between periodic discovery scans (Unit: seconds) |
| `discovery.timeout_ms` | `integer` (min: 1000, max: 30000) | `5000` | DCP discovery response timeout (Env: `WTC_DCP_DISCOVERY_MS`, Unit: milliseconds) |

### limits

PROFINET stack limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.max_api` | `integer` | `256` | Maximum Application Process Identifiers |
| `limits.max_ar` | `integer` | `256` | Maximum Application Relationships |
| `limits.max_iocr` | `integer` | `64` | Maximum IO Communication Relationships per AR |
| `limits.min_cycle_time_us` | `integer` | `31250` | Minimum PROFINET cycle time (Unit: microseconds) |

### timing

Timing and watchdog settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing.command_timeout_ms` | `integer` (min: 100, max: 10000) | `3000` | Command execution timeout (Env: `WTC_COMMAND_TIMEOUT_MS`, Unit: milliseconds) |
| `timing.reconnect_delay_ms` | `integer` (min: 1000, max: 60000) | `5000` | Delay before reconnection attempt (Unit: milliseconds) |
| `timing.watchdog_ms` | `integer` (min: 100, max: 60000) | `3000` | Device watchdog timeout (Unit: milliseconds) |

---

## Web API and HMI Configuration

Configuration for FastAPI REST API, WebSocket streaming, and React HMI

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

### api

FastAPI backend configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api.api_only` | `boolean` | `false` | Run API only (no UI serving) (Env: `WTC_API_ONLY`) |
| `api.cors_origins` | `string` | `""` | Comma-separated list of allowed CORS origins (Env: `WTC_CORS_ORIGINS`) |
| `api.debug` | `boolean` | `false` | Enable API debug mode (Env: `WTC_API_DEBUG`) |
| `api.host` | `string` | `"0.0.0.0"` | API server bind address (Env: `WTC_API_HOST`) |
| `api.port` | `integer` (min: 1, max: 65535) | `8000` | API server port (Env: `WTC_API_PORT`, CLI: `-p, --port`) |
| `api.workers` | `integer` (min: 1, max: 32) | `4` | Number of API worker processes |

### authentication

Authentication configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `authentication.ad_domain` | `string` | `""` | Active Directory domain (Env: `WTC_AD_DOMAIN`) |
| `authentication.ad_enabled` | `boolean` | `false` | Enable Active Directory authentication (Env: `WTC_AD_ENABLED`) |
| `authentication.ad_server` | `string` | `""` | Active Directory server (Env: `WTC_AD_SERVER`) |
| `authentication.enabled` | `boolean` | `true` | Enable authentication (Env: `WTC_AUTH_ENABLED`) |
| `authentication.max_sessions_per_user` | `integer` (min: 1, max: 100) | `5` | Maximum concurrent sessions per user |
| `authentication.session_timeout_minutes` | `integer` (min: 5, max: 1440) | `60` | Session timeout (Unit: minutes) |

### circuit_breaker

Circuit breaker for API resilience

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `circuit_breaker.failure_threshold` | `integer` (min: 1, max: 100) | `5` | Failures before opening circuit (Env: `WTC_CB_FAILURE_THRESHOLD`) |
| `circuit_breaker.reset_timeout_seconds` | `integer` (min: 1, max: 600) | `30` | Time before attempting reset (Env: `WTC_CB_RESET_TIMEOUT`, Unit: seconds) |
| `circuit_breaker.success_threshold` | `integer` (min: 1, max: 100) | `3` | Successes required to close circuit (Env: `WTC_CB_SUCCESS_THRESHOLD`) |

### polling

Fallback polling configuration (when WebSocket unavailable)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `polling.default_interval_ms` | `integer` (min: 1000, max: 60000) | `5000` | Default polling interval (Env: `WTC_POLL_INTERVAL_MS`, Unit: milliseconds) |
| `polling.many_rtus_interval_ms` | `integer` (min: 1000, max: 120000) | `10000` | Reduced polling interval when many RTUs (Env: `WTC_MANY_RTUS_POLL_MS`, Unit: ... |
| `polling.many_rtus_threshold` | `integer` (min: 1, max: 100) | `10` | RTU count to trigger reduced polling (Env: `WTC_MANY_RTUS_THRESHOLD`) |

### security

Security settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `security.csrf_enabled` | `boolean` | `true` | Enable CSRF protection |
| `security.rate_limit_requests_per_minute` | `integer` (min: 10, max: 10000) | `100` | API rate limit per IP |
| `security.secure_cookies` | `boolean` | `true` | Use secure cookies (HTTPS only) |

### timeouts

API timeout configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeouts.command_ms` | `integer` (min: 100, max: 30000) | `3000` | Command execution timeout (Env: `WTC_COMMAND_TIMEOUT_MS`, Unit: milliseconds) |
| `timeouts.db_query_ms` | `integer` (min: 100, max: 60000) | `5000` | Database query timeout (Env: `WTC_DB_QUERY_TIMEOUT_MS`, Unit: milliseconds) |
| `timeouts.dcp_discovery_ms` | `integer` (min: 1000, max: 30000) | `5000` | PROFINET DCP discovery timeout (Env: `WTC_DCP_DISCOVERY_MS`, Unit: milliseconds) |

### ui

Web UI configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ui.api_url` | `string` | `""` | API URL for UI to connect to (Env: `NEXT_PUBLIC_API_URL`) |
| `ui.dist_dir` | `string` | `""` | Static UI distribution directory (Env: `WTC_UI_DIST_DIR`) |
| `ui.port` | `integer` (min: 1, max: 65535) | `3000` | UI server port (when running separately) (Env: `WTC_UI_PORT`) |

### websocket

WebSocket streaming configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `websocket.heartbeat_interval_ms` | `integer` (min: 1000, max: 60000) | `30000` | WebSocket heartbeat interval (Unit: milliseconds) |
| `websocket.reconnect_base_ms` | `integer` (min: 100, max: 30000) | `1000` | Base reconnection interval (exponential backoff) (Env: `WTC_WS_RECONNECT_MS`,... |
| `websocket.reconnect_max_attempts` | `integer` (min: 1, max: 100) | `10` | Maximum reconnection attempts (Env: `WTC_WS_RECONNECT_ATTEMPTS`) |

---

## Environment Variable Quick Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `""` | API URL for UI to connect to |
| `WTC_AD_DOMAIN` | `""` | Active Directory domain |
| `WTC_AD_ENABLED` | `false` | Enable Active Directory authentication |
| `WTC_AD_SERVER` | `""` | Active Directory server |
| `WTC_ALARMS_ENABLED` | `true` | Enable alarm management |
| `WTC_API_DEBUG` | `false` | Enable API debug mode |
| `WTC_API_HOST` | `"0.0.0.0"` | API server bind address |
| `WTC_API_ONLY` | `false` | Run API only (no UI serving) |
| `WTC_API_PORT` | `8000` | API server port |
| `WTC_AUTH_ENABLED` | `true` | Enable authentication |
| `WTC_CB_FAILURE_THRESHOLD` | `5` | Failures before opening circuit |
| `WTC_CB_RESET_TIMEOUT` | `30` | Time before attempting reset |
| `WTC_CB_SUCCESS_THRESHOLD` | `3` | Successes required to close circuit |
| `WTC_COMMAND_TIMEOUT_MS` | `3000` | Command execution timeout |
| `WTC_COMMAND_TIMEOUT_MS` | `3000` | Command execution timeout |
| `WTC_CONFIG_DIR` | `"/etc/water-controller"` | Directory for configuration files |
| `WTC_CORS_ORIGINS` | `""` | Comma-separated list of allowed CORS origins |
| `WTC_CYCLE_TIME` | `1000` | Main cycle time for data collection and control |
| `WTC_DATA_DIR` | `"/var/lib/water-controller"` | Directory for persistent data storage |
| `WTC_DB_AUTO_INIT` | `true` | Automatically initialize database schema |
| `WTC_DB_ECHO` | `false` | Echo SQL queries for debugging |
| `WTC_DB_HOST` | `"localhost"` | PostgreSQL server hostname |
| `WTC_DB_NAME` | `"water_controller"` | Database name |
| `WTC_DB_PASSWORD` | `""` | Database password |
| `WTC_DB_PATH` | `"/var/lib/water-controller/wtc.db"` | SQLite database file path |
| `WTC_DB_PORT` | `5432` | PostgreSQL server port |
| `WTC_DB_QUERY_TIMEOUT_MS` | `5000` | Database query timeout |
| `WTC_DB_USER` | `"wtc"` | Database username |
| `WTC_DCP_DISCOVERY_MS` | `5000` | DCP discovery response timeout |
| `WTC_DCP_DISCOVERY_MS` | `5000` | PROFINET DCP discovery timeout |
| `WTC_DEBUG` | `false` | Enable debug mode |
| `WTC_FAILOVER_ENABLED` | `true` | Enable automatic failover handling |
| `WTC_FAILOVER_MODE` | `"auto"` | Failover mode |
| `WTC_FAILOVER_TIMEOUT_MS` | `5000` | Time to wait before declaring RTU failed |
| `WTC_HISTORIAN_DB` | `"/var/lib/water-controller/historian.db"` | SQLite historian database path (for local storage) |
| `WTC_HISTORIAN_ENABLED` | `true` | Enable historian data collection |
| `WTC_HISTORIAN_MAX_SAMPLES` | `1000000` | Maximum samples stored per tag (prevents unbounded growth) |
| `WTC_HISTORIAN_RETENTION_DAYS` | `365` | Number of days to retain historical data |
| `WTC_INSTALL_DIR` | `"/opt/water-controller"` | Installation directory |
| `WTC_INTERFACE` | `"eth0"` | Network interface for PROFINET communication |
| `WTC_LOG_DIR` | `"/var/log/water-controller"` | Directory for log files |
| `WTC_LOG_FILE` | `""` | Log file path (empty for stderr only) |
| `WTC_LOG_FORWARD_ENABLED` | `false` | Enable log forwarding |
| `WTC_LOG_FORWARD_HOST` | `""` | Log forwarder hostname |
| `WTC_LOG_FORWARD_PORT` | `0` | Log forwarder port |
| `WTC_LOG_FORWARD_TYPE` | `""` | Log forwarder type |
| `WTC_LOG_LEVEL` | `"INFO"` | Minimum log level to output |
| `WTC_LOG_STRUCTURED` | `false` | Enable structured JSON logging for log aggregators |
| `WTC_MANY_RTUS_POLL_MS` | `10000` | Reduced polling interval when many RTUs |
| `WTC_MANY_RTUS_THRESHOLD` | `10` | RTU count to trigger reduced polling |
| `WTC_MODBUS_ENABLED` | `true` | Enable Modbus gateway |
| `WTC_MODBUS_RTU_BAUD` | `9600` | Serial baud rate |
| `WTC_MODBUS_RTU_DEVICE` | `""` | Serial device path (e.g., /dev/ttyUSB0) |
| `WTC_MODBUS_RTU_ENABLED` | `false` | Enable Modbus RTU server |
| `WTC_MODBUS_SLAVE_ADDR` | `1` | RTU slave address |
| `WTC_MODBUS_TCP_ENABLED` | `true` | Enable Modbus TCP server |
| `WTC_MODBUS_TCP_PORT` | `502` | Modbus TCP listen port |
| `WTC_POLL_INTERVAL_MS` | `5000` | Default polling interval |
| `WTC_SHM_NAME` | `"/wtc_shared_memory"` | Shared memory segment name |
| `WTC_SHM_READ_TIMEOUT_MS` | `100` | Timeout for reading shared memory |
| `WTC_SIMULATION_MODE` | `false` | Run in simulation mode without real hardware |
| `WTC_SMTP_HOST` | `""` | SMTP server hostname |
| `WTC_STARTUP_MODE` | `""` | Startup mode override |
| `WTC_STATION_NAME` | `"wtc-controller"` | Controller station name (DNS compatible) |
| `WTC_SYSTEM_NAME` | `"Water Treatment Controller"` | Human-readable system name |
| `WTC_TIMESCALE_DB` | `"wtc_historian"` | TimescaleDB database name |
| `WTC_TIMESCALE_ENABLED` | `false` | Use TimescaleDB instead of SQLite |
| `WTC_TIMESCALE_HOST` | `"localhost"` | TimescaleDB server hostname |
| `WTC_TIMESCALE_PASSWORD` | `"wtc_password"` | TimescaleDB password |
| `WTC_TIMESCALE_PORT` | `5432` | TimescaleDB server port |
| `WTC_TIMESCALE_USER` | `"wtc"` | TimescaleDB username |
| `WTC_UI_DIST_DIR` | `""` | Static UI distribution directory |
| `WTC_UI_PORT` | `3000` | UI server port (when running separately) |
| `WTC_WS_RECONNECT_ATTEMPTS` | `10` | Maximum reconnection attempts |
| `WTC_WS_RECONNECT_MS` | `1000` | Base reconnection interval (exponential backoff) |