#!/bin/bash
# =============================================================================
# PROFINET RPC Communication Diagnostic Script
# =============================================================================
# Diagnoses why PROFINET RPC communication with RTUs is failing.
#
# Usage:
#   ./diagnose-profinet-rpc.sh <rtu-ip>
#   ./diagnose-profinet-rpc.sh 192.168.6.21
#
# Checks:
#   1. Network connectivity (ping)
#   2. Port 34964 (PROFINET RPC) reachability
#   3. Port 9081 (RTU HTTP API) reachability
#   4. Firewall rules
#   5. Controller RPC socket binding
#
# Copyright (C) 2024-2026
# SPDX-License-Identifier: GPL-3.0-or-later
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Usage
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <rtu-ip>"
    echo "Example: $0 192.168.6.21"
    exit 1
fi

RTU_IP="$1"
PNIO_RPC_PORT=34964
RTU_HTTP_PORT=9081

echo -e "${BLUE}=== PROFINET RPC Diagnostic ===${NC}"
echo "RTU IP: $RTU_IP"
echo ""

# Check 1: Basic connectivity
echo -e "${BLUE}[1/7] Checking basic network connectivity...${NC}"
if ping -c 3 -W 2 "$RTU_IP" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Ping successful${NC}"
else
    echo -e "${RED}✗ Ping failed - check network cable and RTU power${NC}"
    exit 1
fi
echo ""

# Check 2: Port 34964 (PROFINET RPC)
echo -e "${BLUE}[2/7] Checking PROFINET RPC port ($PNIO_RPC_PORT)...${NC}"
if command -v nc >/dev/null 2>&1; then
    if timeout 2 nc -zvu "$RTU_IP" "$PNIO_RPC_PORT" 2>&1 | grep -q "succeeded"; then
        echo -e "${GREEN}✓ Port $PNIO_RPC_PORT is reachable${NC}"
    else
        echo -e "${YELLOW}⚠ Port $PNIO_RPC_PORT not responding (nc check)${NC}"
        echo "  This is expected for UDP - RTU may still be listening"
    fi
elif command -v nmap >/dev/null 2>&1; then
    if nmap -sU -p "$PNIO_RPC_PORT" "$RTU_IP" 2>&1 | grep -q "open"; then
        echo -e "${GREEN}✓ Port $PNIO_RPC_PORT is open (nmap)${NC}"
    else
        echo -e "${YELLOW}⚠ Port $PNIO_RPC_PORT status unknown (nmap)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Install 'nc' or 'nmap' for port checking${NC}"
fi
echo ""

# Check 3: Port 9081 (HTTP API)
echo -e "${BLUE}[3/7] Checking RTU HTTP API port ($RTU_HTTP_PORT)...${NC}"
if command -v curl >/dev/null 2>&1; then
    if curl -s -m 2 "http://$RTU_IP:$RTU_HTTP_PORT/api/v1/slots" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ HTTP API responding on port $RTU_HTTP_PORT${NC}"
        echo "  RTU is alive and HTTP service is working"
    else
        echo -e "${RED}✗ HTTP API not responding on port $RTU_HTTP_PORT${NC}"
        echo "  RTU may be down or not running water-treat firmware"
    fi
else
    echo -e "${YELLOW}⚠ Install 'curl' for HTTP checking${NC}"
fi
echo ""

# Check 4: Firewall rules (local)
echo -e "${BLUE}[4/7] Checking local firewall rules...${NC}"
if command -v iptables >/dev/null 2>&1 && [[ $EUID -eq 0 ]]; then
    BLOCK_COUNT=$(iptables -L OUTPUT -n | grep -c "$RTU_IP.*$PNIO_RPC_PORT.*DROP" || true)
    if [[ $BLOCK_COUNT -gt 0 ]]; then
        echo -e "${RED}✗ Firewall is blocking outbound UDP $PNIO_RPC_PORT to $RTU_IP${NC}"
        echo "  Run: iptables -D OUTPUT -d $RTU_IP -p udp --dport $PNIO_RPC_PORT -j DROP"
    else
        echo -e "${GREEN}✓ No blocking firewall rules found${NC}"
    fi
elif command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        echo -e "${YELLOW}⚠ UFW is active - may be blocking traffic${NC}"
        echo "  Check with: ufw status verbose"
    else
        echo -e "${GREEN}✓ UFW is inactive${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Run as root to check iptables/firewall${NC}"
fi
echo ""

# Check 5: Controller RPC socket binding
echo -e "${BLUE}[5/7] Checking controller RPC socket binding...${NC}"
if command -v ss >/dev/null 2>&1; then
    if ss -uln | grep -q ":$PNIO_RPC_PORT"; then
        echo -e "${YELLOW}⚠ Local socket already bound to port $PNIO_RPC_PORT${NC}"
        ss -ulnp | grep ":$PNIO_RPC_PORT" || true
        echo "  This may interfere with controller RPC"
    else
        echo -e "${GREEN}✓ Port $PNIO_RPC_PORT not in use locally${NC}"
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -uln | grep -q ":$PNIO_RPC_PORT"; then
        echo -e "${YELLOW}⚠ Local socket already bound to port $PNIO_RPC_PORT${NC}"
        netstat -ulnp | grep ":$PNIO_RPC_PORT" || true
    else
        echo -e "${GREEN}✓ Port $PNIO_RPC_PORT not in use locally${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Install 'ss' or 'netstat' for socket checking${NC}"
fi
echo ""

# Check 6: RTU listening on 34964
echo -e "${BLUE}[6/7] Checking if RTU is listening on port $PNIO_RPC_PORT...${NC}"
echo "Attempting to send test UDP packet to $RTU_IP:$PNIO_RPC_PORT"
if command -v nc >/dev/null 2>&1; then
    # Send test packet and wait for response
    echo -n "test" | timeout 2 nc -u "$RTU_IP" "$PNIO_RPC_PORT" 2>&1 || true
    echo -e "${YELLOW}⚠ No response from RTU on port $PNIO_RPC_PORT${NC}"
    echo "  This could mean:"
    echo "    - RTU p-net stack not running"
    echo "    - RTU not configured to accept RPC connections"
    echo "    - RTU firewall blocking port 34964"
else
    echo -e "${YELLOW}⚠ Install 'nc' for UDP testing${NC}"
fi
echo ""

# Check 7: Docker container network mode
echo -e "${BLUE}[7/7] Checking Docker network configuration...${NC}"
if command -v docker >/dev/null 2>&1; then
    NETWORK_MODE=$(docker inspect wtc-controller --format='{{.HostConfig.NetworkMode}}' 2>/dev/null || echo "not-found")
    if [[ "$NETWORK_MODE" == "host" ]]; then
        echo -e "${GREEN}✓ Controller using host network mode${NC}"
    elif [[ "$NETWORK_MODE" == "not-found" ]]; then
        echo -e "${YELLOW}⚠ Controller container not found${NC}"
    else
        echo -e "${RED}✗ Controller using network mode: $NETWORK_MODE${NC}"
        echo "  Should be 'host' for PROFINET to work"
    fi
else
    echo -e "${YELLOW}⚠ Docker not installed or not accessible${NC}"
fi
echo ""

# Summary and recommendations
echo -e "${BLUE}=== Summary and Recommendations ===${NC}"
echo ""
echo "Common causes of RPC timeout:"
echo "  1. RTU p-net stack not listening on port 34964"
echo "     → Check RTU logs: docker logs <rtu-container>"
echo "     → Verify p-net initialization in RTU startup"
echo ""
echo "  2. Network isolation between controller and RTU"
echo "     → Ensure both on same subnet: $RTU_IP/24"
echo "     → Check switch/router configuration"
echo ""
echo "  3. RTU firmware mismatch"
echo "     → Verify RTU is running water-treat firmware"
echo "     → Check version compatibility with controller"
echo ""
echo "  4. P-net configuration issue on RTU"
echo "     → RTU may need explicit configuration to enable RPC"
echo "     → Check RTU's p-net initialization parameters"
echo ""
echo "Next steps:"
echo "  1. Check RTU logs for p-net errors"
echo "  2. Verify RTU is listening on port 34964: lsof -i :34964"
echo "  3. Try tcpdump to see if packets reach RTU: tcpdump -i any port 34964"
echo "  4. Check RTU's CLAUDE.md for p-net configuration requirements"
echo ""
