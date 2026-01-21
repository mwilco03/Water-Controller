#!/bin/bash
# =============================================================================
# Water Treatment Controller - Uninstall Module
# =============================================================================
# Uninstallation logic and helper functions.
# Depends on: common.sh (logging)

# Prevent double-sourcing
[[ -n "${_WTC_UNINSTALL_LOADED:-}" ]] && return 0
_WTC_UNINSTALL_LOADED=1

# =============================================================================
# Global Uninstall State
# =============================================================================

# Arrays to track what was removed/preserved (used by do_uninstall)
UNINSTALL_REMOVED_ITEMS=()
UNINSTALL_PRESERVED_ITEMS=()

# =============================================================================
# Main Uninstall Function
# =============================================================================

do_uninstall() {
    log_info "Starting uninstallation process..."

    local manifest_file="/tmp/water-controller-uninstall-manifest-$(date +%Y%m%d_%H%M%S).txt"
    # Reset global arrays
    UNINSTALL_REMOVED_ITEMS=()
    UNINSTALL_PRESERVED_ITEMS=()
    local errors=0

    if [ "${DRY_RUN:-0}" -eq 1 ]; then
        log_info "[DRY RUN] Would uninstall Water Controller"
        log_info "  - Stop and disable service"
        log_info "  - Remove ${INSTALL_DIR:-/opt/water-controller}"
        log_info "  - Remove service file"
        log_info "  - Remove logrotate config"
        log_info "  - Remove tmpfs mount from fstab"
        if [ "${KEEP_DATA:-0}" -eq 0 ]; then
            log_info "  - Remove ${CONFIG_DIR:-/etc/water-controller} (with confirmation)"
            log_info "  - Remove ${DATA_DIR:-/var/lib/water-controller} (with confirmation)"
            log_info "  - Remove ${LOG_DIR:-/var/log/water-controller} (with confirmation)"
            log_info "  - Remove ${BACKUP_DIR:-/var/backups/water-controller} (with confirmation)"
        else
            log_info "  - Preserve ${CONFIG_DIR:-/etc/water-controller} (--keep-data)"
            log_info "  - Preserve ${DATA_DIR:-/var/lib/water-controller} (--keep-data)"
            log_info "  - Preserve ${LOG_DIR:-/var/log/water-controller} (--keep-data)"
            log_info "  - Preserve ${BACKUP_DIR:-/var/backups/water-controller} (--keep-data)"
        fi
        if [ "${PURGE_MODE:-0}" -eq 1 ]; then
            log_info "  - Remove P-Net libraries and headers (--purge)"
            log_info "  - Remove firewall rules (--purge)"
            log_info "  - Remove udev rules (--purge)"
            log_info "  - Remove network configuration (--purge)"
        fi
        return 0
    fi

    # Confirm uninstallation
    local confirm_msg="This will remove the Water Controller installation."
    if [ "${PURGE_MODE:-0}" -eq 1 ]; then
        confirm_msg="$confirm_msg Including P-Net libraries, firewall rules, and udev rules (PURGE mode)."
    fi
    if [ "${KEEP_DATA:-0}" -eq 1 ]; then
        confirm_msg="$confirm_msg Configuration and data will be PRESERVED."
    fi
    confirm_msg="$confirm_msg Continue?"

    if ! confirm "$confirm_msg" "n"; then
        log_info "Uninstallation cancelled"
        return 0
    fi

    # Initialize manifest
    {
        echo "Water Controller Uninstall Manifest"
        echo "===================================="
        echo "Date: $(date -Iseconds)"
        echo "Mode: ${PURGE_MODE:+PURGE }${KEEP_DATA:+KEEP-DATA }STANDARD"
        echo ""
        echo "Removed Items:"
    } > "$manifest_file"

    # Stop service
    log_info "Stopping service..."
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl stop water-controller.service 2>/dev/null || true
        sudo systemctl disable water-controller.service 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Service: water-controller.service (stopped and disabled)")
    fi

    # Remove service file
    log_info "Removing service file..."
    if [ -f /etc/systemd/system/water-controller.service ]; then
        sudo rm -f /etc/systemd/system/water-controller.service
        UNINSTALL_REMOVED_ITEMS+=("File: /etc/systemd/system/water-controller.service")
    fi
    sudo systemctl daemon-reload 2>/dev/null || true

    # Remove installation directory
    log_info "Removing installation directory..."
    if [ -d "${INSTALL_DIR:-/opt/water-controller}" ]; then
        sudo rm -rf "${INSTALL_DIR:-/opt/water-controller}" || ((errors++))
        UNINSTALL_REMOVED_ITEMS+=("Directory: ${INSTALL_DIR:-/opt/water-controller}")
    fi

    # Handle configuration based on --keep-data flag
    if [ -d "${CONFIG_DIR:-/etc/water-controller}" ]; then
        if [ "${KEEP_DATA:-0}" -eq 1 ]; then
            log_info "Configuration preserved at ${CONFIG_DIR:-/etc/water-controller} (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${CONFIG_DIR:-/etc/water-controller}")
        elif confirm "Remove configuration directory (${CONFIG_DIR:-/etc/water-controller})?" "n"; then
            sudo rm -rf "${CONFIG_DIR:-/etc/water-controller}" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: ${CONFIG_DIR:-/etc/water-controller}")
        else
            log_info "Configuration preserved at ${CONFIG_DIR:-/etc/water-controller}"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${CONFIG_DIR:-/etc/water-controller}")
        fi
    fi

    # Handle data directory based on --keep-data flag
    if [ -d "${DATA_DIR:-/var/lib/water-controller}" ]; then
        if [ "${KEEP_DATA:-0}" -eq 1 ]; then
            log_info "Data preserved at ${DATA_DIR:-/var/lib/water-controller} (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${DATA_DIR:-/var/lib/water-controller}")
        elif confirm "Remove data directory (${DATA_DIR:-/var/lib/water-controller})? This includes the database!" "n"; then
            sudo rm -rf "${DATA_DIR:-/var/lib/water-controller}" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: ${DATA_DIR:-/var/lib/water-controller}")
        else
            log_info "Data preserved at ${DATA_DIR:-/var/lib/water-controller}"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${DATA_DIR:-/var/lib/water-controller}")
        fi
    fi

    # Handle logs based on --keep-data flag
    if [ -d "${LOG_DIR:-/var/log/water-controller}" ]; then
        if [ "${KEEP_DATA:-0}" -eq 1 ]; then
            log_info "Logs preserved at ${LOG_DIR:-/var/log/water-controller} (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${LOG_DIR:-/var/log/water-controller}")
        elif confirm "Remove log directory (${LOG_DIR:-/var/log/water-controller})?" "n"; then
            sudo rm -rf "${LOG_DIR:-/var/log/water-controller}" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: ${LOG_DIR:-/var/log/water-controller}")
        else
            log_info "Logs preserved at ${LOG_DIR:-/var/log/water-controller}"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${LOG_DIR:-/var/log/water-controller}")
        fi
    fi

    # Handle backups based on --keep-data flag
    if [ -d "${BACKUP_DIR:-/var/backups/water-controller}" ]; then
        if [ "${KEEP_DATA:-0}" -eq 1 ]; then
            log_info "Backups preserved at ${BACKUP_DIR:-/var/backups/water-controller} (--keep-data)"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${BACKUP_DIR:-/var/backups/water-controller}")
        elif confirm "Remove backup directory (${BACKUP_DIR:-/var/backups/water-controller})?" "n"; then
            sudo rm -rf "${BACKUP_DIR:-/var/backups/water-controller}" || ((errors++))
            UNINSTALL_REMOVED_ITEMS+=("Directory: ${BACKUP_DIR:-/var/backups/water-controller}")
        else
            log_info "Backups preserved at ${BACKUP_DIR:-/var/backups/water-controller}"
            UNINSTALL_PRESERVED_ITEMS+=("Directory: ${BACKUP_DIR:-/var/backups/water-controller}")
        fi
    fi

    # Ask about service user (only if not keeping data)
    if [ "${KEEP_DATA:-0}" -eq 0 ]; then
        if id water-controller >/dev/null 2>&1; then
            if confirm "Remove service user (water-controller)?" "n"; then
                sudo userdel water-controller 2>/dev/null || ((errors++))
                UNINSTALL_REMOVED_ITEMS+=("User: water-controller")
            else
                log_info "Service user preserved"
                UNINSTALL_PRESERVED_ITEMS+=("User: water-controller")
            fi
        fi
    fi

    # Remove logrotate config
    if [ -f /etc/logrotate.d/water-controller ]; then
        sudo rm -f /etc/logrotate.d/water-controller 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("File: /etc/logrotate.d/water-controller")
    fi

    # Remove tmpfs mount from fstab
    if grep -q "water-controller" /etc/fstab 2>/dev/null; then
        log_info "Removing tmpfs mount from fstab..."
        sudo sed -i '/water-controller/d' /etc/fstab 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Fstab entry: water-controller tmpfs")
    fi

    # Unmount tmpfs if mounted
    if mountpoint -q /run/water-controller 2>/dev/null; then
        sudo umount /run/water-controller 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Mount: /run/water-controller")
    fi

    # =========================================================================
    # PURGE MODE: Remove P-Net, firewall rules, udev rules, network config
    # =========================================================================
    if [ "${PURGE_MODE:-0}" -eq 1 ]; then
        log_info "PURGE MODE: Removing additional components..."

        # Remove P-Net libraries
        _uninstall_pnet_libraries || ((errors++))

        # Remove firewall rules
        _uninstall_firewall_rules || ((errors++))

        # Remove udev rules
        _uninstall_udev_rules || ((errors++))

        # Remove network configuration (optional, with confirmation)
        if confirm "Remove Water Controller network configuration (static IP, etc.)?" "n"; then
            _uninstall_network_config || ((errors++))
        else
            UNINSTALL_PRESERVED_ITEMS+=("Network configuration")
        fi
    fi

    # Write manifest
    for item in "${UNINSTALL_REMOVED_ITEMS[@]}"; do
        echo "  - $item" >> "$manifest_file"
    done

    if [ ${#UNINSTALL_PRESERVED_ITEMS[@]} -gt 0 ]; then
        echo "" >> "$manifest_file"
        echo "Preserved Items:" >> "$manifest_file"
        for item in "${UNINSTALL_PRESERVED_ITEMS[@]}"; do
            echo "  - $item" >> "$manifest_file"
        done
    fi

    echo "" >> "$manifest_file"
    echo "Errors: $errors" >> "$manifest_file"
    echo "Manifest saved to: $manifest_file" >> "$manifest_file"

    log_info "Uninstall manifest saved to: $manifest_file"

    if [ $errors -eq 0 ]; then
        log_info "Uninstallation completed successfully"
    else
        log_warn "Uninstallation completed with $errors errors"
    fi

    return 0
}

# =============================================================================
# Uninstall Helper Functions
# =============================================================================

# Remove P-Net libraries and related files
_uninstall_pnet_libraries() {
    log_info "Removing P-Net libraries..."
    local removed=0

    # P-Net library locations
    local pnet_lib_paths=(
        "/usr/local/lib/libpnet.so"
        "/usr/local/lib/libpnet.so.*"
        "/usr/local/lib/libpnet.a"
        "/usr/lib/libpnet.so"
        "/usr/lib/libpnet.so.*"
        "/usr/lib/libpnet.a"
    )

    # Remove library files
    for pattern in "${pnet_lib_paths[@]}"; do
        # shellcheck disable=SC2086
        for lib_file in $pattern; do
            if [ -f "$lib_file" ]; then
                sudo rm -f "$lib_file" 2>/dev/null && {
                    log_info "  Removed: $lib_file"
                    UNINSTALL_REMOVED_ITEMS+=("P-Net: $lib_file")
                    ((removed++))
                }
            fi
        done
    done

    # Remove P-Net headers
    local pnet_include_paths=(
        "/usr/local/include/pnet"
        "/usr/local/include/pnet_api.h"
        "/usr/include/pnet"
        "/usr/include/pnet_api.h"
    )

    for path in "${pnet_include_paths[@]}"; do
        if [ -e "$path" ]; then
            sudo rm -rf "$path" 2>/dev/null && {
                log_info "  Removed: $path"
                UNINSTALL_REMOVED_ITEMS+=("P-Net: $path")
                ((removed++))
            }
        fi
    done

    # Remove P-Net config directory
    if [ -d "/etc/pnet" ]; then
        sudo rm -rf /etc/pnet 2>/dev/null && {
            log_info "  Removed: /etc/pnet"
            UNINSTALL_REMOVED_ITEMS+=("P-Net: /etc/pnet")
            ((removed++))
        }
    fi

    # Remove P-Net sample application
    if [ -d "/opt/pnet-sample" ]; then
        sudo rm -rf /opt/pnet-sample 2>/dev/null && {
            log_info "  Removed: /opt/pnet-sample"
            UNINSTALL_REMOVED_ITEMS+=("P-Net: /opt/pnet-sample")
            ((removed++))
        }
    fi

    # Remove P-Net pkg-config file
    local pkgconfig_paths=(
        "/usr/local/lib/pkgconfig/pnet.pc"
        "/usr/lib/pkgconfig/pnet.pc"
    )

    for pc_file in "${pkgconfig_paths[@]}"; do
        if [ -f "$pc_file" ]; then
            sudo rm -f "$pc_file" 2>/dev/null && {
                log_info "  Removed: $pc_file"
                UNINSTALL_REMOVED_ITEMS+=("P-Net: $pc_file")
                ((removed++))
            }
        fi
    done

    # Update library cache
    if [ $removed -gt 0 ]; then
        sudo ldconfig 2>/dev/null || true
        log_info "  Updated library cache (ldconfig)"
    fi

    log_info "P-Net cleanup complete ($removed items removed)"
    return 0
}

# Remove firewall rules added by Water Controller
_uninstall_firewall_rules() {
    log_info "Removing firewall rules..."

    # Detect and clean up based on firewall system
    if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
        log_info "  Cleaning UFW rules..."
        sudo ufw delete allow 8000/tcp 2>/dev/null || true
        sudo ufw delete allow 34964/udp 2>/dev/null || true
        sudo ufw delete allow 34962:34963/tcp 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Firewall: UFW rules (ports 8000, 34962-34964)")
        log_info "  UFW rules removed"

    elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active firewalld >/dev/null 2>&1; then
        log_info "  Cleaning firewalld rules..."
        sudo firewall-cmd --permanent --remove-port=8000/tcp 2>/dev/null || true
        sudo firewall-cmd --permanent --remove-port=34964/udp 2>/dev/null || true
        sudo firewall-cmd --permanent --remove-port=34962-34963/tcp 2>/dev/null || true
        sudo firewall-cmd --reload 2>/dev/null || true
        UNINSTALL_REMOVED_ITEMS+=("Firewall: firewalld rules (ports 8000, 34962-34964)")
        log_info "  firewalld rules removed"

    elif command -v nft >/dev/null 2>&1; then
        log_info "  Cleaning nftables rules..."
        sudo nft delete table inet water_controller 2>/dev/null || true
        if [ -f /etc/nftables.d/water-controller.nft ]; then
            sudo rm -f /etc/nftables.d/water-controller.nft 2>/dev/null || true
            UNINSTALL_REMOVED_ITEMS+=("Firewall: /etc/nftables.d/water-controller.nft")
            log_info "  Removed: /etc/nftables.d/water-controller.nft"
        fi
        UNINSTALL_REMOVED_ITEMS+=("Firewall: nftables table water_controller")
        log_info "  nftables rules removed"

    elif command -v iptables >/dev/null 2>&1; then
        log_info "  Cleaning iptables rules..."
        sudo iptables -D INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true
        sudo iptables -D INPUT -p udp --dport 34964 -j ACCEPT 2>/dev/null || true
        sudo iptables -D INPUT -p tcp --dport 34962:34963 -j ACCEPT 2>/dev/null || true
        if command -v iptables-save >/dev/null 2>&1; then
            if [ -d /etc/iptables ]; then
                sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null 2>/dev/null
            elif command -v netfilter-persistent >/dev/null 2>&1; then
                sudo netfilter-persistent save 2>/dev/null || true
            fi
        fi
        UNINSTALL_REMOVED_ITEMS+=("Firewall: iptables rules (ports 8000, 34962-34964)")
        log_info "  iptables rules removed"
    else
        log_info "  No active firewall detected, skipping"
    fi

    return 0
}

# Remove udev rules added by Water Controller
_uninstall_udev_rules() {
    log_info "Removing udev rules..."

    local udev_rules=(
        "/etc/udev/rules.d/99-water-controller-network.rules"
        "/etc/udev/rules.d/99-water-controller.rules"
        "/etc/udev/rules.d/99-pnet.rules"
    )

    local removed=0
    for rule_file in "${udev_rules[@]}"; do
        if [ -f "$rule_file" ]; then
            sudo rm -f "$rule_file" 2>/dev/null && {
                log_info "  Removed: $rule_file"
                UNINSTALL_REMOVED_ITEMS+=("udev: $rule_file")
                ((removed++))
            }
        fi
    done

    # Reload udev rules if any were removed
    if [ $removed -gt 0 ]; then
        sudo udevadm control --reload-rules 2>/dev/null || true
        sudo udevadm trigger 2>/dev/null || true
        log_info "  Reloaded udev rules"
    fi

    log_info "udev cleanup complete ($removed rules removed)"
    return 0
}

# Remove network configuration added by Water Controller
_uninstall_network_config() {
    log_info "Removing network configuration..."

    # Remove systemd-networkd config
    local networkd_configs=(
        "/etc/systemd/network/10-water-controller-*.network"
    )
    for pattern in "${networkd_configs[@]}"; do
        # shellcheck disable=SC2086
        for config_file in $pattern; do
            if [ -f "$config_file" ]; then
                sudo rm -f "$config_file" 2>/dev/null && {
                    log_info "  Removed: $config_file"
                    UNINSTALL_REMOVED_ITEMS+=("Network: $config_file")
                }
            fi
        done
    done

    # Remove NetworkManager connections
    if command -v nmcli >/dev/null 2>&1; then
        local nm_connections
        nm_connections=$(nmcli -t -f NAME connection show 2>/dev/null | grep "water-controller")
        while IFS= read -r conn; do
            if [ -n "$conn" ]; then
                sudo nmcli connection delete "$conn" 2>/dev/null && {
                    log_info "  Removed NetworkManager connection: $conn"
                    UNINSTALL_REMOVED_ITEMS+=("Network: NetworkManager connection $conn")
                }
            fi
        done <<< "$nm_connections"
    fi

    # Remove dhcpcd configuration entries
    if [ -f /etc/dhcpcd.conf ]; then
        if grep -q "Water-Controller" /etc/dhcpcd.conf 2>/dev/null; then
            log_info "  Cleaning dhcpcd.conf..."
            sudo cp /etc/dhcpcd.conf /etc/dhcpcd.conf.pre-uninstall 2>/dev/null
            sudo sed -i '/# Water-Controller/,/^interface\|^$/d' /etc/dhcpcd.conf 2>/dev/null || true
            UNINSTALL_REMOVED_ITEMS+=("Network: dhcpcd.conf entries (backup saved)")
            log_info "  Cleaned dhcpcd.conf (backup: /etc/dhcpcd.conf.pre-uninstall)"
        fi
    fi

    # Remove interfaces.d config
    local interfaces_d_configs=(
        "/etc/network/interfaces.d/water-controller-*"
    )
    for pattern in "${interfaces_d_configs[@]}"; do
        # shellcheck disable=SC2086
        for config_file in $pattern; do
            if [ -f "$config_file" ]; then
                sudo rm -f "$config_file" 2>/dev/null && {
                    log_info "  Removed: $config_file"
                    UNINSTALL_REMOVED_ITEMS+=("Network: $config_file")
                }
            fi
        done
    done

    log_info "Network configuration cleanup complete"
    return 0
}
