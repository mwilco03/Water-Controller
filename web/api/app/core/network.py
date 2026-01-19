"""
Water Treatment Controller - Network Utilities
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Network interface detection and utilities.
Avoids anti-pattern of hardcoding "eth0" which doesn't exist on
modern Linux systems with predictable interface names.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for detected interface
_cached_interface: Optional[str] = None


def detect_network_interface() -> str:
    """
    Auto-detect the appropriate network interface for PROFINET communication.

    Priority:
    1. WTC_INTERFACE environment variable (if set and non-empty)
    2. First non-loopback, non-virtual interface that is UP
    3. First non-loopback physical interface (even if DOWN)

    Returns:
        Network interface name (e.g., "enp0s3", "eth0", "ens33")

    Raises:
        RuntimeError: If no suitable interface can be found
    """
    global _cached_interface

    # Check environment variable first
    env_interface = os.environ.get("WTC_INTERFACE", "").strip()
    if env_interface and env_interface != "auto":
        # Validate the specified interface exists
        if _interface_exists(env_interface):
            return env_interface
        else:
            logger.warning(
                f"Specified interface '{env_interface}' not found, auto-detecting..."
            )

    # Return cached result if available
    if _cached_interface is not None:
        return _cached_interface

    # Get list of network interfaces from /sys/class/net
    net_path = Path("/sys/class/net")
    if not net_path.exists():
        raise RuntimeError("Cannot access /sys/class/net - network subsystem unavailable")

    interfaces = sorted(net_path.iterdir())

    # Virtual interface patterns to exclude
    virtual_patterns = re.compile(
        r"^(lo|docker\d*|veth.*|br-.*|virbr\d*|vnet\d*|bond\d*|tun\d*|tap\d*)$"
    )

    # First pass: find UP interfaces
    for iface_path in interfaces:
        iface_name = iface_path.name

        # Skip virtual interfaces
        if virtual_patterns.match(iface_name):
            continue

        # Check if interface is UP
        operstate_file = iface_path / "operstate"
        if operstate_file.exists():
            try:
                state = operstate_file.read_text().strip()
                if state == "up":
                    logger.info(f"Auto-detected network interface: {iface_name} (state: UP)")
                    _cached_interface = iface_name
                    return iface_name
            except (PermissionError, IOError):
                pass

    # Second pass: any physical interface (even if DOWN)
    for iface_path in interfaces:
        iface_name = iface_path.name

        # Skip virtual interfaces
        if virtual_patterns.match(iface_name):
            continue

        # Skip wireless interfaces for PROFINET (not recommended)
        wireless_path = iface_path / "wireless"
        if wireless_path.exists():
            logger.debug(f"Skipping wireless interface: {iface_name}")
            continue

        logger.info(f"Auto-detected network interface: {iface_name} (may be DOWN)")
        _cached_interface = iface_name
        return iface_name

    # No suitable interface found
    available = [p.name for p in interfaces]
    raise RuntimeError(
        f"No suitable network interface found. Available: {available}. "
        "Set WTC_INTERFACE environment variable to specify one explicitly."
    )


def _interface_exists(interface: str) -> bool:
    """Check if a network interface exists."""
    return Path(f"/sys/class/net/{interface}").exists()


def get_interface_info(interface: str) -> dict:
    """
    Get information about a network interface.

    Returns:
        Dictionary with interface info (mac, state, mtu, etc.)
    """
    net_path = Path(f"/sys/class/net/{interface}")
    if not net_path.exists():
        return {"error": f"Interface {interface} not found"}

    info = {"name": interface}

    # MAC address
    addr_file = net_path / "address"
    if addr_file.exists():
        try:
            info["mac_address"] = addr_file.read_text().strip()
        except (PermissionError, IOError):
            pass

    # Operational state
    state_file = net_path / "operstate"
    if state_file.exists():
        try:
            info["state"] = state_file.read_text().strip()
        except (PermissionError, IOError):
            pass

    # MTU
    mtu_file = net_path / "mtu"
    if mtu_file.exists():
        try:
            info["mtu"] = int(mtu_file.read_text().strip())
        except (PermissionError, IOError, ValueError):
            pass

    return info


def list_network_interfaces() -> list[dict]:
    """
    List all available network interfaces with their info.

    Returns:
        List of interface info dictionaries
    """
    net_path = Path("/sys/class/net")
    if not net_path.exists():
        return []

    interfaces = []
    for iface_path in sorted(net_path.iterdir()):
        info = get_interface_info(iface_path.name)
        interfaces.append(info)

    return interfaces


# Convenient function for getting the interface to use
def get_profinet_interface() -> str:
    """
    Get the network interface to use for PROFINET communication.

    This is the main entry point - uses auto-detection if WTC_INTERFACE
    is not set.
    """
    return detect_network_interface()
