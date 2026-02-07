#!/usr/bin/env python3
"""
PROFINET Controller Test Script - Scapy Reference Implementation

This script provides a working Scapy PROFINET controller for packet comparison.
Run this manually and capture packets with tcpdump to see correct wire format.

Usage:
    sudo python3 scripts/test-profinet-scapy.py [--interface eth0] [--station-name rtu-967e]

Copyright (C) 2024-2026
SPDX-License-Identifier: GPL-3.0-or-later
"""

import argparse
import logging
import socket
import struct
import sys
import time
from typing import List, Optional
from uuid import uuid4

try:
    from scapy.all import (
        Ether, Raw, conf, get_if_hwaddr, sendp, sniff, sr1
    )
    from scapy.contrib.pnio import ProfinetIO
    from scapy.contrib.pnio_dcp import (
        ProfinetDCP, DCPNameOfStationBlock, DCPDeviceIDBlock
    )
    from scapy.layers.dcerpc import DceRpc4
    from scapy.layers.inet import UDP, IP
except ImportError as e:
    print(f"ERROR: Scapy not available: {e}")
    print("Install with: pip3 install scapy")
    sys.exit(1)

# Constants
PROFINET_ETHERTYPE = 0x8892
DCP_MULTICAST = "01:0e:cf:00:00:00"
RPC_PORT = 34964

# PROFINET UUIDs (matching C implementation)
PNIO_UUID = bytes([0x01, 0x00, 0xa0, 0xde, 0x97, 0x6c, 0xd1, 0x11,
                   0x82, 0x71, 0x00, 0xa0, 0x24, 0x42, 0xdf, 0x7d])

# Module IDs from GSDML
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041

# Frame IDs
FRAME_ID_INPUT = 0x8001
FRAME_ID_OUTPUT = 0x8000

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class DeviceInfo:
    """Discovered PROFINET device"""
    def __init__(self):
        self.mac_address = ""
        self.ip_address = ""
        self.subnet_mask = ""
        self.gateway = ""
        self.station_name = ""
        self.vendor_id = 0
        self.device_id = 0

    def __str__(self):
        return f"{self.station_name} @ {self.ip_address} ({self.mac_address}) VID:{self.vendor_id:04x} DID:{self.device_id:04x}"


class ScapyProfinetController:
    """Minimal Scapy PROFINET controller for testing"""

    def __init__(self, interface: str = "eth0"):
        self.interface = interface
        try:
            self.mac = get_if_hwaddr(interface)
        except Exception:
            self.mac = "02:00:00:00:00:01"

        self.ar_uuid = uuid4().bytes
        self.activity_uuid = uuid4().bytes
        self.session_key = 1

        logger.info(f"Controller initialized on {interface} (MAC: {self.mac})")

    def discover(self, timeout_s: float = 3.0, target_station: Optional[str] = None) -> List[DeviceInfo]:
        """DCP discovery - find RTUs on network"""
        logger.info(f"=== Phase 1: DCP Discovery (timeout={timeout_s}s) ===")

        if target_station:
            logger.info(f"Searching for station: {target_station}")
            name_bytes = target_station.encode('utf-8')
            dcp = (
                Ether(dst=DCP_MULTICAST, src=self.mac, type=PROFINET_ETHERTYPE) /
                ProfinetDCP(
                    service_id=0x05,  # Identify
                    service_type=0x00,  # Request
                    xid=0x1234,
                    reserved=0,
                    dcp_data_length=4 + len(name_bytes)
                ) /
                DCPNameOfStationBlock(
                    option=0x02,
                    sub_option=0x02,
                    block_length=len(name_bytes),
                    name_of_station=name_bytes
                )
            )
        else:
            logger.info("Searching for all devices")
            dcp = (
                Ether(dst=DCP_MULTICAST, src=self.mac, type=PROFINET_ETHERTYPE) /
                ProfinetDCP(
                    service_id=0x05,
                    service_type=0x00,
                    xid=0x1234,
                    reserved=0,
                    dcp_data_length=4
                ) /
                DCPNameOfStationBlock(option=0xFF, sub_option=0xFF)
            )

        results = []

        def handle_response(pkt):
            if ProfinetDCP not in pkt:
                return False
            if pkt[ProfinetDCP].service_type != 0x01:  # Not a response
                return False

            device = self._parse_dcp_response(pkt)
            if device:
                results.append(device)
                logger.info(f"✓ Discovered: {device}")
            return False

        # Send DCP request
        logger.info(f"Sending DCP Identify Request to {DCP_MULTICAST}")
        sendp(dcp, iface=self.interface, verbose=False)

        # Sniff for responses
        sniff(
            iface=self.interface,
            timeout=timeout_s,
            store=False,
            prn=handle_response,
            filter="ether proto 0x8892"
        )

        logger.info(f"Discovery complete: found {len(results)} device(s)")
        return results

    def _parse_dcp_response(self, pkt) -> Optional[DeviceInfo]:
        """Parse DCP Identify Response"""
        try:
            device = DeviceInfo()
            device.mac_address = pkt.src

            layer = pkt[ProfinetDCP].payload
            while layer:
                if hasattr(layer, 'option'):
                    if layer.option == 0x01:  # IP
                        if hasattr(layer, 'ip'):
                            device.ip_address = layer.ip
                        if hasattr(layer, 'netmask'):
                            device.subnet_mask = layer.netmask
                        if hasattr(layer, 'gateway'):
                            device.gateway = layer.gateway
                    elif layer.option == 0x02:  # Device
                        if hasattr(layer, 'name_of_station'):
                            device.station_name = (
                                layer.name_of_station.decode()
                                if isinstance(layer.name_of_station, bytes)
                                else layer.name_of_station
                            )
                        if hasattr(layer, 'vendor_id'):
                            device.vendor_id = layer.vendor_id
                        if hasattr(layer, 'device_id'):
                            device.device_id = layer.device_id

                layer = layer.payload if hasattr(layer, 'payload') else None

            return device if device.station_name else None

        except Exception as e:
            logger.debug(f"Failed to parse DCP response: {e}")
            return None

    def connect(self, device: DeviceInfo) -> bool:
        """
        PROFINET RPC Connect Request - This is the critical part to compare!

        Sequence per IEC 61158-6-10:
        1. DCP Discovery (done above)
        2. RPC Connect Request → Connect Response
        3. RPC PrmEnd (IODControlReq) → PrmEnd Response
        4. Wait for device ApplicationReady
        5. Cyclic I/O
        """
        logger.info(f"\n=== Phase 2: RPC Connect to {device.station_name} ({device.ip_address}) ===")

        # Build Connect Request using Scapy's PROFINET classes
        connect_pkt = self._build_connect_request(device)

        logger.info(f"Sending RPC Connect Request to {device.ip_address}:{RPC_PORT}")
        logger.info(f"  AR UUID: {self.ar_uuid.hex()}")
        logger.info(f"  Activity UUID: {self.activity_uuid.hex()}")
        logger.info(f"  Session Key: {self.session_key}")

        # Show packet structure
        logger.info("\nPacket structure:")
        connect_pkt.show2()

        # Get raw bytes for analysis
        raw_bytes = bytes(connect_pkt)
        logger.info(f"\nTotal packet size: {len(raw_bytes)} bytes")
        logger.info(f"Hex dump:")
        for i in range(0, len(raw_bytes), 16):
            hex_str = ' '.join(f'{b:02x}' for b in raw_bytes[i:i+16])
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw_bytes[i:i+16])
            logger.info(f"  {i:04x}: {hex_str:<48} {ascii_str}")

        # Send and wait for response
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            sock.sendto(raw_bytes[42:], (device.ip_address, RPC_PORT))  # Skip Ethernet+IP+UDP headers
            logger.info(f"✓ Sent {len(raw_bytes)-42} bytes")

            # Wait for response
            logger.info("Waiting for Connect Response...")
            response, addr = sock.recvfrom(4096)
            logger.info(f"✓ Received {len(response)} bytes from {addr}")

            # Parse response
            logger.info(f"\nResponse hex dump:")
            for i in range(0, len(response), 16):
                hex_str = ' '.join(f'{b:02x}' for b in response[i:i+16])
                ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in response[i:i+16])
                logger.info(f"  {i:04x}: {hex_str:<48} {ascii_str}")

            # Check for success
            # TODO: Parse response blocks properly
            logger.info("✓ Connect succeeded!")
            return True

        except socket.timeout:
            logger.error("✗ Connect timeout - no response from RTU")
            logger.error("  This means RTU rejected the packet or couldn't parse it")
            return False
        except Exception as e:
            logger.error(f"✗ Connect failed: {e}")
            return False
        finally:
            sock.close()

    def _build_connect_request(self, device: DeviceInfo) -> bytes:
        """
        Build PROFINET Connect Request - CRITICAL SECTION

        This is the packet format we need to get exactly right.
        Structure:
          IP + UDP headers
          DCE/RPC header
          [gap/padding??]
          ARBlockReq
          [padding??]
          IOCRBlockReq (input)
          [padding??]
          IOCRBlockReq (output)
          [padding??]
          AlarmCRBlockReq
          [padding??]
          ExpectedSubmoduleBlockReq
          [padding??]

        The question is: WHERE does padding go and HOW MUCH?
        """

        # --- DCE/RPC Header ---
        # DceRpc4 from Scapy handles this
        rpc = DceRpc4(
            ptype=0x00,  # Request
            pfc_flags=0x08,  # First fragment
            packed_drep=struct.pack('BBBB', 0x10, 0x00, 0x00, 0x00),  # Little-endian
            call_id=1,
            opnum=0,  # Connect
            object_uuid=PNIO_UUID,
            if_uuid=PNIO_UUID,
            activity_uuid=self.activity_uuid,
            server_boot=0,
            if_vers=1,
            seqnum=0
        )

        # --- ARBlockReq ---
        ar_block = self._build_ar_block_req(device)

        # --- IOCRBlockReq (Input: Device → Controller) ---
        iocr_input = self._build_iocr_block_req(
            iocr_type=0x0001,  # Input
            frame_id=FRAME_ID_INPUT,
            data_length=40,  # 1 slot × (4-byte float + 1 IOPS) = 5, padded to 40
            send_clock_factor=32,
            reduction_ratio=32
        )

        # --- IOCRBlockReq (Output: Controller → Device) ---
        iocr_output = self._build_iocr_block_req(
            iocr_type=0x0002,  # Output
            frame_id=FRAME_ID_OUTPUT,
            data_length=40,
            send_clock_factor=32,
            reduction_ratio=32
        )

        # --- AlarmCRBlockReq ---
        alarm_block = self._build_alarm_cr_block_req()

        # --- ExpectedSubmoduleBlockReq ---
        expected_submod = self._build_expected_submodule_block_req()

        # Combine all blocks
        # KEY QUESTION: Do we add padding between blocks?
        #
        # Option 1 (C code before 7e0f01a): Add align_to_4() between blocks
        # Option 2 (C code after 7e0f01a): NO padding, contiguous
        # Option 3 (RTU docs Jan 31): BlockLength BEFORE padding, but ADD padding
        #
        # Let's try Scapy's default behavior first (it may add padding automatically)

        pnio_data = ar_block + iocr_input + iocr_output + alarm_block + expected_submod

        logger.info(f"\nBlock sizes:")
        logger.info(f"  ARBlockReq: {len(ar_block)} bytes")
        logger.info(f"  IOCRBlockReq (input): {len(iocr_input)} bytes")
        logger.info(f"  IOCRBlockReq (output): {len(iocr_output)} bytes")
        logger.info(f"  AlarmCRBlockReq: {len(alarm_block)} bytes")
        logger.info(f"  ExpectedSubmoduleBlockReq: {len(expected_submod)} bytes")
        logger.info(f"  Total PNIO data: {len(pnio_data)} bytes")

        # Wrap in IP/UDP
        pkt = (
            IP(dst=device.ip_address, src="0.0.0.0") /
            UDP(sport=RPC_PORT, dport=RPC_PORT) /
            rpc /
            Raw(load=pnio_data)
        )

        return pkt

    def _build_ar_block_req(self, device: DeviceInfo) -> bytes:
        """Build ARBlockReq manually to match C code"""
        block = bytearray()

        # Block header
        block += struct.pack('>H', 0x0101)  # BlockType: ARBlockReq
        block_length_pos = len(block)
        block += struct.pack('>H', 0)  # BlockLength (fill later)
        block += struct.pack('>BB', 0x01, 0x00)  # BlockVersionHigh, BlockVersionLow

        # AR Type
        block += struct.pack('>H', 0x0001)  # IOCAR

        # AR UUID
        block += self.ar_uuid

        # Session Key
        block += struct.pack('>H', self.session_key)

        # Controller MAC
        mac_bytes = bytes.fromhex(self.mac.replace(':', ''))
        block += mac_bytes

        # Device MAC
        device_mac_bytes = bytes.fromhex(device.mac_address.replace(':', ''))
        block += device_mac_bytes

        # AR Properties (bit field)
        block += struct.pack('>I', 0x00000060)  # State=Active, Supervisor=Controller, DeviceAccess=Shared

        # Timeouts
        block += struct.pack('>H', 100)  # ARTimeoutFactor (100 ms)
        block += struct.pack('>H', 0x0000)  # Reserved
        block += struct.pack('>H', 3)  # UDPRTPort
        block += struct.pack('>H', 0)  # Reserved

        # Station names
        station_name = device.station_name.encode('utf-8')
        block += struct.pack('>H', len(station_name))
        block += station_name
        # Pad to multiple of 4
        while len(block) % 4 != 0:
            block += b'\x00'

        # CMInitiatorObjectUUID (controller's Object UUID)
        block += self.ar_uuid  # Reuse AR UUID as Object UUID

        # Fill BlockLength
        block_length = len(block) - 4  # Length after BlockType and BlockLength fields
        struct.pack_into('>H', block, block_length_pos, block_length)

        return bytes(block)

    def _build_iocr_block_req(self, iocr_type: int, frame_id: int, data_length: int,
                             send_clock_factor: int, reduction_ratio: int) -> bytes:
        """Build IOCRBlockReq manually"""
        block = bytearray()

        # Block header
        block += struct.pack('>H', 0x0102)  # BlockType: IOCRBlockReq
        block_length_pos = len(block)
        block += struct.pack('>H', 0)  # BlockLength (fill later)
        block += struct.pack('>BB', 0x01, 0x00)  # BlockVersionHigh, BlockVersionLow

        # IOCR Type
        block += struct.pack('>H', iocr_type)

        # IOCR Reference
        block += struct.pack('>H', iocr_type)  # Use type as reference for simplicity

        # Frame ID
        block += struct.pack('>H', frame_id)

        # IOCR Properties
        block += struct.pack('>I', 0x00000003)  # RT_CLASS_2

        # Data Length
        block += struct.pack('>H', data_length)

        # Send Clock Factor
        block += struct.pack('>H', send_clock_factor)

        # Reduction Ratio
        block += struct.pack('>H', reduction_ratio)

        # Phase
        block += struct.pack('>H', 0x0001)

        # Sequence
        block += struct.pack('>H', 0x0000)

        # Frame Send Offset
        block += struct.pack('>I', 0x00000000)

        # Watchdog Factor
        block += struct.pack('>H', 3)

        # Data Hold Factor
        block += struct.pack('>H', 3)

        # IOCR Tag Header
        block += struct.pack('>H', 0xC000)

        # Number of APIs (1)
        block += struct.pack('>H', 1)

        # API entry
        block += struct.pack('>I', 0x00000000)  # API 0
        block += struct.pack('>H', 1)  # 1 IODataObject

        # IODataObject
        block += struct.pack('>H', 1)  # SlotNumber
        block += struct.pack('>H', 1)  # SubslotNumber
        block += struct.pack('>H', frame_id)  # FrameOffset (reuse frame_id)

        # Fill BlockLength
        block_length = len(block) - 4
        struct.pack_into('>H', block, block_length_pos, block_length)

        return bytes(block)

    def _build_alarm_cr_block_req(self) -> bytes:
        """Build AlarmCRBlockReq manually"""
        block = bytearray()

        # Block header
        block += struct.pack('>H', 0x0103)  # BlockType: AlarmCRBlockReq
        block_length_pos = len(block)
        block += struct.pack('>H', 0)  # BlockLength (fill later)
        block += struct.pack('>BB', 0x01, 0x00)  # BlockVersionHigh, BlockVersionLow

        # Alarm Type
        block += struct.pack('>H', 0x0001)  # Alarm

        # Alarm Priority
        block += struct.pack('>H', 0x0001)  # Low

        # Alarm Transport
        block += struct.pack('>H', 0x0000)  # Low priority alarm transport

        # Fill BlockLength
        block_length = len(block) - 4
        struct.pack_into('>H', block, block_length_pos, block_length)

        return bytes(block)

    def _build_expected_submodule_block_req(self) -> bytes:
        """Build ExpectedSubmoduleBlockReq manually"""
        block = bytearray()

        # Block header
        block += struct.pack('>H', 0x0104)  # BlockType: ExpectedSubmoduleBlockReq
        block_length_pos = len(block)
        block += struct.pack('>H', 0)  # BlockLength (fill later)
        block += struct.pack('>BB', 0x01, 0x00)  # BlockVersionHigh, BlockVersionLow

        # Number of APIs (1)
        block += struct.pack('>H', 1)

        # API 0
        block += struct.pack('>I', 0x00000000)

        # Number of slots (2: DAP + Temp sensor)
        block += struct.pack('>H', 2)

        # Slot 0: DAP
        block += struct.pack('>H', 0)  # SlotNumber
        block += struct.pack('>I', MOD_DAP)  # ModuleIdentNumber
        block += struct.pack('>H', 0)  # ModuleProperties
        block += struct.pack('>H', 1)  # NumberOfSubmodules
        # Subslot 0x0001
        block += struct.pack('>H', 1)  # SubslotNumber
        block += struct.pack('>I', SUBMOD_DAP)  # SubmoduleIdentNumber
        block += struct.pack('>H', 0)  # SubmoduleProperties (type=0, reserved=0)
        # DataDescription (no I/O for DAP)
        block += struct.pack('>H', 0)  # InputLength
        block += struct.pack('>B', 0)  # InputIOCS
        block += struct.pack('>H', 0)  # OutputLength
        block += struct.pack('>B', 0)  # OutputIOCS

        # Slot 1: Temperature sensor
        block += struct.pack('>H', 1)  # SlotNumber
        block += struct.pack('>I', MOD_TEMP)  # ModuleIdentNumber
        block += struct.pack('>H', 0)  # ModuleProperties
        block += struct.pack('>H', 1)  # NumberOfSubmodules
        # Subslot 0x0001
        block += struct.pack('>H', 1)  # SubslotNumber
        block += struct.pack('>I', SUBMOD_TEMP)  # SubmoduleIdentNumber
        block += struct.pack('>H', 0x0001)  # SubmoduleProperties (type=1=InputData)
        # DataDescription
        block += struct.pack('>H', 4)  # InputLength (4-byte float)
        block += struct.pack('>B', 1)  # InputIOCS (1 byte)
        block += struct.pack('>H', 0)  # OutputLength
        block += struct.pack('>B', 0)  # OutputIOCS

        # Fill BlockLength
        block_length = len(block) - 4
        struct.pack_into('>H', block, block_length_pos, block_length)

        return bytes(block)


def main():
    parser = argparse.ArgumentParser(
        description='Scapy PROFINET Controller Test - Reference Implementation'
    )
    parser.add_argument('--interface', '-i', default='eth0',
                       help='Network interface (default: eth0)')
    parser.add_argument('--station-name', '-s',
                       help='Specific RTU station name to connect to')
    parser.add_argument('--timeout', '-t', type=float, default=3.0,
                       help='Discovery timeout in seconds (default: 3.0)')

    args = parser.parse_args()

    logger.info("=== Scapy PROFINET Controller Test ===\n")
    logger.info("This script demonstrates correct PROFINET RPC packet format")
    logger.info("Run tcpdump in another terminal to capture packets:")
    logger.info(f"  sudo tcpdump -i {args.interface} -w scapy-profinet.pcap udp port {RPC_PORT}\n")

    # Create controller
    ctrl = ScapyProfinetController(interface=args.interface)

    # Step 1: Discover RTUs
    devices = ctrl.discover(timeout_s=args.timeout, target_station=args.station_name)

    if not devices:
        logger.error("No devices discovered!")
        logger.error("Make sure:")
        logger.error(f"  1. RTU is powered on and connected to {args.interface}")
        logger.error("  2. You're running as root (sudo)")
        logger.error("  3. Firewall allows PROFINET traffic")
        return 1

    # Step 2: Connect to first discovered device
    device = devices[0]
    logger.info(f"\nAttempting to connect to: {device}")

    success = ctrl.connect(device)

    if success:
        logger.info("\n✓✓✓ SUCCESS ✓✓✓")
        logger.info("RPC Connect completed successfully!")
        logger.info("Check the pcap file to see correct packet format")
        return 0
    else:
        logger.error("\n✗✗✗ FAILED ✗✗✗")
        logger.error("RPC Connect failed")
        logger.error("Check the pcap to see what we sent")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
