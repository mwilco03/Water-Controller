#!/bin/bash
#
# Water Treatment Controller - Network and Storage Configuration
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module provides network interface configuration, firewall setup,
# tmpfs configuration for SD write endurance, and SQLite optimization.
#
# Target: ARM/x86 SBCs running Debian-based Linux
# Constraints: SD card write endurance, real-time PROFINET requirements
#

# Prevent multiple sourcing
if [ -n "$_WTC_NETWORK_STORAGE_LOADED" ]; then
    return 0
fi
_WTC_NETWORK_STORAGE_LOADED=1

# Source detection module for logging functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/detection.sh" ]; then
    # shellcheck source=detection.sh
    source "$SCRIPT_DIR/detection.sh"
fi

# =============================================================================
# Constants
# =============================================================================

readonly NETWORK_STORAGE_VERSION="1.0.0"

# Paths
readonly DATA_DIR="/var/lib/water-controller"
readonly LOG_DIR="/var/log/water-controller"
readonly RUN_DIR="/run/water-controller"
readonly CONFIG_DIR="/etc/water-controller"

# Default network settings
readonly DEFAULT_STATIC_IP="192.168.1.100"
readonly DEFAULT_NETMASK="255.255.255.0"
readonly DEFAULT_API_PORT=8000

# PROFINET ports
readonly PROFINET_UDP_PORT=34964
readonly PROFINET_TCP_PORT_START=34962
readonly PROFINET_TCP_PORT_END=34963

# tmpfs settings
readonly TMPFS_SIZE="64M"

# =============================================================================
# Network Interface Selection
# =============================================================================

# List available Ethernet interfaces
_list_ethernet_interfaces() {
    local interfaces=()

    # Get interfaces from /sys/class/net
    for iface_path in /sys/class/net/*; do
        local iface
        iface="$(basename "$iface_path")"

        # Skip loopback
        [ "$iface" = "lo" ] && continue

        # Skip virtual interfaces
        [[ "$iface" == veth* ]] && continue
        [[ "$iface" == docker* ]] && continue
        [[ "$iface" == br-* ]] && continue
        [[ "$iface" == virbr* ]] && continue

        # Check if it's a physical or virtual ethernet (not wireless)
        if [ -d "$iface_path/device" ] || [[ "$iface" == eth* ]] || [[ "$iface" == en* ]]; then
            # Check it's not wireless
            if [ ! -d "$iface_path/wireless" ] && [ ! -d "$iface_path/phy80211" ]; then
                interfaces+=("$iface")
            fi
        fi
    done

    printf '%s\n' "${interfaces[@]}"
}

# Select network interface for PROFINET
# Returns: interface name or exit 2 on failure
select_network_interface() {
    local non_interactive="${1:-false}"
    local default_interface="${2:-}"

    log_info "Selecting network interface..."

    # Get available interfaces
    local interfaces
    mapfile -t interfaces < <(_list_ethernet_interfaces)

    if [ ${#interfaces[@]} -eq 0 ]; then
        log_error "No Ethernet interfaces found"
        return 2
    fi

    log_debug "Found ${#interfaces[@]} interface(s): ${interfaces[*]}"

    # If only one interface, use it
    if [ ${#interfaces[@]} -eq 1 ]; then
        local selected="${interfaces[0]}"
        log_info "Auto-selected single interface: $selected"
        echo "$selected"
        return 0
    fi

    # If default provided and valid, use it
    if [ -n "$default_interface" ]; then
        for iface in "${interfaces[@]}"; do
            if [ "$iface" = "$default_interface" ]; then
                log_info "Using specified interface: $default_interface"
                echo "$default_interface"
                return 0
            fi
        done
        log_warn "Specified interface '$default_interface' not found"
    fi

    # Non-interactive mode: use first interface
    if [ "$non_interactive" = "true" ]; then
        local selected="${interfaces[0]}"
        log_info "Non-interactive mode, using first interface: $selected"
        echo "$selected"
        return 0
    fi

    # Interactive selection
    echo ""
    echo "Available network interfaces:"
    local i=1
    for iface in "${interfaces[@]}"; do
        local ip_addr
        ip_addr="$(ip -4 addr show "$iface" 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)"
        local status
        status="$(cat /sys/class/net/"$iface"/operstate 2>/dev/null || echo "unknown")"
        echo "  $i) $iface (${ip_addr:-no IP}, $status)"
        ((i++))
    done
    echo ""

    # Prompt for selection with timeout
    local selection
    read -r -t 30 -p "Select interface [1-${#interfaces[@]}] (default: 1): " selection

    if [ -z "$selection" ]; then
        selection=1
    fi

    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt ${#interfaces[@]} ]; then
        log_error "Invalid selection: $selection"
        return 2
    fi

    local selected="${interfaces[$((selection-1))]}"
    log_info "Selected interface: $selected"
    echo "$selected"
    return 0
}

# Validate interface exists and is ethernet
_validate_interface() {
    local iface="$1"

    if [ -z "$iface" ]; then
        return 1
    fi

    if [ ! -d "/sys/class/net/$iface" ]; then
        return 1
    fi

    # Check not wireless
    if [ -d "/sys/class/net/$iface/wireless" ] || [ -d "/sys/class/net/$iface/phy80211" ]; then
        return 1
    fi

    return 0
}

# =============================================================================
# Static IP Configuration
# =============================================================================

# Detect network configuration system
_detect_network_config_system() {
    # Check for systemd-networkd
    if systemctl is-active systemd-networkd >/dev/null 2>&1; then
        echo "systemd-networkd"
        return 0
    fi

    # Check for NetworkManager
    if systemctl is-active NetworkManager >/dev/null 2>&1; then
        echo "NetworkManager"
        return 0
    fi

    # Check for dhcpcd (common on Raspberry Pi)
    if systemctl is-active dhcpcd >/dev/null 2>&1; then
        echo "dhcpcd"
        return 0
    fi

    # Check for /etc/network/interfaces
    if [ -f /etc/network/interfaces ]; then
        echo "ifupdown"
        return 0
    fi

    echo "unknown"
    return 1
}

# Configure static IP address
# Input: interface name, IP address (default 192.168.1.100)
# Returns: 0 on success
configure_static_ip() {
    local iface="$1"
    local ip_addr="${2:-$DEFAULT_STATIC_IP}"
    local netmask="${3:-$DEFAULT_NETMASK}"

    if [ -z "$iface" ]; then
        log_error "Interface name required"
        return 2
    fi

    if ! _validate_interface "$iface"; then
        log_error "Invalid interface: $iface"
        return 2
    fi

    log_info "Configuring static IP: $ip_addr on $iface"

    local net_system
    net_system="$(_detect_network_config_system)"
    log_debug "Detected network system: $net_system"

    case "$net_system" in
        systemd-networkd)
            _configure_ip_systemd_networkd "$iface" "$ip_addr" "$netmask"
            ;;
        NetworkManager)
            _configure_ip_networkmanager "$iface" "$ip_addr" "$netmask"
            ;;
        dhcpcd)
            _configure_ip_dhcpcd "$iface" "$ip_addr" "$netmask"
            ;;
        ifupdown)
            _configure_ip_ifupdown "$iface" "$ip_addr" "$netmask"
            ;;
        *)
            log_warn "Unknown network system, applying IP directly"
            _configure_ip_direct "$iface" "$ip_addr" "$netmask"
            ;;
    esac

    local result=$?

    # Verify IP was assigned
    sleep 2
    local current_ip
    current_ip="$(ip -4 addr show "$iface" 2>/dev/null | grep -oP 'inet \K[\d.]+' | head -1)"

    if [ "$current_ip" = "$ip_addr" ]; then
        log_info "Static IP configured successfully: $ip_addr"
        return 0
    else
        log_warn "IP verification: expected $ip_addr, got ${current_ip:-none}"
        return $result
    fi
}

# Configure IP via systemd-networkd
_configure_ip_systemd_networkd() {
    local iface="$1"
    local ip_addr="$2"
    local netmask="$3"

    local network_file="/etc/systemd/network/10-water-controller-${iface}.network"

    # Convert netmask to CIDR
    local cidr
    cidr="$(_netmask_to_cidr "$netmask")"

    log_debug "Creating systemd-networkd config: $network_file"

    cat > "$network_file" << EOF
# Water-Controller PROFINET Network Configuration
# Generated by installation script

[Match]
Name=$iface

[Network]
Address=${ip_addr}/${cidr}
# No gateway - isolated PROFINET network
# Gateway=192.168.1.1

[Link]
RequiredForOnline=no
EOF

    chmod 644 "$network_file"

    # Restart networkd
    systemctl restart systemd-networkd 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_warn "Failed to restart systemd-networkd"
        return 1
    }

    return 0
}

# Configure IP via NetworkManager
_configure_ip_networkmanager() {
    local iface="$1"
    local ip_addr="$2"
    local netmask="$3"

    local cidr
    cidr="$(_netmask_to_cidr "$netmask")"

    # Use nmcli to configure
    if command -v nmcli >/dev/null 2>&1; then
        local conn_name="water-controller-$iface"

        # Delete existing connection if present
        nmcli connection delete "$conn_name" 2>/dev/null || true

        # Create new connection
        nmcli connection add \
            type ethernet \
            con-name "$conn_name" \
            ifname "$iface" \
            ipv4.method manual \
            ipv4.addresses "${ip_addr}/${cidr}" \
            connection.autoconnect yes 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            log_error "Failed to create NetworkManager connection"
            return 1
        }

        # Activate connection
        nmcli connection up "$conn_name" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            log_warn "Failed to activate connection"
        }
    else
        log_error "nmcli not found"
        return 1
    fi

    return 0
}

# Configure IP via dhcpcd
_configure_ip_dhcpcd() {
    local iface="$1"
    local ip_addr="$2"
    local netmask="$3"

    local cidr
    cidr="$(_netmask_to_cidr "$netmask")"

    local dhcpcd_conf="/etc/dhcpcd.conf"

    # Backup existing config
    if [ -f "$dhcpcd_conf" ]; then
        cp "$dhcpcd_conf" "${dhcpcd_conf}.backup.$(date +%Y%m%d_%H%M%S)"
    fi

    # Check if interface already configured
    if grep -q "^interface $iface" "$dhcpcd_conf" 2>/dev/null; then
        log_warn "Interface $iface already in dhcpcd.conf, skipping"
        return 0
    fi

    # Append static IP configuration
    cat >> "$dhcpcd_conf" << EOF

# Water-Controller PROFINET Network Configuration
interface $iface
static ip_address=${ip_addr}/${cidr}
# No gateway for isolated PROFINET network
# static routers=192.168.1.1
noipv6
EOF

    # Restart dhcpcd
    systemctl restart dhcpcd 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_warn "Failed to restart dhcpcd"
        return 1
    }

    return 0
}

# Configure IP via /etc/network/interfaces
_configure_ip_ifupdown() {
    local iface="$1"
    local ip_addr="$2"
    local netmask="$3"

    local interfaces_file="/etc/network/interfaces"
    local interfaces_d="/etc/network/interfaces.d"

    # Use interfaces.d if available
    if [ -d "$interfaces_d" ]; then
        local iface_file="$interfaces_d/water-controller-$iface"

        cat > "$iface_file" << EOF
# Water-Controller PROFINET Network Configuration
auto $iface
iface $iface inet static
    address $ip_addr
    netmask $netmask
    # No gateway for isolated PROFINET network
EOF

        chmod 644 "$iface_file"
    else
        # Append to main interfaces file
        if grep -q "^iface $iface" "$interfaces_file" 2>/dev/null; then
            log_warn "Interface $iface already in interfaces file"
            return 0
        fi

        cat >> "$interfaces_file" << EOF

# Water-Controller PROFINET Network Configuration
auto $iface
iface $iface inet static
    address $ip_addr
    netmask $netmask
EOF
    fi

    # Bring up interface
    ifdown "$iface" 2>/dev/null || true
    ifup "$iface" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_warn "Failed to bring up interface"
        return 1
    }

    return 0
}

# Configure IP directly (fallback)
_configure_ip_direct() {
    local iface="$1"
    local ip_addr="$2"
    local netmask="$3"

    local cidr
    cidr="$(_netmask_to_cidr "$netmask")"

    # Flush existing IPs
    ip addr flush dev "$iface" 2>/dev/null || true

    # Add IP
    ip addr add "${ip_addr}/${cidr}" dev "$iface" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_error "Failed to add IP address"
        return 1
    }

    # Bring up interface
    ip link set "$iface" up 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_error "Failed to bring up interface"
        return 1
    }

    log_warn "IP configured directly - will not persist across reboots"
    return 0
}

# Convert netmask to CIDR notation
_netmask_to_cidr() {
    local netmask="$1"
    local cidr=0

    IFS='.' read -ra octets <<< "$netmask"
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
            0) ;;
        esac
    done

    echo "$cidr"
}

# =============================================================================
# Network Performance Tuning
# =============================================================================

# Tune network interface for PROFINET performance
# Returns: 0 on success
tune_network_interface() {
    local iface="$1"

    if [ -z "$iface" ]; then
        log_error "Interface name required"
        return 1
    fi

    if ! _validate_interface "$iface"; then
        log_error "Invalid interface: $iface"
        return 1
    fi

    log_info "Tuning network interface: $iface"

    # Disable power management (Wake-on-LAN off)
    if command -v ethtool >/dev/null 2>&1; then
        log_debug "Disabling Wake-on-LAN..."
        ethtool -s "$iface" wol d 2>/dev/null || {
            log_debug "WoL disable failed (may not be supported)"
        }

        # Disable interrupt coalescing for low latency
        log_debug "Disabling interrupt coalescing..."
        ethtool -C "$iface" rx-usecs 0 tx-usecs 0 2>/dev/null || {
            log_debug "Interrupt coalescing config failed (may not be supported)"
        }

        # Disable pause frames for real-time
        ethtool -A "$iface" rx off tx off 2>/dev/null || {
            log_debug "Pause frame disable failed (may not be supported)"
        }
    else
        log_warn "ethtool not available, skipping NIC tuning"
    fi

    # Set MTU
    log_debug "Setting MTU to 1500..."
    ip link set "$iface" mtu 1500 2>/dev/null || {
        log_debug "MTU set failed"
    }

    # Create udev rule for persistent settings
    local udev_rule="/etc/udev/rules.d/99-water-controller-network.rules"
    log_debug "Creating udev rule for persistent settings..."

    cat > "$udev_rule" << EOF
# Water-Controller Network Performance Settings
# Disable WoL and optimize for low latency

ACTION=="add", SUBSYSTEM=="net", KERNEL=="$iface", \\
    RUN+="/usr/sbin/ethtool -s %k wol d", \\
    RUN+="/usr/sbin/ethtool -C %k rx-usecs 0 tx-usecs 0"
EOF

    chmod 644 "$udev_rule"

    log_info "Network interface tuning complete"
    _log_write "INFO" "Network interface $iface tuned for PROFINET"

    return 0
}

# =============================================================================
# Firewall Configuration
# =============================================================================

# Detect firewall system
_detect_firewall_system() {
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        echo "ufw"
    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
        echo "firewalld"
    elif command -v nft >/dev/null 2>&1 && systemctl is-active nftables >/dev/null 2>&1; then
        echo "nftables"
    elif command -v iptables >/dev/null 2>&1; then
        echo "iptables"
    else
        echo "none"
    fi
}

# Configure firewall rules
# Input: allow_ssh flag (optional)
# Returns: 0 on success
configure_firewall() {
    local allow_ssh="${1:-true}"

    log_info "Configuring firewall..."

    local fw_system
    fw_system="$(_detect_firewall_system)"
    log_debug "Detected firewall system: $fw_system"

    case "$fw_system" in
        ufw)
            _configure_firewall_ufw "$allow_ssh"
            ;;
        firewalld)
            _configure_firewall_firewalld "$allow_ssh"
            ;;
        nftables)
            _configure_firewall_nftables "$allow_ssh"
            ;;
        iptables)
            _configure_firewall_iptables "$allow_ssh"
            ;;
        none)
            log_warn "No active firewall detected"
            log_warn "Consider enabling a firewall for security"
            return 0
            ;;
    esac

    return $?
}

# Configure UFW
_configure_firewall_ufw() {
    local allow_ssh="$1"

    log_info "Configuring UFW firewall..."

    # Allow API port
    ufw allow "$DEFAULT_API_PORT/tcp" comment "Water-Controller API" 2>&1 | tee -a "$INSTALL_LOG_FILE"

    # Allow PROFINET ports
    ufw allow "$PROFINET_UDP_PORT/udp" comment "PROFINET UDP" 2>&1 | tee -a "$INSTALL_LOG_FILE"
    ufw allow "${PROFINET_TCP_PORT_START}:${PROFINET_TCP_PORT_END}/tcp" comment "PROFINET TCP" 2>&1 | tee -a "$INSTALL_LOG_FILE"

    # Allow SSH with rate limiting if requested
    if [ "$allow_ssh" = "true" ]; then
        ufw limit ssh comment "SSH with rate limiting" 2>&1 | tee -a "$INSTALL_LOG_FILE"
    fi

    # Enable UFW if not already
    if ! ufw status | grep -q "Status: active"; then
        log_info "Enabling UFW..."
        echo "y" | ufw enable 2>&1 | tee -a "$INSTALL_LOG_FILE"
    fi

    # Reload
    ufw reload 2>&1 | tee -a "$INSTALL_LOG_FILE"

    log_info "UFW firewall configured"
    return 0
}

# Configure firewalld
_configure_firewall_firewalld() {
    local allow_ssh="$1"

    log_info "Configuring firewalld..."

    # Allow API port
    firewall-cmd --permanent --add-port="$DEFAULT_API_PORT/tcp" 2>&1 | tee -a "$INSTALL_LOG_FILE"

    # Allow PROFINET ports
    firewall-cmd --permanent --add-port="$PROFINET_UDP_PORT/udp" 2>&1 | tee -a "$INSTALL_LOG_FILE"
    firewall-cmd --permanent --add-port="${PROFINET_TCP_PORT_START}-${PROFINET_TCP_PORT_END}/tcp" 2>&1 | tee -a "$INSTALL_LOG_FILE"

    # Allow SSH if requested
    if [ "$allow_ssh" = "true" ]; then
        firewall-cmd --permanent --add-service=ssh 2>&1 | tee -a "$INSTALL_LOG_FILE"
    fi

    # Reload
    firewall-cmd --reload 2>&1 | tee -a "$INSTALL_LOG_FILE"

    log_info "firewalld configured"
    return 0
}

# Configure nftables
_configure_firewall_nftables() {
    local allow_ssh="$1"

    log_info "Configuring nftables..."

    local nft_file="/etc/nftables.d/water-controller.nft"
    mkdir -p /etc/nftables.d

    cat > "$nft_file" << EOF
# Water-Controller Firewall Rules
table inet water_controller {
    chain input {
        type filter hook input priority 0; policy accept;

        # Allow established connections
        ct state established,related accept

        # Allow loopback
        iif lo accept

        # Allow API port
        tcp dport $DEFAULT_API_PORT accept

        # Allow PROFINET
        udp dport $PROFINET_UDP_PORT accept
        tcp dport ${PROFINET_TCP_PORT_START}-${PROFINET_TCP_PORT_END} accept
EOF

    if [ "$allow_ssh" = "true" ]; then
        cat >> "$nft_file" << EOF

        # Allow SSH with rate limiting
        tcp dport 22 ct state new limit rate 4/minute accept
EOF
    fi

    cat >> "$nft_file" << EOF
    }
}
EOF

    chmod 644 "$nft_file"

    # Apply rules
    nft -f "$nft_file" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
        log_warn "Failed to apply nftables rules"
        return 1
    }

    log_info "nftables configured"
    return 0
}

# Configure iptables
_configure_firewall_iptables() {
    local allow_ssh="$1"

    log_info "Configuring iptables..."

    # Allow established connections
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null

    # Allow loopback
    iptables -A INPUT -i lo -j ACCEPT 2>/dev/null

    # Allow API port
    iptables -A INPUT -p tcp --dport "$DEFAULT_API_PORT" -j ACCEPT 2>/dev/null

    # Allow PROFINET
    iptables -A INPUT -p udp --dport "$PROFINET_UDP_PORT" -j ACCEPT 2>/dev/null
    iptables -A INPUT -p tcp --dport "${PROFINET_TCP_PORT_START}:${PROFINET_TCP_PORT_END}" -j ACCEPT 2>/dev/null

    # Allow SSH with rate limiting if requested
    if [ "$allow_ssh" = "true" ]; then
        iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --set 2>/dev/null
        iptables -A INPUT -p tcp --dport 22 -m state --state NEW -m recent --update --seconds 60 --hitcount 4 -j DROP 2>/dev/null
        iptables -A INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null
    fi

    # Log dropped packets
    iptables -A INPUT -m limit --limit 5/min -j LOG --log-prefix "iptables-dropped: " 2>/dev/null

    # Save rules
    if command -v iptables-save >/dev/null 2>&1; then
        if [ -d /etc/iptables ]; then
            iptables-save > /etc/iptables/rules.v4 2>/dev/null
        elif command -v netfilter-persistent >/dev/null 2>&1; then
            netfilter-persistent save 2>/dev/null
        fi
    fi

    log_info "iptables configured"
    return 0
}

# =============================================================================
# tmpfs Configuration for Write Endurance
# =============================================================================

# Configure tmpfs mount for temporary files
# Returns: 0 on success
configure_tmpfs() {
    log_info "Configuring tmpfs for write endurance..."

    local tmpfs_mount="$RUN_DIR"
    local fstab_entry="tmpfs $tmpfs_mount tmpfs size=$TMPFS_SIZE,mode=0755,uid=water-controller,gid=water-controller 0 0"

    # Check if already in fstab
    if grep -q "$tmpfs_mount" /etc/fstab 2>/dev/null; then
        log_info "tmpfs entry already exists in fstab"
    else
        # Backup fstab
        cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)

        # Add entry
        echo "" >> /etc/fstab
        echo "# Water-Controller tmpfs for write endurance" >> /etc/fstab
        echo "$fstab_entry" >> /etc/fstab

        log_info "Added tmpfs entry to fstab"
    fi

    # Create mount point if needed
    mkdir -p "$tmpfs_mount"

    # Mount if not already mounted
    if ! mountpoint -q "$tmpfs_mount" 2>/dev/null; then
        log_info "Mounting tmpfs..."
        mount "$tmpfs_mount" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
            # Try mounting directly
            mount -t tmpfs -o "size=$TMPFS_SIZE,mode=0755" tmpfs "$tmpfs_mount" 2>&1 | tee -a "$INSTALL_LOG_FILE" || {
                log_warn "Failed to mount tmpfs"
                return 1
            }
        }
    fi

    # Verify mount
    if mountpoint -q "$tmpfs_mount" 2>/dev/null; then
        log_info "tmpfs mounted at $tmpfs_mount"
    else
        log_warn "tmpfs mount verification failed"
    fi

    # Set ownership
    chown water-controller:water-controller "$tmpfs_mount" 2>/dev/null || true

    _log_write "INFO" "tmpfs configured at $tmpfs_mount"

    return 0
}

# =============================================================================
# SQLite Configuration for Write Endurance
# =============================================================================

# Configure SQLite database with WAL mode for write endurance
# Returns: 0 on success
configure_sqlite() {
    log_info "Configuring SQLite for write endurance..."

    local db_path="$DATA_DIR/historian.db"

    # Check if sqlite3 is available
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "sqlite3 not installed, skipping database configuration"
        return 0
    fi

    # Create data directory if needed
    mkdir -p "$DATA_DIR"
    chown water-controller:water-controller "$DATA_DIR" 2>/dev/null || true

    # Create database if it doesn't exist
    if [ ! -f "$db_path" ]; then
        log_info "Creating historian database..."
        touch "$db_path"
        chown water-controller:water-controller "$db_path"
        chmod 660 "$db_path"
    fi

    # Apply SQLite pragmas for write endurance
    log_info "Applying SQLite optimizations..."

    sqlite3 "$db_path" << 'EOF'
-- Enable WAL mode for better write performance and crash recovery
PRAGMA journal_mode=WAL;

-- NORMAL synchronous is good balance of safety and performance
PRAGMA synchronous=NORMAL;

-- 64MB cache size (negative = KB)
PRAGMA cache_size=-65536;

-- Store temp tables in memory
PRAGMA temp_store=MEMORY;

-- Checkpoint every 1000 pages
PRAGMA wal_autocheckpoint=1000;

-- Enable memory-mapped I/O (256MB)
PRAGMA mmap_size=268435456;

-- Verify settings
.headers on
SELECT 'journal_mode' as setting, journal_mode as value FROM pragma_journal_mode()
UNION ALL
SELECT 'synchronous', synchronous FROM pragma_synchronous()
UNION ALL
SELECT 'cache_size', cache_size FROM pragma_cache_size()
UNION ALL
SELECT 'temp_store', temp_store FROM pragma_temp_store();
EOF

    local result=$?

    if [ $result -ne 0 ]; then
        log_warn "SQLite configuration may have partially failed"
    fi

    # Set ownership
    chown water-controller:water-controller "$db_path"* 2>/dev/null || true
    chmod 660 "$db_path"* 2>/dev/null || true

    log_info "SQLite database configured: $db_path"
    _log_write "INFO" "SQLite configured with WAL mode at $db_path"

    return 0
}

# =============================================================================
# Log Rotation Configuration
# =============================================================================

# Configure log rotation for Water-Controller logs
# Returns: 0 on success
configure_log_rotation() {
    log_info "Configuring log rotation..."

    local logrotate_conf="/etc/logrotate.d/water-controller"

    cat > "$logrotate_conf" << EOF
# Water-Controller Log Rotation
# Rotate daily, keep 7 days, compress old logs

$LOG_DIR/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 water-controller water-controller
    sharedscripts
    postrotate
        # Signal uvicorn to reopen log files (if using file logging)
        systemctl kill -s HUP water-controller.service 2>/dev/null || true
    endscript
}

# Application-specific logs
$LOG_DIR/app.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 water-controller water-controller
    size 10M
}

# Historian query logs (can grow large)
$LOG_DIR/historian.log {
    weekly
    missingok
    rotate 4
    compress
    delaycompress
    notifempty
    create 0640 water-controller water-controller
    size 50M
}
EOF

    chmod 644 "$logrotate_conf"

    # Verify logrotate config
    if command -v logrotate >/dev/null 2>&1; then
        if logrotate -d "$logrotate_conf" 2>&1 | grep -q "error"; then
            log_warn "Logrotate configuration may have errors"
        else
            log_debug "Logrotate configuration verified"
        fi
    fi

    log_info "Log rotation configured"
    _log_write "INFO" "Log rotation configured in $logrotate_conf"

    return 0
}

# =============================================================================
# Combined Configuration
# =============================================================================

# Run all network and storage configuration
# Returns: 0 on success
configure_all_network_storage() {
    local iface="${1:-}"
    local ip_addr="${2:-$DEFAULT_STATIC_IP}"

    log_info "Running complete network and storage configuration..."

    # Select interface if not provided
    if [ -z "$iface" ]; then
        iface="$(select_network_interface true)" || {
            log_error "Failed to select network interface"
            return 2
        }
    fi

    # Configure static IP
    configure_static_ip "$iface" "$ip_addr" || {
        log_warn "Static IP configuration failed"
    }

    # Tune network interface
    tune_network_interface "$iface" || {
        log_warn "Network tuning failed"
    }

    # Configure firewall
    configure_firewall true || {
        log_warn "Firewall configuration failed"
    }

    # Configure tmpfs
    configure_tmpfs || {
        log_warn "tmpfs configuration failed"
    }

    # Configure SQLite
    configure_sqlite || {
        log_warn "SQLite configuration failed"
    }

    # Configure log rotation
    configure_log_rotation || {
        log_warn "Log rotation configuration failed"
    }

    log_info "Network and storage configuration complete"
    return 0
}

# =============================================================================
# Main Entry Point (when run directly)
# =============================================================================

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Initialize logging
    init_logging || {
        echo "[WARN] Logging initialization failed" >&2
    }

    case "${1:-}" in
        --select-interface)
            select_network_interface "${2:-false}" "${3:-}"
            exit $?
            ;;
        --configure-ip)
            configure_static_ip "$2" "$3" "$4"
            exit $?
            ;;
        --tune-network)
            tune_network_interface "$2"
            exit $?
            ;;
        --configure-firewall)
            configure_firewall "${2:-true}"
            exit $?
            ;;
        --configure-tmpfs)
            configure_tmpfs
            exit $?
            ;;
        --configure-sqlite)
            configure_sqlite
            exit $?
            ;;
        --configure-logrotate)
            configure_log_rotation
            exit $?
            ;;
        --configure-all)
            configure_all_network_storage "$2" "$3"
            exit $?
            ;;
        --help|-h)
            echo "Water-Controller Network/Storage Module v$NETWORK_STORAGE_VERSION"
            echo ""
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  --select-interface [non-interactive] [default]"
            echo "                              Select network interface"
            echo "  --configure-ip <iface> [ip] [netmask]"
            echo "                              Configure static IP"
            echo "  --tune-network <iface>      Tune network for PROFINET"
            echo "  --configure-firewall [allow-ssh]"
            echo "                              Configure firewall rules"
            echo "  --configure-tmpfs           Setup tmpfs for write endurance"
            echo "  --configure-sqlite          Configure SQLite WAL mode"
            echo "  --configure-logrotate       Setup log rotation"
            echo "  --configure-all [iface] [ip]"
            echo "                              Run all configuration"
            echo "  --help, -h                  Show this help"
            echo ""
            echo "Defaults:"
            echo "  IP: $DEFAULT_STATIC_IP"
            echo "  Netmask: $DEFAULT_NETMASK"
            echo "  API Port: $DEFAULT_API_PORT"
            ;;
        *)
            echo "Usage: $0 [--select-interface|--configure-ip|--tune-network|--configure-firewall|--configure-tmpfs|--configure-sqlite|--configure-logrotate|--configure-all|--help]" >&2
            exit 1
            ;;
    esac
fi
