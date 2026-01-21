#!/bin/sh
# Water Treatment Controller - Entrypoint Script
# Copyright (C) 2024-2025
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Auto-detects network interface if WTC_INTERFACE is not set.
# This avoids the anti-pattern of hardcoding "eth0" which doesn't
# exist on modern Linux systems with predictable interface names.

set -e

# Clean up stale shared memory from previous runs
# This ensures fresh creation with correct permissions (0666)
SHM_NAME="${WTC_SHM_NAME:-/wtc_shared_memory}"
SHM_PATH="/dev/shm${SHM_NAME}"
if [ -e "$SHM_PATH" ]; then
    echo "Cleaning up stale shared memory: $SHM_PATH"
    rm -f "$SHM_PATH"
fi

# Auto-detect network interface if not specified
detect_interface() {
    # Priority order:
    # 1. Explicit WTC_INTERFACE environment variable
    # 2. First non-loopback, non-virtual interface that is UP
    # 3. Fall back to first non-loopback interface

    if [ -n "$WTC_INTERFACE" ] && [ "$WTC_INTERFACE" != "auto" ]; then
        # Validate the specified interface exists
        if ip link show "$WTC_INTERFACE" >/dev/null 2>&1; then
            echo "$WTC_INTERFACE"
            return 0
        else
            echo "WARNING: Specified interface '$WTC_INTERFACE' not found, auto-detecting..." >&2
        fi
    fi

    # Get list of interfaces, excluding loopback and virtual interfaces
    # Virtual interfaces: docker*, veth*, br-*, virbr*, lo
    for iface in $(ip -o link show | awk -F': ' '{print $2}' | cut -d@ -f1); do
        case "$iface" in
            lo|docker*|veth*|br-*|virbr*|vnet*)
                # Skip loopback and virtual interfaces
                continue
                ;;
        esac

        # Check if interface is UP and has a link
        if ip link show "$iface" 2>/dev/null | grep -q "state UP"; then
            echo "$iface"
            return 0
        fi
    done

    # Fall back to first non-loopback physical interface (even if DOWN)
    for iface in $(ip -o link show | awk -F': ' '{print $2}' | cut -d@ -f1); do
        case "$iface" in
            lo|docker*|veth*|br-*|virbr*|vnet*)
                continue
                ;;
        esac
        echo "$iface"
        return 0
    done

    # Absolute fallback - shouldn't happen on any real system
    echo "ERROR: No suitable network interface found!" >&2
    echo "Available interfaces:" >&2
    ip -o link show >&2
    exit 1
}

# Detect interface
INTERFACE=$(detect_interface)
echo "Using network interface: $INTERFACE"

# Build command arguments
# Start with interface
ARGS="-i $INTERFACE"

# Add cycle time if specified
if [ -n "$WTC_CYCLE_TIME" ]; then
    ARGS="$ARGS -t $WTC_CYCLE_TIME"
fi

# Add log level if specified
case "$WTC_LOG_LEVEL" in
    TRACE|DEBUG|INFO|WARN|ERROR|FATAL)
        # Convert to lowercase for the controller
        LEVEL=$(echo "$WTC_LOG_LEVEL" | tr '[:upper:]' '[:lower:]')
        ARGS="$ARGS -l $LEVEL"
        ;;
esac

# Add simulation mode if enabled
if [ "$WTC_SIMULATION_MODE" = "true" ] || [ "$WTC_SIMULATION_MODE" = "1" ]; then
    ARGS="$ARGS --simulation"
    if [ -n "$WTC_SIMULATION_SCENARIO" ]; then
        ARGS="$ARGS --scenario $WTC_SIMULATION_SCENARIO"
    fi
fi

# Add any additional arguments passed to the container
if [ $# -gt 0 ]; then
    ARGS="$ARGS $*"
fi

echo "Starting water_treat_controller with: $ARGS"
exec water_treat_controller $ARGS
