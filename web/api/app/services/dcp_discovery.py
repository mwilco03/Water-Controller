"""
Water Treatment Controller - PROFINET DCP Discovery
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Real PROFINET DCP (Discovery and Configuration Protocol) implementation.
Performs Layer 2 multicast discovery to find PROFINET devices on the network.

Requires:
- CAP_NET_RAW capability (or root)
- Host network mode (to access physical interface)
"""

import asyncio
import logging
import os
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# PROFINET DCP constants
PROFINET_ETHERTYPE = 0x8892
DCP_MULTICAST_MAC = b'\x01\x0e\xcf\x00\x00\x00'
DCP_SERVICE_ID_IDENTIFY = 0x05
DCP_SERVICE_TYPE_REQUEST = 0x00
DCP_SERVICE_TYPE_RESPONSE = 0x01

# DCP Block options
DCP_OPTION_IP = 0x01
DCP_OPTION_DEVICE = 0x02
DCP_OPTION_DHCP = 0x03
DCP_OPTION_CONTROL = 0x05
DCP_OPTION_ALL = 0xFF

# DCP Sub-options
DCP_SUBOPTION_IP_ADDRESS = 0x02
DCP_SUBOPTION_DEVICE_VENDOR = 0x01
DCP_SUBOPTION_DEVICE_NAME = 0x02
DCP_SUBOPTION_DEVICE_ID = 0x03
DCP_SUBOPTION_DEVICE_ROLE = 0x04


@dataclass
class DCPDevice:
    """Discovered PROFINET device."""
    mac_address: str
    ip_address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    device_name: str | None = None
    vendor_id: int | None = None
    device_id: int | None = None
    vendor_name: str | None = None
    device_role: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mac_address": self.mac_address,
            "ip_address": self.ip_address,
            "device_name": self.device_name,
            "vendor_name": self.vendor_name or self._lookup_vendor_name(),
            "device_type": "PROFINET Device",
            "profinet_vendor_id": self.vendor_id,
            "profinet_device_id": self.device_id,
        }

    def _lookup_vendor_name(self) -> str:
        """Look up vendor name from vendor ID."""
        # Common PROFINET vendor IDs
        vendors = {
            0x002A: "Siemens",
            0x00A0: "Phoenix Contact",
            0x0120: "Wago",
            0x0493: "Water-Treat RTU",  # Our custom device
            0x006C: "Beckhoff",
            0x0113: "Turck",
        }
        return vendors.get(self.vendor_id, f"Vendor 0x{self.vendor_id:04X}" if self.vendor_id else "Unknown")


def get_interface_mac(interface: str) -> bytes:
    """Get MAC address of network interface."""
    try:
        with open(f"/sys/class/net/{interface}/address", "r") as f:
            mac_str = f.read().strip()
            return bytes.fromhex(mac_str.replace(":", ""))
    except (FileNotFoundError, PermissionError) as e:
        logger.warning(f"Could not get MAC for {interface}: {e}")
        # Return a default MAC
        return b'\x00\x00\x00\x00\x00\x01'


def build_dcp_identify_all_frame(src_mac: bytes, xid: int = 0x12345678) -> bytes:
    """
    Build a PROFINET DCP Identify All request frame.

    Frame structure:
    - Ethernet header (14 bytes): dst_mac, src_mac, ethertype
    - Frame ID (2 bytes): 0xFEFE for DCP Identify Request
    - DCP header (10 bytes): service_id, service_type, xid, response_delay, data_length
    - DCP block (4 bytes): option=0xFF (all), suboption=0xFF, length=0
    """
    # Ethernet header
    dst_mac = DCP_MULTICAST_MAC
    ethertype = struct.pack(">H", PROFINET_ETHERTYPE)
    eth_header = dst_mac + src_mac + ethertype

    # Frame ID - 0xFEFE for DCP Identify Request
    frame_id = struct.pack(">H", 0xFEFE)

    # DCP header
    service_id = DCP_SERVICE_ID_IDENTIFY
    service_type = DCP_SERVICE_TYPE_REQUEST
    response_delay = 0x0001  # 10ms units, so 10ms delay
    data_length = 4  # Length of DCP blocks

    dcp_header = struct.pack(">BBIHH",
                             service_id,
                             service_type,
                             xid,
                             response_delay,
                             data_length)

    # DCP block - Identify All (option=0xFF, suboption=0xFF)
    dcp_block = struct.pack(">BBH", DCP_OPTION_ALL, 0xFF, 0)

    return eth_header + frame_id + dcp_header + dcp_block


def parse_dcp_response(data: bytes) -> DCPDevice | None:
    """
    Parse a DCP Identify response frame.

    Returns DCPDevice with extracted information, or None if not a valid response.
    """
    if len(data) < 16:  # Minimum: 14 (eth) + 2 (frame_id)
        return None

    # Ethernet header
    dst_mac = data[0:6]
    src_mac = data[6:12]
    ethertype = struct.unpack(">H", data[12:14])[0]

    if ethertype != PROFINET_ETHERTYPE:
        return None

    # Frame ID at offset 14
    frame_id = struct.unpack(">H", data[14:16])[0]

    # Accept DCP response frame IDs (0xFEFC-0xFEFF)
    if frame_id < 0xFEFC or frame_id > 0xFEFF:
        return None

    # Format MAC address
    mac_str = ":".join(f"{b:02X}" for b in src_mac)

    # DCP header starts at offset 16 (after frame ID)
    if len(data) < 26:
        return None

    service_id = data[16]
    service_type = data[17]

    if service_id != DCP_SERVICE_ID_IDENTIFY or service_type != DCP_SERVICE_TYPE_RESPONSE:
        return None

    # Parse XID and data length
    xid = struct.unpack(">I", data[18:22])[0]
    response_delay = struct.unpack(">H", data[22:24])[0]
    data_length = struct.unpack(">H", data[24:26])[0]

    device = DCPDevice(mac_address=mac_str)

    # Parse DCP blocks starting at offset 26
    offset = 26
    end = min(26 + data_length, len(data))

    while offset + 4 <= end:
        option = data[offset]
        suboption = data[offset + 1]
        block_length = struct.unpack(">H", data[offset + 2:offset + 4])[0]

        block_data = data[offset + 4:offset + 4 + block_length]

        if option == DCP_OPTION_IP and suboption == DCP_SUBOPTION_IP_ADDRESS:
            # IP address block: block_info (2 bytes) + IP (4) + subnet (4) + gateway (4)
            if len(block_data) >= 14:
                ip_bytes = block_data[2:6]
                subnet_bytes = block_data[6:10]
                gw_bytes = block_data[10:14]
                device.ip_address = ".".join(str(b) for b in ip_bytes)
                device.subnet_mask = ".".join(str(b) for b in subnet_bytes)
                device.gateway = ".".join(str(b) for b in gw_bytes)

        elif option == DCP_OPTION_DEVICE and suboption == DCP_SUBOPTION_DEVICE_NAME:
            # Device name (station name)
            if len(block_data) >= 2:
                name_bytes = block_data[2:]  # Skip block_info
                try:
                    device.device_name = name_bytes.rstrip(b'\x00').decode('ascii', errors='replace')
                except Exception as e:
                    logger.debug(f"Failed to decode device name: {e}")

        elif option == DCP_OPTION_DEVICE and suboption == DCP_SUBOPTION_DEVICE_ID:
            # Vendor ID and Device ID
            if len(block_data) >= 6:
                device.vendor_id = struct.unpack(">H", block_data[2:4])[0]
                device.device_id = struct.unpack(">H", block_data[4:6])[0]

        elif option == DCP_OPTION_DEVICE and suboption == DCP_SUBOPTION_DEVICE_VENDOR:
            # Vendor name string
            if len(block_data) >= 2:
                try:
                    device.vendor_name = block_data[2:].rstrip(b'\x00').decode('ascii', errors='replace')
                except Exception as e:
                    logger.debug(f"Failed to decode vendor name: {e}")

        elif option == DCP_OPTION_DEVICE and suboption == DCP_SUBOPTION_DEVICE_ROLE:
            # Device role
            if len(block_data) >= 4:
                device.device_role = struct.unpack(">H", block_data[2:4])[0]

        # Move to next block (aligned to 2 bytes)
        offset += 4 + block_length
        if block_length % 2:
            offset += 1  # Padding

    return device


def discover_profinet_devices_sync(
    interface: str | None = None,
    timeout_sec: float = 5.0
) -> list[DCPDevice]:
    """
    Synchronous PROFINET DCP discovery.

    Sends DCP Identify All multicast and collects responses.
    Requires CAP_NET_RAW capability.

    Args:
        interface: Network interface. Auto-detected if None.
        timeout_sec: Discovery timeout in seconds.
    """
    if interface is None:
        from ..core.network import get_profinet_interface
        interface = get_profinet_interface()
    devices: list[DCPDevice] = []
    seen_macs: set[str] = set()

    try:
        # Create raw socket for PROFINET
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(PROFINET_ETHERTYPE))
        sock.bind((interface, 0))
        sock.settimeout(0.1)  # Short timeout for recv loop

        # Get our MAC address
        src_mac = get_interface_mac(interface)

        # Build and send DCP Identify All frame
        xid = int(time.time() * 1000) & 0xFFFFFFFF
        frame = build_dcp_identify_all_frame(src_mac, xid)

        logger.info(f"Sending DCP Identify All on {interface}")
        sock.send(frame)

        # Collect responses until timeout
        end_time = time.time() + timeout_sec
        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(1500)
                device = parse_dcp_response(data)
                if device and device.mac_address not in seen_macs:
                    seen_macs.add(device.mac_address)
                    devices.append(device)
                    logger.info(f"Discovered: {device.device_name or 'Unknown'} at {device.ip_address} ({device.mac_address})")
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Error receiving DCP response: {e}")

        sock.close()
        logger.info(f"DCP discovery complete: found {len(devices)} devices")

    except PermissionError:
        logger.error("DCP discovery requires CAP_NET_RAW capability. Run with sudo or add capability.")
        raise
    except OSError as e:
        logger.error(f"Network error during DCP discovery: {e}")
        raise

    return devices


async def discover_profinet_devices(
    interface: str | None = None,
    timeout_sec: float = 5.0
) -> list[dict[str, Any]]:
    """
    Async wrapper for PROFINET DCP discovery.

    Args:
        interface: Network interface to use. Auto-detected if not specified.
        timeout_sec: Discovery timeout in seconds.

    Returns:
        List of discovered device dictionaries.
    """
    if interface is None:
        # Use auto-detection instead of hardcoded eth0
        from ..core.network import get_profinet_interface
        interface = get_profinet_interface()  # Let RuntimeError propagate

    # Run synchronous discovery in thread pool
    loop = asyncio.get_event_loop()
    devices = await loop.run_in_executor(
        None,
        discover_profinet_devices_sync,
        interface,
        timeout_sec
    )
    return [d.to_dict() for d in devices]
    # PermissionError and OSError propagate to caller for proper HTTP error handling
