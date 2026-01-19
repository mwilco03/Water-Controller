#!/bin/bash
# Water Treatment Controller - PROFINET Network Configuration Script
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script configures the network interface for PROFINET communication.
# PROFINET requires a dedicated Ethernet interface with specific settings.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Auto-detect network interface
detect_interface() {
    # Find first non-loopback, non-virtual interface that is UP
    for iface in /sys/class/net/*; do
        name=$(basename "$iface")
        case "$name" in
            lo|docker*|veth*|br-*|virbr*|vnet*) continue ;;
        esac
        if [ -f "$iface/operstate" ] && [ "$(cat "$iface/operstate")" = "up" ]; then
            echo "$name"
            return 0
        fi
    done
    # Fallback: first physical interface
    for iface in /sys/class/net/*; do
        name=$(basename "$iface")
        case "$name" in
            lo|docker*|veth*|br-*|virbr*|vnet*) continue ;;
        esac
        echo "$name"
        return 0
    done
    echo ""
}

# Default values - auto-detect interface if not specified
PROFINET_INTERFACE="${1:-$(detect_interface)}"
if [ -z "$PROFINET_INTERFACE" ]; then
    echo "ERROR: No network interface found. Please specify one."
    exit 1
fi
PROFINET_IP="${2:-192.168.1.1}"
PROFINET_NETMASK="${3:-255.255.255.0}"
PROFINET_VLAN="${4:-}"

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  PROFINET Network Configuration${NC}"
    echo -e "${BLUE}============================================${NC}"
}

print_step() {
    echo -e "${GREEN}[*]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Convert dotted decimal netmask to CIDR notation
# Handles both formats: "255.255.255.0" -> "24" or "24" -> "24"
netmask_to_cidr() {
    local mask="$1"

    # If already CIDR notation (just a number), return it
    if [[ "$mask" =~ ^[0-9]+$ ]] && [[ "$mask" -ge 0 ]] && [[ "$mask" -le 32 ]]; then
        echo "$mask"
        return
    fi

    # Convert dotted decimal to CIDR
    local cidr=0
    local IFS='.'
    read -ra octets <<< "$mask"

    for octet in "${octets[@]}"; do
        case $octet in
            255) cidr=$((cidr + 8)) ;;
            254) cidr=$((cidr + 7)) ;;
            252) cidr=$((cidr + 6)) ;;
            248) cidr=$((cidr + 5)) ;;
            240) cidr=$((cidr + 4)) ;;
            224) cidr=$((cidr + 3)) ;;
            192) cidr=$((cidr + 2)) ;;
            128) cidr=$((cidr + 1)) ;;
            0)   ;;
            *)   print_error "Invalid netmask octet: $octet"; exit 1 ;;
        esac
    done

    echo "$cidr"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        exit 1
    fi
}

check_interface() {
    if ! ip link show "$PROFINET_INTERFACE" &>/dev/null; then
        print_error "Interface $PROFINET_INTERFACE does not exist"
        echo ""
        echo "Available interfaces:"
        ip link show | grep -E "^[0-9]+" | awk -F: '{print "  - " $2}' | tr -d ' '
        exit 1
    fi
}

detect_interface_type() {
    local iface=$1
    local driver=$(ethtool -i "$iface" 2>/dev/null | grep "driver:" | awk '{print $2}')

    # Check if it's a wireless interface
    if [[ -d "/sys/class/net/$iface/wireless" ]]; then
        print_error "PROFINET requires a wired Ethernet connection. $iface is wireless."
        exit 1
    fi

    # Check link speed
    local speed=$(ethtool "$iface" 2>/dev/null | grep "Speed:" | awk '{print $2}')
    if [[ "$speed" == "10Mb/s" ]]; then
        print_warning "Interface speed is only 10 Mbps. 100 Mbps or higher recommended."
    fi

    echo "$driver"
}

configure_interface() {
    print_step "Configuring interface $PROFINET_INTERFACE..."

    # Bring interface down
    ip link set "$PROFINET_INTERFACE" down 2>/dev/null || true

    # Flush existing configuration
    ip addr flush dev "$PROFINET_INTERFACE" 2>/dev/null || true

    # Configure VLAN if specified
    if [[ -n "$PROFINET_VLAN" ]]; then
        print_step "Creating VLAN interface ${PROFINET_INTERFACE}.${PROFINET_VLAN}..."

        # Load 8021q module
        modprobe 8021q

        # Create VLAN interface
        ip link add link "$PROFINET_INTERFACE" name "${PROFINET_INTERFACE}.${PROFINET_VLAN}" type vlan id "$PROFINET_VLAN"

        PROFINET_INTERFACE="${PROFINET_INTERFACE}.${PROFINET_VLAN}"
    fi

    # Convert netmask to CIDR notation if needed
    local cidr
    cidr=$(netmask_to_cidr "$PROFINET_NETMASK")

    # Set IP address
    ip addr add "${PROFINET_IP}/${cidr}" dev "$PROFINET_INTERFACE"

    # Bring interface up
    ip link set "$PROFINET_INTERFACE" up

    # Enable multicast (required for DCP discovery)
    ip link set "$PROFINET_INTERFACE" multicast on

    print_step "Interface configured: $PROFINET_IP/$cidr (netmask: $PROFINET_NETMASK)"
}

configure_kernel_params() {
    print_step "Configuring kernel parameters for real-time..."

    # Create sysctl configuration
    cat > /etc/sysctl.d/99-profinet.conf << 'EOF'
# PROFINET Real-time Network Configuration

# Increase network buffer sizes
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.rmem_default = 1048576
net.core.wmem_default = 1048576
net.core.netdev_max_backlog = 5000

# Reduce latency
net.ipv4.tcp_low_latency = 1

# Disable TCP timestamps for reduced overhead
net.ipv4.tcp_timestamps = 0

# Enable IP forwarding (for gateway scenarios)
net.ipv4.ip_forward = 0

# ARP settings for industrial networks
net.ipv4.conf.all.arp_announce = 2
net.ipv4.conf.all.arp_ignore = 1

# IGMP settings for multicast
net.ipv4.igmp_max_memberships = 256
EOF

    # Apply settings
    sysctl -p /etc/sysctl.d/99-profinet.conf
}

configure_firewall() {
    print_step "Configuring firewall rules for PROFINET..."

    # Check if iptables is available
    if command -v iptables &>/dev/null; then
        # PROFINET Real-time ports (RTC)
        iptables -A INPUT -i "$PROFINET_INTERFACE" -p udp --dport 34962 -j ACCEPT
        iptables -A INPUT -i "$PROFINET_INTERFACE" -p udp --dport 34963 -j ACCEPT
        iptables -A INPUT -i "$PROFINET_INTERFACE" -p udp --dport 34964 -j ACCEPT

        # DCP Discovery (multicast)
        iptables -A INPUT -i "$PROFINET_INTERFACE" -d 224.0.0.0/4 -j ACCEPT

        # Allow established connections
        iptables -A INPUT -i "$PROFINET_INTERFACE" -m state --state ESTABLISHED,RELATED -j ACCEPT

        # Save rules
        if command -v iptables-save &>/dev/null; then
            iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
        fi

        print_step "Firewall rules configured"
    else
        print_warning "iptables not found, skipping firewall configuration"
    fi
}

configure_network_priority() {
    print_step "Configuring network priority for real-time traffic..."

    # Check if tc is available
    if command -v tc &>/dev/null; then
        # Remove existing qdisc
        tc qdisc del dev "$PROFINET_INTERFACE" root 2>/dev/null || true

        # Add priority queuing
        tc qdisc add dev "$PROFINET_INTERFACE" root handle 1: prio

        # High priority for PROFINET traffic (EtherType 0x8892)
        tc filter add dev "$PROFINET_INTERFACE" parent 1: protocol 0x8892 prio 1 u32 match u32 0 0 action skbedit priority 7

        print_step "Traffic prioritization configured"
    else
        print_warning "tc not found, skipping traffic prioritization"
    fi
}

create_systemd_network() {
    print_step "Creating persistent network configuration..."

    # Convert netmask to CIDR notation if needed
    local cidr
    cidr=$(netmask_to_cidr "$PROFINET_NETMASK")

    # Create systemd-networkd configuration
    mkdir -p /etc/systemd/network

    cat > "/etc/systemd/network/10-profinet.network" << EOF
[Match]
Name=$PROFINET_INTERFACE

[Network]
Address=$PROFINET_IP/$cidr
DHCP=no
MulticastDNS=yes

[Link]
RequiredForOnline=no
EOF

    # Create link configuration for performance
    cat > "/etc/systemd/network/10-profinet.link" << EOF
[Match]
OriginalName=$PROFINET_INTERFACE

[Link]
WakeOnLan=off
NamePolicy=keep kernel database onboard slot path
EOF

    print_step "Persistent configuration created at /etc/systemd/network/10-profinet.network"
}

create_env_file() {
    print_step "Creating environment file..."

    mkdir -p /etc/water-controller

    cat > /etc/water-controller/profinet.env << EOF
# PROFINET Interface Configuration
# Generated by setup-profinet-network.sh on $(date)

PROFINET_INTERFACE=$PROFINET_INTERFACE
PROFINET_IP=$PROFINET_IP
PROFINET_NETMASK=$PROFINET_NETMASK
PROFINET_VLAN=$PROFINET_VLAN

# Controller settings
WT_INTERFACE=$PROFINET_INTERFACE
WT_CYCLE_TIME=1000
WT_LOG_LEVEL=INFO
EOF

    print_step "Environment file created at /etc/water-controller/profinet.env"
}

verify_configuration() {
    print_step "Verifying configuration..."

    echo ""
    echo "Interface Status:"
    ip addr show "$PROFINET_INTERFACE"

    echo ""
    echo "Multicast Groups:"
    ip maddr show dev "$PROFINET_INTERFACE"

    echo ""
    echo "Link Status:"
    ethtool "$PROFINET_INTERFACE" 2>/dev/null | grep -E "(Speed|Duplex|Link detected)" || ip link show "$PROFINET_INTERFACE"
}

print_summary() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Configuration Complete${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "PROFINET Interface: $PROFINET_INTERFACE"
    echo "IP Address: $PROFINET_IP"
    echo "Netmask: $PROFINET_NETMASK"
    if [[ -n "$PROFINET_VLAN" ]]; then
        echo "VLAN ID: $PROFINET_VLAN"
    fi
    echo ""
    echo "Configuration files created:"
    echo "  - /etc/sysctl.d/99-profinet.conf"
    echo "  - /etc/systemd/network/10-profinet.network"
    echo "  - /etc/water-controller/profinet.env"
    echo ""
    echo "To start the controller with PROFINET:"
    echo "  source /etc/water-controller/profinet.env"
    echo "  docker-compose --profile profinet up -d"
    echo ""
    echo "Or for native installation:"
    echo "  water_treat_controller -i $PROFINET_INTERFACE"
}

usage() {
    echo "Usage: $0 [INTERFACE] [IP_ADDRESS] [NETMASK] [VLAN_ID]"
    echo ""
    echo "Arguments:"
    echo "  INTERFACE    Network interface to configure (default: auto-detect)"
    echo "  IP_ADDRESS   IP address for PROFINET (default: 192.168.1.1)"
    echo "  NETMASK      Network mask (default: 255.255.255.0)"
    echo "  VLAN_ID      Optional VLAN ID for tagged traffic"
    echo ""
    echo "Examples:"
    echo "  $0 eth1 192.168.100.1 255.255.255.0"
    echo "  $0 enp3s0 10.0.0.1 255.255.0.0 100"
    echo ""
    echo "Requirements:"
    echo "  - Dedicated Ethernet interface (not WiFi)"
    echo "  - 100 Mbps or higher link speed recommended"
    echo "  - Run as root"
}

# Main execution
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 0
fi

print_header
check_root
check_interface
detect_interface_type "$PROFINET_INTERFACE"
configure_interface
configure_kernel_params
configure_firewall
configure_network_priority
create_systemd_network
create_env_file
verify_configuration
print_summary

exit 0
