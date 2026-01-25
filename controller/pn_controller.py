#!/usr/bin/env python3
"""
PROFINET IO Controller - Manual packet building
No dependency on Scapy contrib modules
"""

import struct
import socket
import uuid
import time
from typing import Optional

# Constants
RPC_PORT = 34964
PNIO_INTERFACE_UUID = bytes.fromhex("dea000016c9711d1827100a02442df7d")
PROFINET_ETHERTYPE = 0x8892

# Block types
BLOCK_AR_REQ = 0x0101
BLOCK_IOCR_REQ = 0x0102
BLOCK_ALARM_CR_REQ = 0x0103
BLOCK_EXPECTED_SUBMOD = 0x0104

# Module IDs
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041


def build_block_header(block_type: int, length: int) -> bytes:
    """Build PNIO block header: type(2) + length(2) + version(2)"""
    return struct.pack(">HHbb", block_type, length, 1, 0)


def build_ar_block(ar_uuid: bytes, session_key: int, mac: bytes) -> bytes:
    """Build ARBlockReq"""
    station = b"controller"
    content = struct.pack(">H", 0x0001)  # AR Type: IOCAR
    content += ar_uuid  # 16 bytes
    content += struct.pack(">H", session_key)
    content += mac  # 6 bytes
    content += struct.pack(">H", 0x0001)  # Object UUID version
    content += PNIO_INTERFACE_UUID  # 16 bytes
    content += uuid.uuid4().bytes  # CMInitiatorObjectUUID
    content += struct.pack(">I", 0x00000011)  # AR Properties
    content += struct.pack(">H", 100)  # Timeout
    content += struct.pack(">H", len(station))  # Station name length
    content += station

    header = build_block_header(BLOCK_AR_REQ, len(content) + 2)
    return header + content


def build_iocr_block(iocr_type: int, ref: int, frame_id: int, data_len: int) -> bytes:
    """Build IOCRBlockReq"""
    content = struct.pack(">H", iocr_type)  # 1=Input, 2=Output
    content += struct.pack(">H", ref)
    content += struct.pack(">H", PROFINET_ETHERTYPE)  # LT
    content += struct.pack(">I", 0x00000000)  # Properties (RT Class 1)
    content += struct.pack(">H", data_len)
    content += struct.pack(">H", frame_id)
    content += struct.pack(">H", 32)  # SendClockFactor
    content += struct.pack(">H", 32)  # ReductionRatio
    content += struct.pack(">H", 1)   # Phase
    content += struct.pack(">I", 0xFFFFFFFF)  # FrameSendOffset
    content += struct.pack(">H", 10)  # WatchdogFactor
    content += struct.pack(">H", 10)  # DataHoldFactor
    content += struct.pack(">H", 0)   # Reserved
    content += b"\x00" * 6  # CMInitiatorMAC
    content += struct.pack(">H", 0)  # SubframeData/reserved
    content += struct.pack(">H", 0)  # NumberOfAPIs

    header = build_block_header(BLOCK_IOCR_REQ, len(content) + 2)
    return header + content


def build_alarm_cr_block() -> bytes:
    """Build AlarmCRBlockReq - BlockLength=18 for RT_CLASS_1"""
    content = struct.pack(">H", 0x0001)  # AlarmCRType
    content += struct.pack(">H", PROFINET_ETHERTYPE)  # LT
    content += struct.pack(">I", 0x00000000)  # Properties
    content += struct.pack(">H", 100)  # RTATimeoutFactor
    content += struct.pack(">H", 3)    # RTARetries
    content += struct.pack(">H", 1)    # LocalAlarmReference
    content += struct.pack(">H", 128)  # MaxAlarmDataLength (128 not 200!)
    # No tag headers for RT_CLASS_1

    header = build_block_header(BLOCK_ALARM_CR_REQ, len(content) + 2)
    return header + content


def build_expected_submod_block() -> bytes:
    """Build ExpectedSubmoduleBlockReq for DAP + CPU Temp"""
    content = struct.pack(">H", 1)  # NumberOfAPIs

    # API 0
    content += struct.pack(">I", 0)  # API number
    content += struct.pack(">H", 2)  # SlotCount (DAP + Temp)

    # Slot 0: DAP
    content += struct.pack(">H", 0)  # SlotNumber
    content += struct.pack(">I", MOD_DAP)  # ModuleIdentNumber
    content += struct.pack(">H", 0)  # ModuleProperties
    content += struct.pack(">H", 1)  # NumberOfSubmodules
    content += struct.pack(">H", 1)  # SubslotNumber
    content += struct.pack(">I", SUBMOD_DAP)
    content += struct.pack(">H", 0)  # SubmoduleProperties
    content += struct.pack(">H", 0)  # DataDescriptionCount

    # Slot 1: CPU Temp (5 bytes input)
    content += struct.pack(">H", 1)  # SlotNumber
    content += struct.pack(">I", MOD_TEMP)
    content += struct.pack(">H", 0)  # ModuleProperties
    content += struct.pack(">H", 1)  # NumberOfSubmodules
    content += struct.pack(">H", 1)  # SubslotNumber
    content += struct.pack(">I", SUBMOD_TEMP)
    content += struct.pack(">H", 0x0001)  # SubmoduleProperties: Input
    content += struct.pack(">H", 1)  # DataDescriptionCount
    content += struct.pack(">H", 0x0001)  # DataDescription Type: Input
    content += struct.pack(">H", 5)  # Length: 5 bytes
    content += struct.pack(">B", 0)  # IOCSLength
    content += struct.pack(">B", 1)  # IOPSLength

    header = build_block_header(BLOCK_EXPECTED_SUBMOD, len(content) + 2)
    return header + content


def build_rpc_header(opnum: int, activity_uuid: bytes, frag_len: int) -> bytes:
    """Build DCE/RPC header"""
    hdr = struct.pack("<B", 4)  # Version
    hdr += struct.pack("<B", 0)  # Packet type: Request
    hdr += struct.pack("<H", 0x0020)  # Flags: First frag
    hdr += struct.pack("<I", 0x00000010)  # Data representation (LE, ASCII, IEEE)
    hdr += struct.pack("<H", 0)  # Serial high
    hdr += PNIO_INTERFACE_UUID  # Interface UUID (LE)
    hdr += activity_uuid  # Activity UUID
    hdr += struct.pack("<I", 0)  # Server boot time
    hdr += struct.pack("<I", 1)  # Interface version
    hdr += struct.pack("<I", 0)  # Sequence number
    hdr += struct.pack("<H", opnum)  # Opnum: 0=Connect
    hdr += struct.pack("<H", 0)  # Interface hint
    hdr += struct.pack("<H", 0)  # Activity hint
    hdr += struct.pack("<H", frag_len)  # Fragment length
    hdr += struct.pack("<H", 0)  # Fragment number
    hdr += struct.pack("<B", 0x02)  # Auth length (dummy)
    hdr += struct.pack("<B", 0)  # Serial low
    return hdr


def build_connect_request(ar_uuid: bytes, session_key: int, mac: bytes) -> bytes:
    """Build complete Connect Request"""
    # PNIO blocks
    blocks = b""
    blocks += build_ar_block(ar_uuid, session_key, mac)
    blocks += build_iocr_block(1, 1, 0x8001, 6)  # Input IOCR
    blocks += build_iocr_block(2, 2, 0x8000, 1)  # Output IOCR
    blocks += build_alarm_cr_block()
    blocks += build_expected_submod_block()

    # NDR header
    ndr = struct.pack("<I", len(blocks))  # ArgsMaximum
    ndr += struct.pack("<I", len(blocks))  # ArgsLength
    ndr += struct.pack("<I", len(blocks))  # MaxCount
    ndr += struct.pack("<I", 0)  # Offset
    ndr += struct.pack("<I", len(blocks))  # ActualCount
    ndr += blocks

    # RPC header
    activity = uuid.uuid4().bytes
    rpc = build_rpc_header(0, activity, len(ndr))

    return rpc + ndr


def connect(device_ip: str, mac: bytes) -> bool:
    """Connect to PROFINET device"""
    ar_uuid = uuid.uuid4().bytes

    pkt = build_connect_request(ar_uuid, 1, mac)

    print(f"[RPC] Sending Connect Request ({len(pkt)} bytes) to {device_ip}:{RPC_PORT}")
    print(f"[RPC] AlarmCR BlockLength=18 (no tag headers)")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        sock.sendto(pkt, (device_ip, RPC_PORT))
        resp, addr = sock.recvfrom(4096)
        print(f"[RPC] Response: {len(resp)} bytes")

        # Parse PNIO Status (after RPC header at offset 80)
        if len(resp) > 84:
            status = resp[80:84]
            print(f"[RPC] PNIO Status: {status.hex()}")
            if status == b"\x00\x00\x00\x00":
                print("[RPC] SUCCESS!")
                return True
            else:
                print(f"[RPC] Error: code={status[0]:02x} decode={status[1]:02x} "
                      f"code1={status[2]:02x} code2={status[3]:02x}")
        return False
    except socket.timeout:
        print("[RPC] Timeout")
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    import sys
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.6.7"
    mac = bytes.fromhex("020000000001")  # Placeholder
    connect(ip, mac)
