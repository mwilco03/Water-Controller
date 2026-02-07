#!/usr/bin/env python3
"""
PROFINET Controller Test Script - RPC Reference Implementation

Uses existing working DCP discovery, focuses on testing RPC Connect.
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
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

# Add parent directory to path to import working DCP code
sys.path.insert(0, str(Path(__file__).parent.parent / "web" / "api"))

try:
    from app.services.dcp_discovery import (
        build_dcp_identify_all_frame,
        parse_dcp_response,
        get_interface_mac,
        DCPDevice
    )
except ImportError as e:
    print(f"ERROR: Could not import DCP discovery: {e}")
    print("Make sure you're running from the repo root")
    sys.exit(1)

try:
    from scapy.layers.inet import UDP, IP
    from scapy.all import Raw
except ImportError as e:
    print(f"ERROR: Scapy not available: {e}")
    print("Install with: pip3 install scapy")
    sys.exit(1)

# Constants
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


class ProfinetControllerTest:
    """PROFINET Controller Test - uses working DCP, tests RPC Connect"""

    def __init__(self, interface: str = "eth0"):
        self.interface = interface
        self.mac_bytes = get_interface_mac(interface)
        self.mac = ':'.join(f'{b:02x}' for b in self.mac_bytes)

        self.ar_uuid = uuid4().bytes
        self.activity_uuid = uuid4().bytes
        self.session_key = 1

        logger.info(f"Controller initialized on {interface} (MAC: {self.mac})")

    def discover(self, timeout_s: float = 3.0, target_station: Optional[str] = None) -> List[DCPDevice]:
        """DCP discovery using working code from dcp_discovery.py"""
        logger.info(f"=== Phase 1: DCP Discovery (timeout={timeout_s}s) ===")
        logger.info("Using existing working DCP implementation (raw sockets)")

        if target_station:
            logger.info(f"Searching for station: {target_station}")
        else:
            logger.info("Searching for all devices")

        # Build DCP Identify frame using working code
        dcp_frame = build_dcp_identify_all_frame(self.mac_bytes)

        logger.info(f"DCP frame size: {len(dcp_frame)} bytes")
        logger.info(f"Hex dump:")
        for i in range(0, len(dcp_frame), 16):
            hex_str = ' '.join(f'{b:02x}' for b in dcp_frame[i:i+16])
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in dcp_frame[i:i+16])
            logger.info(f"  {i:04x}: {hex_str:<48} {ascii_str}")

        # Create raw socket
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x8892))
        sock.bind((self.interface, 0))
        sock.settimeout(timeout_s)

        discovered = []

        try:
            # Send DCP Identify
            sock.send(dcp_frame)
            logger.info("✓ Sent DCP Identify Request")

            # Receive responses
            start_time = time.time()
            while time.time() - start_time < timeout_s:
                try:
                    data = sock.recv(4096)
                    device = parse_dcp_response(data)
                    if device:
                        # Filter by station name if specified
                        if target_station and device.device_name != target_station:
                            continue

                        discovered.append(device)
                        logger.info(f"✓ Discovered: {device.device_name} @ {device.ip_address} ({device.mac_address})")

                        # If searching for specific station, stop after finding it
                        if target_station:
                            break

                except socket.timeout:
                    break

        finally:
            sock.close()

        logger.info(f"Discovery complete: found {len(discovered)} device(s)")
        return discovered

    def connect(self, device: DCPDevice) -> bool:
        """
        PROFINET RPC Connect Request - This is the critical part to compare!

        Sequence per IEC 61158-6-10:
        1. DCP Discovery (done above)
        2. RPC Connect Request → Connect Response
        3. RPC PrmEnd (IODControlReq) → PrmEnd Response
        4. Wait for device ApplicationReady
        5. Cyclic I/O
        """
        logger.info(f"\n=== Phase 2: RPC Connect to {device.device_name} ({device.ip_address}) ===")

        # Build Connect Request
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

            # Parse DCE/RPC response header
            if len(response) < 80:
                logger.error(f"✗ Response too short: {len(response)} bytes (expected ≥80)")
                return False

            # Check RPC ptype (should be 0x02 = Response)
            rpc_ptype = response[0]
            if rpc_ptype != 0x02:
                logger.error(f"✗ Invalid RPC ptype: 0x{rpc_ptype:02x} (expected 0x02 Response)")
                return False

            logger.info(f"✓ Valid RPC Response (ptype=0x02)")

            # Skip to PNIO blocks (after ~80 byte RPC header)
            # Look for ARBlockRes (0x8101)
            pos = 80
            found_ar_block = False
            ar_status = None

            while pos + 6 <= len(response):
                block_type = struct.unpack('>H', response[pos:pos+2])[0]
                block_length = struct.unpack('>H', response[pos+2:pos+4])[0]

                logger.info(f"  Block at offset {pos}: type=0x{block_type:04x} length={block_length}")

                if block_type == 0x8101:  # ARBlockRes
                    found_ar_block = True
                    if pos + 6 + 4 <= len(response):
                        # Status is at offset 6 within block content (after header)
                        ar_status = struct.unpack('>I', response[pos+6:pos+10])[0]
                        logger.info(f"  ARBlockRes Status: 0x{ar_status:08x}")
                    break

                # Move to next block (4 bytes header + block_length)
                pos += 4 + block_length

            if not found_ar_block:
                logger.error("✗ ARBlockRes not found in response")
                return False

            if ar_status is None:
                logger.error("✗ Could not parse AR status")
                return False

            # Check status (0x00000000 = success)
            if ar_status == 0x00000000:
                logger.info("✓ Connect succeeded! (AR Status = 0x00000000)")
                return True
            else:
                logger.error(f"✗ Connect failed with AR Status: 0x{ar_status:08x}")
                logger.error(f"  Error class: 0x{(ar_status >> 16) & 0xFF:02x}")
                logger.error(f"  Error code: 0x{ar_status & 0xFF:02x}")
                return False

        except socket.timeout:
            logger.error("✗ Connect timeout - no response from RTU")
            logger.error("  This means RTU rejected the packet or couldn't parse it")
            return False
        except Exception as e:
            logger.error(f"✗ Connect failed: {e}")
            return False
        finally:
            sock.close()

    def _build_connect_request(self, device: DCPDevice) -> bytes:
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

        # --- DCE/RPC Header (build manually to match C code) ---
        rpc_header = bytearray()

        # DCE/RPC header fields
        rpc_header += struct.pack('B', 0x04)  # rpc_vers = 4
        rpc_header += struct.pack('B', 0x00)  # rpc_vers_minor = 0
        rpc_header += struct.pack('B', 0x00)  # ptype = request
        rpc_header += struct.pack('B', 0x00)  # pfc_flags = 0
        rpc_header += struct.pack('BBBB', 0x10, 0x00, 0x00, 0x00)  # packed_drep (little-endian)
        rpc_header += struct.pack('<H', 0)  # frag_length (fill later)
        rpc_header += struct.pack('<H', 0)  # auth_length = 0
        rpc_header += struct.pack('<I', 0)  # call_id = 0

        # UUID byte swapping helper (per commit 84649b6)
        def swap_uuid_fields(uuid_bytes):
            """Swap first 8 bytes of UUID to LE per DREP=0x10"""
            uuid = bytearray(uuid_bytes)
            # time_low (0-3): reverse
            uuid[0], uuid[3] = uuid[3], uuid[0]
            uuid[1], uuid[2] = uuid[2], uuid[1]
            # time_mid (4-5): reverse
            uuid[4], uuid[5] = uuid[5], uuid[4]
            # time_hi_and_version (6-7): reverse
            uuid[6], uuid[7] = uuid[7], uuid[6]
            # Bytes 8-15: unchanged
            return bytes(uuid)

        # Object UUID (PNIO UUID) - swap to LE
        rpc_header += swap_uuid_fields(PNIO_UUID)

        # Interface UUID (PNIO UUID) - swap to LE
        rpc_header += swap_uuid_fields(PNIO_UUID)

        # Activity UUID - swap to LE
        rpc_header += swap_uuid_fields(self.activity_uuid)

        # Server boot time
        rpc_header += struct.pack('<I', 0)

        # Interface version
        rpc_header += struct.pack('<I', 1)

        # Sequence number
        rpc_header += struct.pack('<I', 0)

        # Operation number (0 = Connect)
        rpc_header += struct.pack('<H', 0)

        # Interface hint
        rpc_header += struct.pack('<H', 0xffff)

        # Activity hint
        rpc_header += struct.pack('<H', 0xffff)

        # Fragment length (reserve 2 bytes)
        rpc_header += struct.pack('<H', 0)  # Will be filled later

        # Fragment number
        rpc_header += struct.pack('<H', 0)

        # Auth protocol
        rpc_header += struct.pack('B', 0)

        # Serial high
        rpc_header += struct.pack('B', 0)

        # --- NDR Header (20 bytes, mandatory per Bug 0.4) ---
        # p-net rejects requests without NDR header (pf_cmrpc.c:4622-4634)
        # This goes BETWEEN RPC header and PNIO blocks
        # Will be filled after we know PNIO blocks length
        ndr_header_pos = len(rpc_header)
        rpc_header += bytes(20)  # Reserve 20 bytes

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
        logger.info(f"  RPC header: 88 bytes")
        logger.info(f"  NDR header: 20 bytes (mandatory per Bug 0.4)")
        logger.info(f"  ARBlockReq: {len(ar_block)} bytes")
        logger.info(f"  IOCRBlockReq (input): {len(iocr_input)} bytes")
        logger.info(f"  IOCRBlockReq (output): {len(iocr_output)} bytes")
        logger.info(f"  AlarmCRBlockReq: {len(alarm_block)} bytes")
        logger.info(f"  ExpectedSubmoduleBlockReq: {len(expected_submod)} bytes")
        logger.info(f"  Total PNIO data: {len(pnio_data)} bytes")

        # Combine RPC header + PNIO data
        rpc_payload = bytearray(rpc_header) + pnio_data

        # Fill in NDR header (20 bytes at ndr_header_pos)
        pnio_len = len(pnio_data)
        args_maximum = 4096  # Max buffer size
        # ArgsMaximum (4 bytes LE)
        struct.pack_into('<I', rpc_payload, ndr_header_pos, args_maximum)
        # ArgsLength (4 bytes LE)
        struct.pack_into('<I', rpc_payload, ndr_header_pos + 4, pnio_len)
        # MaxCount (4 bytes LE) = ArgsLength
        struct.pack_into('<I', rpc_payload, ndr_header_pos + 8, pnio_len)
        # Offset (4 bytes LE) = 0
        struct.pack_into('<I', rpc_payload, ndr_header_pos + 12, 0)
        # ActualCount (4 bytes LE) = ArgsLength
        struct.pack_into('<I', rpc_payload, ndr_header_pos + 16, pnio_len)

        # Fill in frag_length in RPC header (offset 8, 2 bytes little-endian)
        frag_length = len(rpc_payload)
        struct.pack_into('<H', rpc_payload, 8, frag_length)
        rpc_payload = bytes(rpc_payload)

        logger.info(f"  Total RPC payload: {len(rpc_payload)} bytes")

        # Wrap in IP/UDP using Scapy
        # Let kernel select source IP based on routing (don't use 0.0.0.0!)
        pkt = (
            IP(dst=device.ip_address) /
            UDP(sport=RPC_PORT, dport=RPC_PORT) /
            Raw(load=rpc_payload)
        )

        return pkt

    def _build_ar_block_req(self, device: DCPDevice) -> bytes:
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
        station_name = device.device_name.encode('utf-8')
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

    logger.info("=== PROFINET RPC Test - Using Working DCP + Scapy RPC ===\n")
    logger.info("This script uses existing working DCP discovery")
    logger.info("and demonstrates RPC Connect packet format for comparison")
    logger.info("Run tcpdump in another terminal to capture packets:")
    logger.info(f"  sudo tcpdump -i {args.interface} -w profinet-test.pcap '(ether proto 0x8892) or (udp port {RPC_PORT})'\n")

    # Create controller
    ctrl = ProfinetControllerTest(interface=args.interface)

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
