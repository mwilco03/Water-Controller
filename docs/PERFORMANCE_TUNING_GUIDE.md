# Water Treatment Controller - Performance Tuning Guide

**Document ID:** WT-PERF-001
**Version:** 1.0.0
**Last Updated:** 2024-12-22

---

## Overview

This guide provides recommendations for optimizing the Water Treatment Controller system performance across different hardware platforms and deployment scenarios.

---

## Quick Reference: Recommended Settings by Platform

| Platform | RAM | Cycle Time | Historian Rate | Max RTUs | Log Level |
|----------|-----|------------|----------------|----------|-----------|
| Raspberry Pi 3/Zero 2 | 1GB | 1000ms | 5000ms | 4 | WARN |
| Raspberry Pi 4/5 | 2-8GB | 500ms | 1000ms | 16 | INFO |
| BeagleBone Black | 512MB | 2000ms | 10000ms | 2 | WARN |
| Luckfox Lyra | 64-256MB | 2000ms | Disabled | 1 | ERROR |
| x86 Industrial PC | 4-16GB | 100ms | 1000ms | 32+ | INFO |

---

## 1. Cycle Time Tuning

The cycle time (`WT_CYCLE_TIME`) determines how frequently the controller scans RTUs and processes data.

### Configuration

```ini
# /etc/water-controller/controller.conf
[general]
cycle_time_ms = 1000
```

Or via environment:
```bash
export WT_CYCLE_TIME=1000
```

### Guidelines

| Cycle Time | Use Case | Trade-offs |
|------------|----------|------------|
| 100ms | Fast processes (filling, pressure control) | Higher CPU, more network traffic |
| 500ms | Typical water treatment | Balanced |
| 1000ms | Default, most applications | Good balance |
| 2000ms | Slow processes, limited hardware | Lower resolution |
| 5000ms | Monitoring only, very limited hardware | Delayed response |

### Measuring Performance

```bash
# Check system health
curl -s http://localhost:8000/health | jq

# Check RTU-specific PROFINET stats (includes cycle time)
curl -s http://localhost:8000/api/v1/rtus/{station_name}/profinet/status | jq '.cycle_time'

# Look for cycle overruns in logs
sudo journalctl -u water-controller | grep -i "overrun\|cycle"
```

### Symptoms of Too-Fast Cycle Time

- CPU usage > 80%
- Cycle time jitter (inconsistent timing)
- "Cycle overrun" warnings in logs
- System becomes unresponsive

**Solution:** Increase cycle time until CPU stays below 60-70%.

---

## 2. Historian Optimization

The historian stores time-series data and can significantly impact disk I/O and storage.

### Sample Rate

```ini
[historian]
sample_rate_ms = 1000
```

| Sample Rate | Data Volume (1 sensor) | Use Case |
|-------------|------------------------|----------|
| 100ms | 864,000 samples/day | High-speed analysis |
| 1000ms | 86,400 samples/day | Typical trending |
| 5000ms | 17,280 samples/day | Long-term storage |
| 60000ms | 1,440 samples/day | Low-resolution, long retention |

### Deadband Compression

Only record values when they change by more than the deadband:

```python
# Via API - set deadband on historian tag
curl -X PUT http://localhost:8000/api/v1/trends/tags/1 \
  -H "Content-Type: application/json" \
  -d '{"deadband": 0.1}'
```

**Recommended Deadbands:**

| Sensor Type | Deadband | Rationale |
|-------------|----------|-----------|
| pH | 0.05 | High precision needed |
| Temperature | 0.5°C | Normal variation |
| Level | 1% | Acceptable noise |
| Flow | 2% | Typically noisy |
| Pressure | 0.5 bar | Depends on range |

### Retention Policy

```ini
[historian]
retention_days = 365
```

**Storage Estimates (1 sensor, 1-second samples, no compression):**

| Retention | Storage |
|-----------|---------|
| 7 days | ~50 MB |
| 30 days | ~200 MB |
| 365 days | ~2.5 GB |

With deadband compression, expect 60-90% reduction.

### PostgreSQL vs SQLite

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Setup complexity | None | Moderate |
| Performance (small) | Excellent | Good |
| Performance (large) | Degrades | Excellent |
| Concurrent access | Limited | Excellent |
| Recommended size | < 1 GB | Any |
| Recommended RTUs | 1-4 | 4+ |

**Switch to PostgreSQL for:**
- More than 4 RTUs
- Historian database > 500 MB
- Multiple concurrent users
- Long retention periods

```bash
# Install PostgreSQL
sudo ./scripts/setup-postgres-production.sh

# Configure
echo "DATABASE_URL=postgresql://wtc:password@localhost/water_controller" \
  >> /etc/water-controller/environment
```

### TimescaleDB Optimization (PostgreSQL)

For large deployments with PostgreSQL:

```sql
-- Enable TimescaleDB hypertable
SELECT create_hypertable('historian_data', 'time',
  chunk_time_interval => INTERVAL '1 day');

-- Enable compression
ALTER TABLE historian_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'rtu_name, slot'
);

-- Compress data older than 7 days
SELECT add_compression_policy('historian_data', INTERVAL '7 days');

-- Set retention policy (delete data older than 1 year)
SELECT add_retention_policy('historian_data', INTERVAL '1 year');
```

---

## 3. Memory Optimization

### Monitoring Memory Usage

```bash
# System memory
free -m

# Process memory
ps aux | grep water_treat

# Detailed memory map
cat /proc/$(pgrep water_treat)/smaps | grep -E "^(Rss|Pss):" | awk '{sum+=$2} END {print sum/1024 " MB"}'
```

### Low-Memory Platforms (<512 MB RAM)

For Luckfox Lyra and similar constrained devices:

```ini
# /etc/water-controller/controller.conf
[general]
log_level = ERROR
cycle_time_ms = 2000

[historian]
enabled = false

[modbus]
tcp_enabled = false
```

Disable unused services:
```bash
sudo systemctl disable water-controller-ui
sudo systemctl disable water-controller-modbus
```

### Swap Configuration

For platforms with limited RAM:

```bash
# Check current swap
free -m

# Create swap file (1GB)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Tune swappiness (lower = less swap usage)
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## 4. Network Optimization

### PROFINET Tuning

```ini
[profinet]
interface = eth0
watchdog_factor = 3
send_clock_factor = 32
```

| Setting | Default | Description |
|---------|---------|-------------|
| watchdog_factor | 3 | AR timeout = cycle_time × factor |
| send_clock_factor | 32 | PROFINET send clock (31.25 µs × factor) |

### Network Interface Tuning

For dedicated PROFINET interface:

```bash
# Increase network buffer sizes
sudo sysctl -w net.core.rmem_max=26214400
sudo sysctl -w net.core.wmem_max=26214400
sudo sysctl -w net.core.rmem_default=1048576

# Disable offloading that can interfere with PROFINET
sudo ethtool -K eth0 rx off tx off gro off

# Make permanent in /etc/sysctl.conf
```

### Reducing Network Latency

1. Use wired Ethernet (not WiFi)
2. Avoid shared switches with heavy traffic
3. Consider managed switch with QoS for PROFINET traffic
4. Use short, quality cables

---

## 5. CPU Optimization

### Process Priority

The controller uses real-time priority for critical threads:

```bash
# Check current priority
ps -eo pid,ni,pri,comm | grep water_treat

# Increase priority manually (if not set by service)
sudo renice -n -10 $(pgrep water_treat)
```

### CPU Affinity (Multi-Core Systems)

Pin the controller to specific cores:

```bash
# Pin to cores 0 and 1
sudo taskset -pc 0,1 $(pgrep water_treat)
```

In systemd service:
```ini
[Service]
CPUAffinity=0 1
```

### PREEMPT_RT Kernel

For best real-time performance, use a PREEMPT_RT kernel:

```bash
# Check current kernel
uname -a | grep -i preempt

# Install RT kernel (Raspberry Pi)
sudo apt install linux-image-rt-arm64

# Reboot and verify
uname -a
```

### Isolating CPU Cores

For critical applications, isolate cores for the controller:

```bash
# Add to kernel command line (in /boot/cmdline.txt or GRUB)
isolcpus=2,3

# Run controller on isolated cores
sudo taskset -c 2,3 /opt/water-controller/bin/water_treat_controller ...
```

---

## 6. Disk I/O Optimization

### Reduce Log Volume

```ini
[general]
log_level = WARN  # or ERROR for minimal logging
log_max_size = 10485760  # 10 MB per file
log_max_files = 5
```

### Log to tmpfs (RAM disk)

For systems with limited write endurance (SD cards):

```bash
# Create tmpfs for logs
sudo mount -t tmpfs -o size=50m tmpfs /var/log/water-controller/

# Make permanent in /etc/fstab
tmpfs /var/log/water-controller tmpfs size=50m,mode=0755 0 0
```

**Warning:** Logs will be lost on reboot. Consider forwarding to remote syslog.

### SD Card Wear Reduction

1. Use log rotation aggressively
2. Consider read-only root filesystem
3. Move writable data to USB drive or NFS

---

## 7. PID Loop Tuning for Performance

Poorly tuned PID loops can cause:
- Oscillations increasing CPU load
- Excessive actuator commands
- Alarm floods

### Detection

```bash
# Look for rapid PV changes
curl -s "http://localhost:8000/api/v1/trends/1?start=$(date -d '-1 hour' -Iseconds)&end=$(date -Iseconds)" | jq '.data | length'
```

### Recommended Starting Points

| Process | Kp | Ki | Kd | Notes |
|---------|----|----|----|----|
| pH Control | 0.5 | 0.01 | 0.1 | Slow, avoid overshoot |
| Level Control | 2.0 | 0.1 | 0.0 | Proportional dominant |
| Temperature | 1.0 | 0.05 | 0.2 | Moderate, with derivative |
| Flow Control | 0.8 | 0.2 | 0.0 | Fast response |

### Rate Limiting

In the controller config, limit output rate of change:

```json
{
  "output_rate_limit": 10,  // Max 10% change per second
  "output_deadband": 0.5    // Ignore changes < 0.5%
}
```

---

## 8. Alarm System Tuning

### Reducing Alarm Noise

| Setting | Default | Recommendation |
|---------|---------|----------------|
| Delay | 0ms | 5000-30000ms for non-critical |
| Deadband | 0 | 5% of threshold |
| Suppression time | 0 | 60s minimum between repeats |

### Alarm Flood Prevention

Configure shelving and suppression:

```json
{
  "max_alarms_per_minute": 20,
  "flood_mode_threshold": 50,
  "auto_shelve_repeated": true,
  "repeated_count_threshold": 5
}
```

---

## 9. Modbus Gateway Tuning

### Poll Rate

```ini
[modbus]
poll_interval_ms = 1000
```

| Rate | Use Case |
|------|----------|
| 100ms | Fast polling from SCADA |
| 500ms | Typical integration |
| 1000ms | Default |
| 5000ms | Low-bandwidth links |

### Connection Limits

```ini
max_connections = 10
connection_timeout_ms = 30000
```

---

## 10. Monitoring and Benchmarks

### Key Metrics to Monitor

| Metric | Target | Action if Exceeded |
|--------|--------|-------------------|
| CPU Usage | < 70% | Increase cycle time |
| Memory Usage | < 80% | Disable features, add swap |
| Cycle Time Jitter | < 20% | Check for interference |
| Disk I/O Wait | < 10% | Move historian to faster storage |
| Network RTT to RTU | < 10ms | Check network path |

### Performance Benchmark Script

```bash
#!/bin/bash
# Run basic performance check

echo "=== System Resources ==="
free -m
df -h /var/lib/water-controller

echo "=== Controller Health ==="
curl -s http://localhost:8000/health | jq

echo "=== CPU Usage (5 second sample) ==="
top -b -n 2 -d 5 -p $(pgrep water_treat) | tail -1

echo "=== Network Latency to RTUs ==="
for ip in $(curl -s http://localhost:8000/api/v1/rtus | jq -r '.[].ip_address'); do
  echo -n "$ip: "
  ping -c 3 -q $ip | tail -1
done
```

---

## 11. Production Checklist

Before deploying to production:

- [ ] Cycle time tested under full load
- [ ] Historian retention configured appropriately
- [ ] Log level set to INFO or WARN
- [ ] Log rotation configured
- [ ] Swap enabled (if limited RAM)
- [ ] PID loops tuned and stable
- [ ] Alarm delays configured
- [ ] Backup automation enabled
- [ ] Monitoring/alerting configured
- [ ] Documentation updated

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024-12-22 | Initial | Initial release |

---

*Performance tuning is an iterative process. Start with conservative settings and adjust based on observed behavior and system metrics.*
