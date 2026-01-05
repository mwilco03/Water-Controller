# Configuration Reference

Complete reference for all configuration options in the Water Treatment Controller system.

## Configuration Files

| File | Purpose | Location |
|------|---------|----------|
| `water-controller.json` | Main controller configuration | `docker/config/` or `/etc/water-controller/` |
| `ports.env` | Port configuration | `config/ports.env` |
| `.env` | Environment overrides | Project root |

## Environment Variables

### Port Configuration

All ports are configurable via environment variables. Default values are defined in `config/ports.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `WTC_API_PORT` | 8000 | REST API port |
| `WTC_UI_PORT` | 8080 | Web UI port |
| `WTC_DB_PORT` | 5432 | PostgreSQL port |
| `WTC_GRAFANA_PORT` | 3000 | Grafana dashboard port |
| `WTC_OPENPLC_PORT` | 8081 | OpenPLC viewer port |
| `WTC_MODBUS_TCP_PORT` | 1502 | Modbus TCP port |

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Full database connection string |
| `DB_PASSWORD` | `wtc_password` | Database password (use env var in production!) |
| `DB_POOL_SIZE` | 5 | Connection pool size |
| `DB_MAX_OVERFLOW` | 10 | Max overflow connections |

### Controller Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WT_INTERFACE` | `eth0` | PROFINET network interface |
| `WT_CYCLE_TIME` | 1000 | Control loop cycle time (ms) |
| `WT_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PROFINET_INTERFACE` | `eth0` | PROFINET network interface |

### Security Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (generated) | JWT signing key |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `API_KEY_ENABLED` | `false` | Enable API key authentication |

## Main Configuration File (water-controller.json)

### Controller Section

```json
{
  "controller": {
    "interface": "eth0",
    "cycle_time_ms": 1000,
    "discovery_timeout_ms": 5000,
    "connection_timeout_ms": 10000
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `interface` | string | `eth0` | Network interface for PROFINET |
| `cycle_time_ms` | integer | 1000 | Main control loop interval |
| `discovery_timeout_ms` | integer | 5000 | Device discovery timeout |
| `connection_timeout_ms` | integer | 10000 | Connection establishment timeout |

### RTU Configuration

```json
{
  "rtus": [
    {
      "station_name": "rtu-tank-1",
      "ip_address": "192.168.1.100",
      "vendor_id": 1,
      "device_id": 1,
      "slot_count": 16,
      "slots": [...]
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `station_name` | string | Yes | Unique RTU identifier |
| `ip_address` | string | Yes | IPv4 address |
| `vendor_id` | integer | Yes | PROFINET vendor ID |
| `device_id` | integer | Yes | PROFINET device ID |
| `slot_count` | integer | Yes | Number of I/O slots |
| `slots` | array | No | Slot configurations |

### Slot Configuration

```json
{
  "slots": [
    {
      "slot": 1,
      "type": "sensor",
      "name": "pH",
      "unit": "pH",
      "scale_min": 0,
      "scale_max": 14,
      "deadband": 0.05
    }
  ]
}
```

#### Sensor Slots

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slot` | integer | Yes | Slot number (1-16) |
| `type` | string | Yes | `"sensor"` |
| `name` | string | Yes | Display name |
| `unit` | string | Yes | Engineering unit |
| `scale_min` | number | Yes | Minimum scaled value |
| `scale_max` | number | Yes | Maximum scaled value |
| `deadband` | number | No | Change threshold for updates |

#### Actuator Slots

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slot` | integer | Yes | Slot number (1-16) |
| `type` | string | Yes | `"actuator"` |
| `name` | string | Yes | Display name |
| `has_pwm` | boolean | No | PWM control capability |
| `pwm_min` | number | Conditional | PWM minimum (if has_pwm) |
| `pwm_max` | number | Conditional | PWM maximum (if has_pwm) |

### PID Loop Configuration

```json
{
  "pid_loops": [
    {
      "name": "pH Control",
      "enabled": true,
      "input_rtu": "rtu-tank-1",
      "input_slot": 1,
      "output_rtu": "rtu-tank-1",
      "output_slot": 12,
      "kp": 2.0,
      "ki": 0.1,
      "kd": 0.5,
      "setpoint": 7.0,
      "output_min": 0.0,
      "output_max": 100.0,
      "mode": "AUTO"
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Loop identifier |
| `enabled` | boolean | Yes | Enable/disable loop |
| `input_rtu` | string | Yes | Input RTU station name |
| `input_slot` | integer | Yes | Input slot number |
| `output_rtu` | string | Yes | Output RTU station name |
| `output_slot` | integer | Yes | Output slot number |
| `kp` | number | Yes | Proportional gain |
| `ki` | number | Yes | Integral gain |
| `kd` | number | Yes | Derivative gain |
| `setpoint` | number | Yes | Target value |
| `output_min` | number | Yes | Output clamp minimum |
| `output_max` | number | Yes | Output clamp maximum |
| `mode` | string | Yes | `"AUTO"` or `"MANUAL"` |

### Interlock Configuration

```json
{
  "interlocks": [
    {
      "name": "Low Level Pump Protect",
      "enabled": true,
      "input_rtu": "rtu-tank-1",
      "input_slot": 7,
      "output_rtu": "rtu-pump-station",
      "output_slot": 9,
      "condition": "BELOW",
      "threshold": 10.0,
      "action": "OFF",
      "delay_ms": 0,
      "latching": true
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Interlock identifier |
| `enabled` | boolean | Yes | Enable/disable interlock |
| `condition` | string | Yes | `"ABOVE"` or `"BELOW"` |
| `threshold` | number | Yes | Trigger threshold |
| `action` | string | Yes | `"ON"` or `"OFF"` |
| `delay_ms` | integer | No | Delay before action |
| `latching` | boolean | No | Require manual reset |

### Alarm Configuration

```json
{
  "alarm_rules": [
    {
      "rtu_station": "rtu-tank-1",
      "slot": 1,
      "condition": "HIGH",
      "threshold": 8.5,
      "severity": "WARNING",
      "delay_ms": 5000,
      "message": "pH High"
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rtu_station` | string | Yes | RTU station name |
| `slot` | integer | Yes | Slot number |
| `condition` | string | Yes | `HIGH`, `HIGH_HIGH`, `LOW`, `LOW_LOW` |
| `threshold` | number | Yes | Alarm threshold |
| `severity` | string | Yes | `INFO`, `WARNING`, `CRITICAL`, `EMERGENCY` |
| `delay_ms` | integer | No | Delay before alarming |
| `message` | string | Yes | Alarm message text |

### Historian Configuration

```json
{
  "historian": {
    "sample_rate_ms": 1000,
    "buffer_size": 100000,
    "max_tags": 500,
    "compression": "SWINGING_DOOR",
    "default_deadband": 0.05
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sample_rate_ms` | integer | 1000 | Data collection interval |
| `buffer_size` | integer | 100000 | In-memory buffer size |
| `max_tags` | integer | 500 | Maximum historian tags |
| `compression` | string | `SWINGING_DOOR` | Compression algorithm |
| `default_deadband` | number | 0.05 | Default deadband for tags |

### Logging Configuration

```json
{
  "logging": {
    "level": "INFO",
    "file": "/var/log/water-controller/controller.log",
    "max_size_mb": 100,
    "max_files": 10
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | string | `INFO` | Log level |
| `file` | string | `/var/log/.../controller.log` | Log file path |
| `max_size_mb` | integer | 100 | Max log file size |
| `max_files` | integer | 10 | Max log file rotation |

## Docker Compose Environment

When using Docker, configure via `docker compose --env-file`:

```bash
# config/ports.env
WTC_API_PORT=8000
WTC_UI_PORT=8080
WTC_GRAFANA_PORT=3000
WTC_OPENPLC_PORT=8081
WTC_DB_PORT=5432
WTC_MODBUS_TCP_PORT=1502

# Secrets (override in .env or environment)
DB_PASSWORD=change_me_in_production
GRAFANA_PASSWORD=change_me_in_production
```

## Configuration Validation

Validate configuration files before deployment:

```bash
# Validate all config files
make validate-config

# Validate specific file
python scripts/validate_config.py docker/config/water-controller.json

# Strict mode (fail on warnings)
python scripts/validate_config.py --strict
```

## Configuration Precedence

Configuration values are resolved in this order (highest priority first):

1. Environment variables
2. `.env` file in project root
3. `ports.env` file
4. Configuration file (water-controller.json)
5. Built-in defaults

## Deployment-Specific Configuration

### Development

```bash
# Use development defaults
docker compose up -d
```

### Production

```bash
# Override with production values
export DB_PASSWORD=$(cat /run/secrets/db_password)
export SECRET_KEY=$(cat /run/secrets/secret_key)
docker compose --env-file config/ports.env up -d
```

### Bare Metal

```bash
# Set environment variables
export WT_INTERFACE=eth1
export WT_CYCLE_TIME=500
./water_treat_controller -c /etc/water-controller/water-controller.json
```
