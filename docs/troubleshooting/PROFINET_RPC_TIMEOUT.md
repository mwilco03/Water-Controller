# PROFINET RPC Timeout Troubleshooting Guide

> **RESOLVED (2026-02-09):** RPC Connect timeouts were caused by **code bugs in
> the controller**, not networking issues. Ten bugs were found and fixed to
> achieve the first successful DAP Connect + PrmEnd. See
> [PROFINET_RPC_BUG_FIXES.md](../development/PROFINET_RPC_BUG_FIXES.md) for the
> complete fix history.

## Symptom

Controller logs show:

```
[INFO] RPC CONNECT: sent 466 bytes OK
[INFO] RPC CONNECT POLL: result=0, revents=0x0000
[WARN] RPC CONNECT TIMEOUT after 5000 ms (no response received)
[ERROR] Connect RPC failed
```

DCP discovery works (RTU is discovered), but RPC Connect requests receive no response.

## Root Cause Analysis

**Primary cause: Code bugs in the controller's RPC packet construction.**

p-net (the PROFINET device stack on RTUs) **silently drops** malformed packets.
There is no reject, no RST, no error — just silence. This makes RPC timeouts
indistinguishable from network issues.

If you are seeing timeouts, check the controller code first. The most common
causes are documented in
[PROFINET_RPC_BUG_FIXES.md](../development/PROFINET_RPC_BUG_FIXES.md).
Only investigate networking after verifying the packet structure is correct.

The Water Treatment Controller uses a custom PROFINET controller implementation that communicates with RTUs running p-net (PROFINET device stack). The RPC Connect timeout indicates the RTU is not responding to DCE/RPC connection requests on UDP port 34964.

### Expected Behavior

Per IEC 61158-6-10 (PROFINET specification), the connection sequence is:

1. **DCP Discovery** (Layer 2 multicast) ✅ Working
   - Controller sends DCP Identify Request
   - RTU responds with IP, MAC, station name, vendor/device IDs

2. **RPC Connect** (Layer 3 UDP, port 34964) ❌ Failing
   - Controller sends Connect Request to RTU IP:34964
   - RTU should respond with Connect Response
   - Establishes AR (Application Relationship)

3. **Cyclic I/O** (Real-Time Ethernet)
   - After AR is established, cyclic data exchange begins

### Why DCP Works But RPC Fails

- **DCP**: Uses Ethernet Layer 2 multicast (0x8892), no IP routing
- **RPC**: Uses UDP/IP on port 34964, requires full network stack

Network issues, firewall rules, or p-net configuration problems affect RPC but not DCP.

## Diagnostic Steps

### 1. Run Diagnostic Script

```bash
cd /home/user/Water-Controller
./scripts/diagnose-profinet-rpc.sh <rtu-ip>
```

This checks:
- Network connectivity
- Port 34964 reachability
- RTU HTTP API (port 9081)
- Firewall rules
- Docker network configuration

### 2. Check RTU p-net Stack

On the RTU system, verify p-net is running and listening:

```bash
# Check if RTU process is running
ps aux | grep -i profinet

# Check if port 34964 is listening
lsof -i :34964
# OR
netstat -uln | grep 34964

# Check RTU logs
docker logs <rtu-container> | grep -i "profinet\|p-net\|34964"
```

**Expected**: RTU should have a process listening on UDP port 34964.

### 3. Network Packet Capture

Capture traffic on both controller and RTU to see if packets are reaching the RTU:

```bash
# On controller
tcpdump -i any -n port 34964 -w controller-rpc.pcap

# On RTU
tcpdump -i any -n port 34964 -w rtu-rpc.pcap
```

Trigger a connect attempt, then analyze:
- Do packets leave the controller? ✅
- Do packets arrive at the RTU? ❓
- Does the RTU send a response? ❓

### 4. Check Firewall Rules

```bash
# Linux iptables
iptables -L -n -v | grep 34964

# UFW
ufw status verbose

# Check for Docker network isolation
docker network inspect wtc-network
```

## Common Fixes

### Fix 1: RTU p-net Not Initialized

**Problem**: RTU firmware not starting p-net stack properly.

**Solution**: Check RTU logs for p-net initialization errors:

```bash
docker logs <rtu-container> 2>&1 | grep -C 10 "p-net\|pnet_init"
```

Verify RTU firmware is up-to-date and compatible.

### Fix 2: Port 34964 Blocked

**Problem**: Firewall or network filtering blocking UDP port 34964.

**Solution**: Add firewall rule to allow traffic:

```bash
# Allow outbound from controller
iptables -A OUTPUT -p udp --dport 34964 -j ACCEPT

# Allow inbound to RTU
iptables -A INPUT -p udp --dport 34964 -j ACCEPT
```

Or disable firewall temporarily for testing:

```bash
systemctl stop ufw
systemctl stop firewalld
```

### Fix 3: Network Interface Mismatch

**Problem**: Controller and RTU on different network interfaces or VLANs.

**Solution**: Verify both are on same subnet:

```bash
# On controller
ip addr show

# On RTU
ip addr show

# Ensure both have IPs in same range (e.g., 192.168.6.x/24)
```

### Fix 4: Docker Network Mode

**Problem**: Controller not using host network mode, can't reach physical network.

**Solution**: Verify docker-compose.yml has:

```yaml
controller:
  network_mode: host
  cap_add:
    - NET_ADMIN
    - NET_RAW
```

Restart controller:

```bash
docker compose restart controller
```

### Fix 5: RTU Version Mismatch

**Problem**: RTU firmware incompatible with controller RPC implementation.

**Solution**: Verify versions match:

```bash
# Controller version
docker logs wtc-controller | grep "Starting Water"

# RTU version
docker logs <rtu-container> | grep -i version
```

Update RTU firmware if needed.

## HTTP Fallback

The controller implements HTTP fallback for slot discovery when RPC fails:

```
[INFO] Phase 6: HTTP Fallback /slots from 192.168.6.21
[INFO] Parsed 4 modules from HTTP /slots
```

This allows basic operation but has limitations:
- ❌ No proper AR establishment
- ❌ No ApplicationReady handshake
- ❌ No cyclic I/O exchange
- ✅ Can read slot configuration
- ✅ Can make HTTP API calls to RTU

HTTP fallback is a workaround, not a solution. Proper PROFINET requires RPC to work.

## Advanced Debugging

### Enable RPC Debug Logging

In controller code, set log level to DEBUG:

```c
// In src/profinet/profinet_rpc.c
LOG_DEBUG("RPC packet details...");
```

Or set environment variable:

```bash
WTC_LOG_LEVEL=DEBUG docker compose up -d controller
```

### Wireshark Analysis

Filter for PROFINET RPC traffic:

```
pn_dcp or pn_rt or dcerpc
```

Check:
1. DCP Identify Request/Response (should work)
2. DCE/RPC Connect Request (controller → RTU)
3. DCE/RPC Connect Response (RTU → controller) ← missing if timeout

### Manual RPC Test

Send raw UDP packet to RTU port 34964:

```bash
echo -n "test" | nc -u <rtu-ip> 34964
```

If RTU is listening, tcpdump on RTU should show the packet.

## Prevention

To avoid RPC timeouts:

1. **Use compatible firmware**: Ensure RTU runs water-treat firmware with p-net
2. **Network planning**: Controller and RTUs on same subnet, no VLANs/NAT
3. **Firewall rules**: Allow UDP port 34964 bidirectionally
4. **Health checks**: Monitor RPC connectivity, alert on failures
5. **Logging**: Enable DEBUG logs for troubleshooting

## References

- [PROFINET Specification IEC 61158-6-10](https://webstore.iec.ch/publication/83457)
- [p-net Documentation](https://rt-labs.com/docs/p-net)
- [CLAUDE.md](../../CLAUDE.md) - PROFINET connection sequence
- [diagnose-profinet-rpc.sh](../../scripts/diagnose-profinet-rpc.sh) - Diagnostic script

## Related Issues

- **DCP discovery failures**: See [DCP_TROUBLESHOOTING.md](./DCP_TROUBLESHOOTING.md)
- **Cyclic I/O timeouts**: See [CYCLIC_IO_TIMEOUT.md](./CYCLIC_IO_TIMEOUT.md)
- **Network configuration**: See [NETWORK_SETUP.md](./NETWORK_SETUP.md)

## Resolution History

RPC Connect timeouts were fully resolved on 2026-02-09 after fixing 10 bugs in
the controller's RPC packet construction and response parsing. The key finding:
**p-net silently drops malformed packets** — all timeout symptoms were caused by
code bugs, not network issues.

For the complete bug-by-bug analysis, see:
- [PROFINET RPC Bug Fixes](../development/PROFINET_RPC_BUG_FIXES.md) — full journey
- [Experimental Debug README](../../experimental/profinet-rpc-debug/README.md) — initial investigation

### Quick Checklist for Future RPC Issues

If RPC timeouts return after code changes, verify:

1. **No inter-block padding** — blocks must be contiguous
2. **UUIDs are LE-swapped** — per DREP=0x10
3. **NDR header present** — 20 bytes before first PNIO block
4. **IOCRTagHeader = 0xC000** — VLAN priority 6
5. **Frame offsets don't overlap** — each entry needs data_length+1 bytes
6. **rta_timeout_factor <= 100** — IEC 61158-6 maximum
7. **Response parser reads 20 bytes** — PNIOStatus first, not ArgsMaximum

### Enable Debug Logging on RTU

Install debug p-net library on the RTU for RTU-side error visibility:
```bash
ssh root@<rtu-ip>
cd /tmp && git clone https://github.com/mwilco03/p-net.git p-net-debug
cd p-net-debug && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Debug -DLOG_LEVEL=3 -DBUILD_SHARED_LIBS=ON
make -j$(nproc)
# Backup original, install debug version
cp /usr/lib/libprofinet.so /usr/lib/libprofinet.so.bak
cp libprofinet.so /usr/lib/
systemctl restart water-treat
```

## Support

If this guide doesn't resolve the issue:

1. Capture tcpdump on both controller and RTU
2. Check RTU logs for p-net errors
3. Report issue with diagnostics to GitHub
