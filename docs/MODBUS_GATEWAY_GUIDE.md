# Modbus Gateway Configuration Guide

**Document ID:** WT-MODBUS-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22

---

## Overview

The Water Treatment Controller includes a Modbus gateway that bridges PROFINET sensor/actuator data to Modbus TCP and RTU protocols. This enables integration with:

- SCADA systems (Ignition, FactoryTalk, WinCC)
- HMI panels (Siemens, Schneider, Omron)
- Building automation systems (BACnet gateways)
- Third-party PLCs (Allen-Bradley, Siemens, Schneider)
- Data historians and analytics platforms

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    WATER TREATMENT CONTROLLER                   │
│                                                                  │
│  ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐  │
│  │  PROFINET   │────▶│  Modbus Gateway  │────▶│ Modbus TCP  │  │
│  │  RTU Data   │     │                  │     │  Server     │  │
│  └─────────────┘     │  ┌────────────┐  │     │  Port 502   │  │
│                       │  │  Register  │  │     └─────────────┘  │
│  ┌─────────────┐     │  │  Mapping   │  │                       │
│  │  PID Loop   │────▶│  │  Engine    │  │     ┌─────────────┐  │
│  │  Values     │     │  └────────────┘  │────▶│ Modbus RTU  │  │
│  └─────────────┘     └──────────────────┘     │ /dev/ttyUSB0│  │
│                                                └─────────────┘  │
│                              │                                   │
│                              ▼                                   │
│                       ┌──────────────────┐                      │
│                       │ Downstream Modbus │                      │
│                       │ Device Polling    │                      │
│                       └──────────────────┘                      │
│                              │                                   │
│                              ▼                                   │
│                       Energy Meters, VFDs, etc.                  │
└────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Enable Modbus Server

```bash
# Check current configuration
curl http://localhost:8000/api/v1/modbus/config

# Enable TCP server
curl -X PUT http://localhost:8000/api/v1/modbus/server \
  -H "Content-Type: application/json" \
  -d '{
    "tcp_enabled": true,
    "tcp_port": 502,
    "tcp_bind_address": "0.0.0.0"
  }'
```

### 2. Create Register Mapping

```bash
# Map pH sensor (RTU slot 1) to Holding Register 100
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 100,
    "register_type": "HOLDING",
    "data_type": "FLOAT32",
    "source_type": "PROFINET_SENSOR",
    "rtu_station": "water-treat-rtu-1",
    "slot": 1,
    "description": "pH Sensor"
  }'
```

### 3. Test Connection

```bash
# Using modpoll (install: apt install mbpoll)
modpoll -m tcp -t 4:float -r 100 -c 1 localhost
```

---

## Server Configuration

### TCP Server Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tcp_enabled` | bool | true | Enable/disable TCP server |
| `tcp_port` | int | 502 | TCP port (standard Modbus) |
| `tcp_bind_address` | string | 0.0.0.0 | Bind address |
| `max_connections` | int | 10 | Max concurrent connections |
| `connection_timeout_ms` | int | 30000 | Idle connection timeout |

**Configuration File:** `/etc/water-controller/modbus.conf`

```ini
[server]
tcp_enabled = true
tcp_port = 502
tcp_bind_address = 0.0.0.0
max_connections = 10
connection_timeout_ms = 30000
```

### RTU Server Settings (Serial)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rtu_enabled` | bool | false | Enable/disable RTU server |
| `rtu_device` | string | /dev/ttyUSB0 | Serial port device |
| `rtu_baud_rate` | int | 9600 | Baud rate |
| `rtu_data_bits` | int | 8 | Data bits (7 or 8) |
| `rtu_parity` | string | N | Parity (N/E/O) |
| `rtu_stop_bits` | int | 1 | Stop bits (1 or 2) |
| `rtu_slave_addr` | int | 1 | Slave address |

```ini
[server]
rtu_enabled = true
rtu_device = /dev/ttyUSB0
rtu_baud_rate = 9600
rtu_data_bits = 8
rtu_parity = N
rtu_stop_bits = 1
rtu_slave_addr = 1
```

**Note:** Ensure user `wtc` has access to serial port:
```bash
sudo usermod -a -G dialout wtc
```

---

## Register Mapping

### Register Types

| Type | Modbus Function | Read/Write | Description |
|------|-----------------|------------|-------------|
| `INPUT` | FC03/FC04 | Read-only | Sensor readings |
| `HOLDING` | FC03/FC06/FC16 | Read-write | Setpoints, config |
| `COIL` | FC01/FC05/FC15 | Read-write | On/off commands |
| `DISCRETE` | FC02 | Read-only | Status bits |

### Data Types

| Type | Registers | Byte Order | Description |
|------|-----------|------------|-------------|
| `INT16` | 1 | Big-endian | Signed 16-bit |
| `UINT16` | 1 | Big-endian | Unsigned 16-bit |
| `INT32` | 2 | Big-endian | Signed 32-bit |
| `UINT32` | 2 | Big-endian | Unsigned 32-bit |
| `FLOAT32` | 2 | Big-endian | IEEE 754 float |

### Byte Ordering

The gateway supports configurable byte ordering for multi-register values:

| Order | Description | Registers | Example (1.0f) |
|-------|-------------|-----------|----------------|
| `AB CD` | Big-endian (default) | [0x3F80, 0x0000] | Most common |
| `CD AB` | Little-endian words | [0x0000, 0x3F80] | Allen-Bradley |
| `BA DC` | Big-endian, byte-swapped | [0x803F, 0x0000] | Some devices |
| `DC BA` | Little-endian | [0x0000, 0x803F] | Less common |

Configure per-mapping:
```json
{
  "byte_order": "CD AB",
  ...
}
```

---

## Mapping Examples

### Sensor Mapping

Map a pH sensor to Input Register 0:

```bash
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 0,
    "register_type": "INPUT",
    "data_type": "FLOAT32",
    "source_type": "PROFINET_SENSOR",
    "rtu_station": "water-treat-rtu-1",
    "slot": 1,
    "description": "Tank 1 pH",
    "scaling_enabled": false
  }'
```

### Actuator Control Mapping

Map a pump control to Coil 0:

```bash
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 0,
    "register_type": "COIL",
    "data_type": "UINT16",
    "source_type": "PROFINET_ACTUATOR",
    "rtu_station": "water-treat-rtu-1",
    "slot": 9,
    "description": "Main Pump On/Off"
  }'
```

### Scaled Value Mapping

Map a 4-20mA level transmitter (0-100%) to integer register:

```bash
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 10,
    "register_type": "INPUT",
    "data_type": "UINT16",
    "source_type": "PROFINET_SENSOR",
    "rtu_station": "water-treat-rtu-1",
    "slot": 7,
    "description": "Tank Level (%)",
    "scaling_enabled": true,
    "scale_raw_min": 0.0,
    "scale_raw_max": 100.0,
    "scale_eng_min": 0,
    "scale_eng_max": 10000
  }'
```

This maps 0-100% float to 0-10000 integer (0.01% resolution).

### PID Loop Mapping

Map PID setpoint and process value:

```bash
# Process Variable (read-only)
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 200,
    "register_type": "INPUT",
    "data_type": "FLOAT32",
    "source_type": "PID_LOOP",
    "pid_loop_id": 1,
    "pid_field": "pv",
    "description": "pH PID - Process Variable"
  }'

# Setpoint (read-write)
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 202,
    "register_type": "HOLDING",
    "data_type": "FLOAT32",
    "source_type": "PID_LOOP",
    "pid_loop_id": 1,
    "pid_field": "setpoint",
    "description": "pH PID - Setpoint"
  }'

# Control Variable (read-only)
curl -X POST http://localhost:8000/api/v1/modbus/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "modbus_addr": 204,
    "register_type": "INPUT",
    "data_type": "FLOAT32",
    "source_type": "PID_LOOP",
    "pid_loop_id": 1,
    "pid_field": "cv",
    "description": "pH PID - Control Variable"
  }'
```

---

## Default Register Map

When `auto_generate = true`, the gateway creates a default map:

### Input Registers (FC04)

| Address | Description | Data Type |
|---------|-------------|-----------|
| 0-1 | Sensor 1 Value | FLOAT32 |
| 2 | Sensor 1 Quality | UINT16 |
| 3-4 | Sensor 2 Value | FLOAT32 |
| 5 | Sensor 2 Quality | UINT16 |
| ... | Additional sensors | ... |

### Holding Registers (FC03/FC06/FC16)

| Address | Description | Data Type | R/W |
|---------|-------------|-----------|-----|
| 100-101 | Actuator 1 PWM Setpoint | FLOAT32 | RW |
| 102-103 | Actuator 2 PWM Setpoint | FLOAT32 | RW |
| ... | Additional actuators | ... | ... |
| 200-201 | PID 1 Setpoint | FLOAT32 | RW |
| 202-203 | PID 1 PV | FLOAT32 | R |
| 204-205 | PID 1 CV | FLOAT32 | R |
| ... | Additional PID loops | ... | ... |

### Coils (FC01/FC05)

| Address | Description | R/W |
|---------|-------------|-----|
| 0 | Actuator 1 On/Off | RW |
| 1 | Actuator 2 On/Off | RW |
| ... | Additional actuators | ... |

### Discrete Inputs (FC02)

| Address | Description |
|---------|-------------|
| 0 | RTU 1 Connected |
| 1 | RTU 2 Connected |
| ... | Additional RTU status |
| 100 | Alarm Active |

---

## Downstream Device Polling

The gateway can poll external Modbus devices and integrate their data:

### Adding a Downstream Device

```bash
# Add energy meter
curl -X POST http://localhost:8000/api/v1/modbus/downstream \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Energy Meter",
    "transport": "TCP",
    "tcp_host": "192.168.1.50",
    "tcp_port": 502,
    "slave_addr": 1,
    "poll_interval_ms": 5000,
    "enabled": true,
    "registers": [
      {
        "address": 0,
        "count": 2,
        "function": 4,
        "data_type": "FLOAT32",
        "tag_name": "power_kw"
      },
      {
        "address": 2,
        "count": 2,
        "function": 4,
        "data_type": "FLOAT32",
        "tag_name": "energy_kwh"
      }
    ]
  }'
```

### Downstream Device Configuration

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Device name |
| `transport` | string | "TCP" or "RTU" |
| `tcp_host` | string | IP address (TCP only) |
| `tcp_port` | int | Port number (TCP only) |
| `rtu_device` | string | Serial device (RTU only) |
| `rtu_baud_rate` | int | Baud rate (RTU only) |
| `slave_addr` | int | Modbus slave address |
| `poll_interval_ms` | int | Polling interval |
| `enabled` | bool | Enable/disable polling |
| `registers` | array | Registers to poll |

---

## Diagnostics and Troubleshooting

### Statistics

```bash
# Get gateway statistics
curl http://localhost:8000/api/v1/modbus/stats
```

Response:
```json
{
  "server": {
    "connections_active": 2,
    "connections_total": 157,
    "requests_total": 45230,
    "requests_successful": 45100,
    "requests_failed": 130,
    "bytes_rx": 1256000,
    "bytes_tx": 3890000
  },
  "downstream": {
    "devices_configured": 3,
    "devices_healthy": 2,
    "polls_total": 12500,
    "polls_failed": 45
  }
}
```

### Common Issues

#### 1. Connection Refused on Port 502

**Cause:** Port 502 requires root privileges.

**Solutions:**
```bash
# Option 1: Use port > 1024
# Edit modbus.conf: tcp_port = 1502

# Option 2: Add capability
sudo setcap 'cap_net_bind_service=+ep' /opt/water-controller/bin/water_treat_controller

# Option 3: Use iptables redirect
sudo iptables -t nat -A PREROUTING -p tcp --dport 502 -j REDIRECT --to-port 1502
```

#### 2. Wrong Values Returned

**Check byte order:**
```bash
# Read raw register value
modpoll -m tcp -t 4 -r 100 -c 2 localhost

# Compare with float interpretation
modpoll -m tcp -t 4:float -r 100 -c 1 localhost
```

**Adjust byte order in mapping if needed:**
```json
{"byte_order": "CD AB"}
```

#### 3. Write Rejected

**Possible causes:**
- Register mapped as read-only
- Source is a sensor (read-only by nature)
- Actuator is interlocked by RTU

**Check mapping:**
```bash
curl http://localhost:8000/api/v1/modbus/mappings | jq '.[] | select(.modbus_addr == 100)'
```

#### 4. Downstream Device Timeout

**Check connectivity:**
```bash
# TCP
nc -zv 192.168.1.50 502

# Verify Modbus response
modpoll -m tcp -a 1 -t 4 -r 0 -c 1 192.168.1.50
```

---

## Integration Examples

### Ignition SCADA

Configure OPC-UA Modbus driver:
- Host: Controller IP
- Port: 502
- Unit ID: 1
- Data type: Float (AB CD byte order)

### Node-RED

Use `node-red-contrib-modbus`:
```json
{
  "host": "192.168.1.100",
  "port": 502,
  "unitId": 1,
  "fc": 3,
  "address": 100,
  "quantity": 2
}
```

### Python (pymodbus)

```python
from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

client = ModbusTcpClient('192.168.1.100', port=502)
client.connect()

# Read pH sensor (float at register 100)
result = client.read_holding_registers(100, 2, unit=1)
decoder = BinaryPayloadDecoder.fromRegisters(
    result.registers,
    byteorder=Endian.BIG,
    wordorder=Endian.BIG
)
ph_value = decoder.decode_32bit_float()
print(f"pH: {ph_value}")

# Write pump command (coil 0)
client.write_coil(0, True, unit=1)

client.close()
```

---

## Security Considerations

1. **Network Isolation:** Place Modbus network on isolated VLAN
2. **Firewall:** Restrict port 502 to authorized SCADA systems
3. **No Authentication:** Modbus has no built-in security - rely on network controls
4. **Read-Only for Sensors:** Map sensor values as INPUT registers (read-only)
5. **Audit Logging:** Enable command audit logging for compliance

```bash
# Allow only specific SCADA IP
sudo iptables -A INPUT -p tcp --dport 502 -s 192.168.1.200 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 502 -j DROP
```

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024-12-22 | Initial | Initial release |

---

*For additional Modbus protocol details, refer to the Modbus Application Protocol Specification (modbus.org).*
