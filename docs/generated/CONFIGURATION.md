<!--
  AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

  Generated from: schemas/config/*.schema.yaml
  Generated at: 2025-12-30 19:16:59 UTC
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
| `enabled` | `boolean` | `true` | Enable alarm management ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `enabled`

Enable alarm management

- **Environment variable**: `WTC_ALARMS_ENABLED`

</details>

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
| `isa_18_2.max_shelve_duration_hours` | `integer` (min: 1, max: 168) | `24` | Maximum duration an alarm can be shelved ℹ️ |
| `isa_18_2.out_of_service_logging` | `boolean` | `true` | Log all out-of-service state changes |
| `isa_18_2.rationalization_required` | `boolean` | `false` | Require consequence and response for each alarm rule |
| `isa_18_2.require_acknowledgment` | `boolean` | `true` | Require operator acknowledgment for alarms |
| `isa_18_2.shelving_enabled` | `boolean` | `true` | Allow alarm shelving (temporary disable with audit) |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `isa_18_2.max_shelve_duration_hours`

Maximum duration an alarm can be shelved

- **Unit**: hours

</details>

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
| `notifications.email.smtp_host` | `string` | `""` | SMTP server hostname ℹ️ |
| `notifications.email.smtp_port` | `integer` (min: 1, max: 65535) | `587` | SMTP server port |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `notifications.email.smtp_host`

SMTP server hostname

- **Environment variable**: `WTC_SMTP_HOST`

</details>

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
| `suppression.max_duration_minutes` | `integer` (min: 1, max: 1440) | `60` | Maximum suppression duration ℹ️ |
| `suppression.require_reason` | `boolean` | `true` | Require reason when suppressing alarms |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `suppression.max_duration_minutes`

Maximum suppression duration

- **Unit**: minutes

</details>

---

## Water Treatment Controller Configuration

Main configuration for the Water Treatment PROFINET IO Controller

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

### cycle

Main control cycle timing

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cycle.scan_rate_ms` | `integer` (min: 10, max: 10000) | `100` | Control engine scan rate for PID/interlock evaluation ℹ️ |
| `cycle.time_ms` | `integer` (min: 100, max: 60000) | `1000` | Main cycle time for data collection and control ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `cycle.scan_rate_ms`

Control engine scan rate for PID/interlock evaluation

- **Unit**: milliseconds

#### `cycle.time_ms`

Main cycle time for data collection and control

- **Environment variable**: `WTC_CYCLE_TIME`
- **CLI argument**: `-t, --cycle`
- **Unit**: milliseconds

</details>

### daemon

Daemon/service mode settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `daemon.enabled` | `boolean` | `false` | Run as a background daemon ℹ️ |
| `daemon.pid_file` | `string` | `"/var/run/water-controller.pid"` | PID file location when running as daemon |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `daemon.enabled`

Run as a background daemon

- **CLI argument**: `-d, --daemon`

</details>

### database

PostgreSQL database configuration for persistent storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database.connection_timeout_ms` | `integer` (min: 1000, max: 60000) | `5000` | Connection timeout ℹ️ |
| `database.enabled` | `boolean` | `true` | Enable database persistence ℹ️ |
| `database.host` | `string` | `"localhost"` | PostgreSQL server hostname ℹ️ |
| `database.max_connections` | `integer` (min: 1, max: 100) | `5` | Maximum database connection pool size |
| `database.name` | `string` | `"water_controller"` | Database name ℹ️ |
| `database.password` | `string` | `""` | Database password ℹ️ |
| `database.port` | `integer` (min: 1, max: 65535) | `5432` | PostgreSQL server port ℹ️ |
| `database.use_ssl` | `boolean` | `false` | Use SSL for database connections |
| `database.user` | `string` | `"wtc"` | Database username ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `database.connection_timeout_ms`

Connection timeout

- **Unit**: milliseconds

#### `database.enabled`

Enable database persistence

- **CLI argument**: `--no-db (disables)`

#### `database.host`

PostgreSQL server hostname

- **Environment variable**: `WTC_DB_HOST`
- **CLI argument**: `--db-host`

#### `database.name`

Database name

- **Environment variable**: `WTC_DB_NAME`
- **CLI argument**: `--db-name`

#### `database.password`

Database password

- **Environment variable**: `WTC_DB_PASSWORD`
- **CLI argument**: `--db-password`
- ⚠️ **Sensitive** - This value should be kept secret

#### `database.port`

PostgreSQL server port

- **Environment variable**: `WTC_DB_PORT`
- **CLI argument**: `--db-port`

#### `database.user`

Database username

- **Environment variable**: `WTC_DB_USER`
- **CLI argument**: `--db-user`

</details>

### debug

Debug and development settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `debug.enabled` | `boolean` | `false` | Enable debug mode ℹ️ |
| `debug.simulation_mode` | `boolean` | `false` | Run in simulation mode without real hardware ℹ️ |
| `debug.startup_mode` | `string` (``, `development`, `testing`, `production`) | `""` | Startup mode override ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `debug.enabled`

Enable debug mode

- **Environment variable**: `WTC_DEBUG`

#### `debug.simulation_mode`

Run in simulation mode without real hardware

- **Environment variable**: `WTC_SIMULATION_MODE`

#### `debug.startup_mode`

Startup mode override

- **Environment variable**: `WTC_STARTUP_MODE`

</details>

### failover

RTU failover and redundancy settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `failover.enabled` | `boolean` | `true` | Enable automatic failover handling ℹ️ |
| `failover.heartbeat_interval_ms` | `integer` (min: 100, max: 10000) | `1000` | RTU health check interval ℹ️ |
| `failover.max_retries` | `integer` (min: 0, max: 10) | `3` | Number of reconnection attempts before failover |
| `failover.mode` | `string` (`manual`, `auto`, `hot_standby`) | `"auto"` | Failover mode ℹ️ |
| `failover.timeout_ms` | `integer` (min: 1000, max: 60000) | `5000` | Time to wait before declaring RTU failed ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `failover.enabled`

Enable automatic failover handling

- **Environment variable**: `WTC_FAILOVER_ENABLED`

#### `failover.heartbeat_interval_ms`

RTU health check interval

- **Unit**: milliseconds

#### `failover.mode`

Failover mode

- **Environment variable**: `WTC_FAILOVER_MODE`

#### `failover.timeout_ms`

Time to wait before declaring RTU failed

- **Environment variable**: `WTC_FAILOVER_TIMEOUT_MS`
- **Unit**: milliseconds

</details>

### ipc

Inter-process communication settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ipc.shm_name` | `string` | `"/wtc_shared_memory"` | Shared memory segment name ℹ️ |
| `ipc.shm_read_timeout_ms` | `integer` (min: 10, max: 5000) | `100` | Timeout for reading shared memory ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `ipc.shm_name`

Shared memory segment name

- **Environment variable**: `WTC_SHM_NAME`

#### `ipc.shm_read_timeout_ms`

Timeout for reading shared memory

- **Environment variable**: `WTC_SHM_READ_TIMEOUT_MS`
- **Unit**: milliseconds

</details>

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
| `logging.file` | `string` | `""` | Log file path (empty for stderr only) ℹ️ |
| `logging.level` | `string` (`TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`) | `"INFO"` | Minimum log level to output ℹ️ |
| `logging.log_dir` | `string` | `"/var/log/water-controller"` | Directory for log files ℹ️ |
| `logging.structured` | `boolean` | `false` | Enable structured JSON logging for log aggregators ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `logging.file`

Log file path (empty for stderr only)

- **Environment variable**: `WTC_LOG_FILE`
- **CLI argument**: `-l, --log`

#### `logging.level`

Minimum log level to output

- **Environment variable**: `WTC_LOG_LEVEL`
- **CLI argument**: `-v, --verbose (decreases level) / -q, --quiet (increases level)`

#### `logging.log_dir`

Directory for log files

- **Environment variable**: `WTC_LOG_DIR`

#### `logging.structured`

Enable structured JSON logging for log aggregators

- **Environment variable**: `WTC_LOG_STRUCTURED`

</details>

#### logging.forward

Log forwarding to external systems (Elastic, Graylog, Syslog)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `logging.forward.enabled` | `boolean` | `false` | Enable log forwarding ℹ️ |
| `logging.forward.host` | `string` | `""` | Log forwarder hostname ℹ️ |
| `logging.forward.port` | `integer` (min: 1, max: 65535) | `0` | Log forwarder port ℹ️ |
| `logging.forward.type` | `string` (`elastic`, `graylog`, `syslog`, ``) | `""` | Log forwarder type ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `logging.forward.enabled`

Enable log forwarding

- **Environment variable**: `WTC_LOG_FORWARD_ENABLED`

#### `logging.forward.host`

Log forwarder hostname

- **Environment variable**: `WTC_LOG_FORWARD_HOST`
- **CLI argument**: `--log-forward (host:port format)`

#### `logging.forward.port`

Log forwarder port

- **Environment variable**: `WTC_LOG_FORWARD_PORT`

#### `logging.forward.type`

Log forwarder type

- **Environment variable**: `WTC_LOG_FORWARD_TYPE`
- **CLI argument**: `--log-forward-type`

</details>

### sqlite

SQLite configuration for local-only deployments

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sqlite.auto_init` | `boolean` | `true` | Automatically initialize database schema ℹ️ |
| `sqlite.db_path` | `string` | `"/var/lib/water-controller/wtc.db"` | SQLite database file path ℹ️ |
| `sqlite.echo` | `boolean` | `false` | Echo SQL queries for debugging ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `sqlite.auto_init`

Automatically initialize database schema

- **Environment variable**: `WTC_DB_AUTO_INIT`

#### `sqlite.db_path`

SQLite database file path

- **Environment variable**: `WTC_DB_PATH`

#### `sqlite.echo`

Echo SQL queries for debugging

- **Environment variable**: `WTC_DB_ECHO`

</details>

### system

System-wide settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `system.config_dir` | `string` | `"/etc/water-controller"` | Directory for configuration files ℹ️ |
| `system.data_dir` | `string` | `"/var/lib/water-controller"` | Directory for persistent data storage ℹ️ |
| `system.install_dir` | `string` | `"/opt/water-controller"` | Installation directory ℹ️ |
| `system.name` | `string` (max 64 chars) | `"Water Treatment Controller"` | Human-readable system name ℹ️ |
| `system.version` | `string` | `"0.0.1"` | Controller version string ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `system.config_dir`

Directory for configuration files

- **Environment variable**: `WTC_CONFIG_DIR`
- **CLI argument**: `--config-dir`

#### `system.data_dir`

Directory for persistent data storage

- **Environment variable**: `WTC_DATA_DIR`

#### `system.install_dir`

Installation directory

- **Environment variable**: `WTC_INSTALL_DIR`

#### `system.name`

Human-readable system name

- **Environment variable**: `WTC_SYSTEM_NAME`

#### `system.version`

Controller version string

- *Read-only* - Cannot be modified at runtime

</details>

---

## Data Historian Configuration

Configuration for time-series data collection, compression, and storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_path` | `string` | `"/var/lib/water-controller/historian.db"` | SQLite historian database path (for local storage) ℹ️ |
| `enabled` | `boolean` | `true` | Enable historian data collection ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `database_path`

SQLite historian database path (for local storage)

- **Environment variable**: `WTC_HISTORIAN_DB`

#### `enabled`

Enable historian data collection

- **Environment variable**: `WTC_HISTORIAN_ENABLED`

</details>

### compression

Data compression settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `compression.default_algorithm` | `string` (`none`, `swinging_door`, `boxcar`, `deadband`) | `"swinging_door"` | Default compression algorithm (SDT is industry standard) |
| `compression.swinging_door_deviation` | `number` (min: 0.0, max: 10.0) | `0.5` | Swinging door compression deviation percentage ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `compression.swinging_door_deviation`

Swinging door compression deviation percentage

- **Unit**: percent

</details>

### limits

Historian limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.buffer_size` | `integer` (min: 100, max: 100000) | `1000` | In-memory buffer size per tag before flush |
| `limits.max_samples_per_tag` | `integer` (min: 1000, max: 100000000) | `1000000` | Maximum samples stored per tag (prevents unbounded gro... ℹ️ |
| `limits.max_tags` | `integer` (min: 1, max: 100000) | `1024` | Maximum number of historian tags |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `limits.max_samples_per_tag`

Maximum samples stored per tag (prevents unbounded growth)

- **Environment variable**: `WTC_HISTORIAN_MAX_SAMPLES`

</details>

### performance

Performance tuning

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `performance.async_writes` | `boolean` | `true` | Use asynchronous database writes |
| `performance.batch_size` | `integer` (min: 1, max: 10000) | `100` | Number of samples to batch before writing |
| `performance.flush_interval_ms` | `integer` (min: 100, max: 60000) | `5000` | Maximum time between buffer flushes ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `performance.flush_interval_ms`

Maximum time between buffer flushes

- **Unit**: milliseconds

</details>

### retention

Data retention settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retention.auto_purge` | `boolean` | `true` | Automatically purge data older than retention period |
| `retention.days` | `integer` (min: 1, max: 36500) | `365` | Number of days to retain historical data ℹ️ |
| `retention.purge_interval_hours` | `integer` (min: 1, max: 168) | `24` | Interval between purge operations ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `retention.days`

Number of days to retain historical data

- **Environment variable**: `WTC_HISTORIAN_RETENTION_DAYS`

#### `retention.purge_interval_hours`

Interval between purge operations

- **Unit**: hours

</details>

### sampling

Default sampling settings for new tags

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sampling.default_deadband` | `number` (min: 0.0, max: 100.0) | `0.1` | Default deadband percentage (change threshold to record) ℹ️ |
| `sampling.default_rate_ms` | `integer` (min: 100, max: 3600000) | `1000` | Default sample rate for new historian tags ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `sampling.default_deadband`

Default deadband percentage (change threshold to record)

- **Unit**: percent

#### `sampling.default_rate_ms`

Default sample rate for new historian tags

- **Unit**: milliseconds

</details>

### timescale

TimescaleDB configuration for scalable time-series storage

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timescale.database` | `string` | `"wtc_historian"` | TimescaleDB database name ℹ️ |
| `timescale.enabled` | `boolean` | `false` | Use TimescaleDB instead of SQLite ℹ️ |
| `timescale.host` | `string` | `"localhost"` | TimescaleDB server hostname ℹ️ |
| `timescale.password` | `string` | `"wtc_password"` | TimescaleDB password ℹ️ |
| `timescale.port` | `integer` (min: 1, max: 65535) | `5432` | TimescaleDB server port ℹ️ |
| `timescale.user` | `string` | `"wtc"` | TimescaleDB username ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `timescale.database`

TimescaleDB database name

- **Environment variable**: `WTC_TIMESCALE_DB`

#### `timescale.enabled`

Use TimescaleDB instead of SQLite

- **Environment variable**: `WTC_TIMESCALE_ENABLED`

#### `timescale.host`

TimescaleDB server hostname

- **Environment variable**: `WTC_TIMESCALE_HOST`

#### `timescale.password`

TimescaleDB password

- **Environment variable**: `WTC_TIMESCALE_PASSWORD`
- ⚠️ **Sensitive** - This value should be kept secret

#### `timescale.port`

TimescaleDB server port

- **Environment variable**: `WTC_TIMESCALE_PORT`

#### `timescale.user`

TimescaleDB username

- **Environment variable**: `WTC_TIMESCALE_USER`

</details>

---

## Modbus Gateway Configuration

PROFINET to Modbus TCP/RTU protocol bridge configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `boolean` | `true` | Enable Modbus gateway ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `enabled`

Enable Modbus gateway

- **Environment variable**: `WTC_MODBUS_ENABLED`

</details>

### downstream

Downstream Modbus client configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `downstream.default_poll_interval_ms` | `integer` (min: 100, max: 60000) | `1000` | Default polling interval for downstream devices ℹ️ |
| `downstream.default_timeout_ms` | `integer` (min: 100, max: 30000) | `1000` | Default timeout for downstream device communication ℹ️ |
| `downstream.max_devices` | `integer` (min: 0, max: 16) | `16` | Maximum downstream devices |
| `downstream.retry_count` | `integer` (min: 0, max: 10) | `3` | Number of retries on communication failure |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `downstream.default_poll_interval_ms`

Default polling interval for downstream devices

- **Unit**: milliseconds

#### `downstream.default_timeout_ms`

Default timeout for downstream device communication

- **Unit**: milliseconds

</details>

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
| `server.tcp.enabled` | `boolean` | `true` | Enable Modbus TCP server ℹ️ |
| `server.tcp.max_connections` | `integer` (min: 1, max: 100) | `10` | Maximum concurrent TCP connections |
| `server.tcp.port` | `integer` (min: 1, max: 65535) | `502` | Modbus TCP listen port ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `server.tcp.enabled`

Enable Modbus TCP server

- **Environment variable**: `WTC_MODBUS_TCP_ENABLED`

#### `server.tcp.port`

Modbus TCP listen port

- **Environment variable**: `WTC_MODBUS_TCP_PORT`

</details>

#### server.rtu

Modbus RTU server settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server.rtu.baud_rate` | `integer` (`1200`, `2400`, `4800`, `9600`, `19200`, `38400`, `57600`, `115200`) | `9600` | Serial baud rate ℹ️ |
| `server.rtu.data_bits` | `integer` (`7`, `8`) | `8` | Serial data bits |
| `server.rtu.device` | `string` (max 64 chars) | `""` | Serial device path (e.g., /dev/ttyUSB0) ℹ️ |
| `server.rtu.enabled` | `boolean` | `false` | Enable Modbus RTU server ℹ️ |
| `server.rtu.parity` | `string` (`N`, `E`, `O`) | `"N"` | Serial parity (None, Even, Odd) |
| `server.rtu.slave_address` | `integer` (min: 1, max: 247) | `1` | RTU slave address ℹ️ |
| `server.rtu.stop_bits` | `integer` (`1`, `2`) | `1` | Serial stop bits |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `server.rtu.baud_rate`

Serial baud rate

- **Environment variable**: `WTC_MODBUS_RTU_BAUD`

#### `server.rtu.device`

Serial device path (e.g., /dev/ttyUSB0)

- **Environment variable**: `WTC_MODBUS_RTU_DEVICE`

#### `server.rtu.enabled`

Enable Modbus RTU server

- **Environment variable**: `WTC_MODBUS_RTU_ENABLED`

#### `server.rtu.slave_address`

RTU slave address

- **Environment variable**: `WTC_MODBUS_SLAVE_ADDR`

</details>

### timing

Modbus timing configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing.inter_frame_delay_ms` | `integer` (min: 0, max: 1000) | `5` | Delay between frames (for RTU compliance) ℹ️ |
| `timing.response_timeout_ms` | `integer` (min: 50, max: 10000) | `500` | Response timeout for requests ℹ️ |
| `timing.turnaround_delay_ms` | `integer` (min: 0, max: 1000) | `50` | Turnaround delay after response ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `timing.inter_frame_delay_ms`

Delay between frames (for RTU compliance)

- **Unit**: milliseconds

#### `timing.response_timeout_ms`

Response timeout for requests

- **Unit**: milliseconds

#### `timing.turnaround_delay_ms`

Turnaround delay after response

- **Unit**: milliseconds

</details>

---

## PROFINET IO Controller Configuration

Configuration for PROFINET RT Class 1 communication with RTU devices

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cycle_time_us` | `integer` (min: 31250, max: 4000000) | `1000000` | PROFINET cycle time (minimum 31.25us, typically 1ms fo... ℹ️ |
| `interface` | `string` (max 32 chars) | `"eth0"` | Network interface for PROFINET communication ℹ️ |
| `reduction_ratio` | `integer` (min: 1, max: 512) | `1` | Reduction ratio for actual cycle time |
| `send_clock_factor` | `integer` (min: 1, max: 128) | `32` | Send clock factor (32 = 1ms base cycle) |
| `socket_priority` | `integer` (min: 0, max: 7) | `6` | Socket priority for QoS (0-7, 6 recommended for RT) |
| `use_raw_sockets` | `boolean` | `true` | Use raw sockets for RT frames (requires CAP_NET_RAW) |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `cycle_time_us`

PROFINET cycle time (minimum 31.25us, typically 1ms for RT Class 1)

- **Unit**: microseconds

#### `interface`

Network interface for PROFINET communication

- **Environment variable**: `WTC_INTERFACE`
- **CLI argument**: `-i, --interface`

</details>

### authority

Authority handoff protocol settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `authority.handoff_timeout_ms` | `integer` (min: 1000, max: 30000) | `5000` | Maximum time to wait for authority handoff acknowledgment ℹ️ |
| `authority.stale_command_threshold_ms` | `integer` (min: 100, max: 10000) | `1000` | Commands older than this are rejected during authority... ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `authority.handoff_timeout_ms`

Maximum time to wait for authority handoff acknowledgment

- **Unit**: milliseconds

#### `authority.stale_command_threshold_ms`

Commands older than this are rejected during authority transfer

- **Unit**: milliseconds

</details>

### controller

Controller identity settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `controller.device_id` | `integer` (min: 0, max: 65535) | `1` | PROFINET device ID |
| `controller.gateway` | `string` (ipv4) | `""` | Default gateway (optional) |
| `controller.ip_address` | `string` (ipv4) | `""` | Controller IP address (auto-detect if empty) |
| `controller.mac_address` | `string` | `""` | Controller MAC address (auto-detect if empty) |
| `controller.station_name` | `string` (max 64 chars) | `"wtc-controller"` | Controller station name (DNS compatible) ℹ️ |
| `controller.subnet_mask` | `string` (ipv4) | `"255.255.255.0"` | Network subnet mask |
| `controller.vendor_id` | `integer` (min: 0, max: 65535) | `4660` | PROFINET vendor ID (0x1234) |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `controller.station_name`

Controller station name (DNS compatible)

- **Environment variable**: `WTC_STATION_NAME`

</details>

### discovery

DCP discovery settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `discovery.auto_discover` | `boolean` | `true` | Automatically discover RTUs on startup |
| `discovery.periodic_scan` | `boolean` | `false` | Periodically scan for new devices |
| `discovery.scan_interval_sec` | `integer` (min: 60, max: 3600) | `300` | Interval between periodic discovery scans ℹ️ |
| `discovery.timeout_ms` | `integer` (min: 1000, max: 30000) | `5000` | DCP discovery response timeout ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `discovery.scan_interval_sec`

Interval between periodic discovery scans

- **Unit**: seconds

#### `discovery.timeout_ms`

DCP discovery response timeout

- **Environment variable**: `WTC_DCP_DISCOVERY_MS`
- **Unit**: milliseconds

</details>

### limits

PROFINET stack limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limits.max_api` | `integer` | `256` | Maximum Application Process Identifiers |
| `limits.max_ar` | `integer` | `256` | Maximum Application Relationships |
| `limits.max_iocr` | `integer` | `64` | Maximum IO Communication Relationships per AR |
| `limits.min_cycle_time_us` | `integer` | `31250` | Minimum PROFINET cycle time ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `limits.min_cycle_time_us`

Minimum PROFINET cycle time

- **Unit**: microseconds

</details>

### timing

Timing and watchdog settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing.command_timeout_ms` | `integer` (min: 100, max: 10000) | `3000` | Command execution timeout ℹ️ |
| `timing.reconnect_delay_ms` | `integer` (min: 1000, max: 60000) | `5000` | Delay before reconnection attempt ℹ️ |
| `timing.watchdog_ms` | `integer` (min: 100, max: 60000) | `3000` | Device watchdog timeout ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `timing.command_timeout_ms`

Command execution timeout

- **Environment variable**: `WTC_COMMAND_TIMEOUT_MS`
- **Unit**: milliseconds

#### `timing.reconnect_delay_ms`

Delay before reconnection attempt

- **Unit**: milliseconds

#### `timing.watchdog_ms`

Device watchdog timeout

- **Unit**: milliseconds

</details>

---

## Web API and HMI Configuration

Configuration for FastAPI REST API, WebSocket streaming, and React HMI

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|

### api

FastAPI backend configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api.api_only` | `boolean` | `false` | Run API only (no UI serving) ℹ️ |
| `api.cors_origins` | `string` | `""` | Comma-separated list of allowed CORS origins ℹ️ |
| `api.debug` | `boolean` | `false` | Enable API debug mode ℹ️ |
| `api.host` | `string` | `"0.0.0.0"` | API server bind address ℹ️ |
| `api.port` | `integer` (min: 1, max: 65535) | `8080` | API server port ℹ️ |
| `api.workers` | `integer` (min: 1, max: 32) | `4` | Number of API worker processes |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `api.api_only`

Run API only (no UI serving)

- **Environment variable**: `WTC_API_ONLY`

#### `api.cors_origins`

Comma-separated list of allowed CORS origins

- **Environment variable**: `WTC_CORS_ORIGINS`

#### `api.debug`

Enable API debug mode

- **Environment variable**: `WTC_API_DEBUG`

#### `api.host`

API server bind address

- **Environment variable**: `WTC_API_HOST`

#### `api.port`

API server port

- **Environment variable**: `WTC_API_PORT`
- **CLI argument**: `-p, --port`

</details>

### authentication

Authentication configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `authentication.ad_domain` | `string` | `""` | Active Directory domain ℹ️ |
| `authentication.ad_enabled` | `boolean` | `false` | Enable Active Directory authentication ℹ️ |
| `authentication.ad_server` | `string` | `""` | Active Directory server ℹ️ |
| `authentication.enabled` | `boolean` | `true` | Enable authentication ℹ️ |
| `authentication.max_sessions_per_user` | `integer` (min: 1, max: 100) | `5` | Maximum concurrent sessions per user |
| `authentication.session_timeout_minutes` | `integer` (min: 5, max: 1440) | `60` | Session timeout ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `authentication.ad_domain`

Active Directory domain

- **Environment variable**: `WTC_AD_DOMAIN`

#### `authentication.ad_enabled`

Enable Active Directory authentication

- **Environment variable**: `WTC_AD_ENABLED`

#### `authentication.ad_server`

Active Directory server

- **Environment variable**: `WTC_AD_SERVER`

#### `authentication.enabled`

Enable authentication

- **Environment variable**: `WTC_AUTH_ENABLED`

#### `authentication.session_timeout_minutes`

Session timeout

- **Unit**: minutes

</details>

### circuit_breaker

Circuit breaker for API resilience

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `circuit_breaker.failure_threshold` | `integer` (min: 1, max: 100) | `5` | Failures before opening circuit ℹ️ |
| `circuit_breaker.reset_timeout_seconds` | `integer` (min: 1, max: 600) | `30` | Time before attempting reset ℹ️ |
| `circuit_breaker.success_threshold` | `integer` (min: 1, max: 100) | `3` | Successes required to close circuit ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `circuit_breaker.failure_threshold`

Failures before opening circuit

- **Environment variable**: `WTC_CB_FAILURE_THRESHOLD`

#### `circuit_breaker.reset_timeout_seconds`

Time before attempting reset

- **Environment variable**: `WTC_CB_RESET_TIMEOUT`
- **Unit**: seconds

#### `circuit_breaker.success_threshold`

Successes required to close circuit

- **Environment variable**: `WTC_CB_SUCCESS_THRESHOLD`

</details>

### polling

Fallback polling configuration (when WebSocket unavailable)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `polling.default_interval_ms` | `integer` (min: 1000, max: 60000) | `5000` | Default polling interval ℹ️ |
| `polling.many_rtus_interval_ms` | `integer` (min: 1000, max: 120000) | `10000` | Reduced polling interval when many RTUs ℹ️ |
| `polling.many_rtus_threshold` | `integer` (min: 1, max: 100) | `10` | RTU count to trigger reduced polling ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `polling.default_interval_ms`

Default polling interval

- **Environment variable**: `WTC_POLL_INTERVAL_MS`
- **Unit**: milliseconds

#### `polling.many_rtus_interval_ms`

Reduced polling interval when many RTUs

- **Environment variable**: `WTC_MANY_RTUS_POLL_MS`
- **Unit**: milliseconds

#### `polling.many_rtus_threshold`

RTU count to trigger reduced polling

- **Environment variable**: `WTC_MANY_RTUS_THRESHOLD`

</details>

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
| `timeouts.command_ms` | `integer` (min: 100, max: 30000) | `3000` | Command execution timeout ℹ️ |
| `timeouts.db_query_ms` | `integer` (min: 100, max: 60000) | `5000` | Database query timeout ℹ️ |
| `timeouts.dcp_discovery_ms` | `integer` (min: 1000, max: 30000) | `5000` | PROFINET DCP discovery timeout ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `timeouts.command_ms`

Command execution timeout

- **Environment variable**: `WTC_COMMAND_TIMEOUT_MS`
- **Unit**: milliseconds

#### `timeouts.db_query_ms`

Database query timeout

- **Environment variable**: `WTC_DB_QUERY_TIMEOUT_MS`
- **Unit**: milliseconds

#### `timeouts.dcp_discovery_ms`

PROFINET DCP discovery timeout

- **Environment variable**: `WTC_DCP_DISCOVERY_MS`
- **Unit**: milliseconds

</details>

### ui

Web UI configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ui.api_url` | `string` | `""` | API URL for UI to connect to ℹ️ |
| `ui.dist_dir` | `string` | `""` | Static UI distribution directory ℹ️ |
| `ui.port` | `integer` (min: 1, max: 65535) | `3000` | UI server port (when running separately) ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `ui.api_url`

API URL for UI to connect to

- **Environment variable**: `NEXT_PUBLIC_API_URL`

#### `ui.dist_dir`

Static UI distribution directory

- **Environment variable**: `WTC_UI_DIST_DIR`

#### `ui.port`

UI server port (when running separately)

- **Environment variable**: `WTC_UI_PORT`

</details>

### websocket

WebSocket streaming configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `websocket.heartbeat_interval_ms` | `integer` (min: 1000, max: 60000) | `30000` | WebSocket heartbeat interval ℹ️ |
| `websocket.reconnect_base_ms` | `integer` (min: 100, max: 30000) | `1000` | Base reconnection interval (exponential backoff) ℹ️ |
| `websocket.reconnect_max_attempts` | `integer` (min: 1, max: 100) | `10` | Maximum reconnection attempts ℹ️ |

<details>
<summary><strong>Parameter Details</strong> (click to expand)</summary>

#### `websocket.heartbeat_interval_ms`

WebSocket heartbeat interval

- **Unit**: milliseconds

#### `websocket.reconnect_base_ms`

Base reconnection interval (exponential backoff)

- **Environment variable**: `WTC_WS_RECONNECT_MS`
- **Unit**: milliseconds

#### `websocket.reconnect_max_attempts`

Maximum reconnection attempts

- **Environment variable**: `WTC_WS_RECONNECT_ATTEMPTS`

</details>

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
| `WTC_API_PORT` | `8080` | API server port |
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