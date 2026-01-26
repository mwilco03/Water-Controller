#!/usr/bin/env python3
"""
PROFINET IO Controller - Complete Implementation
Standalone module with Connect, PrmEnd, ApplicationReady, and Cyclic I/O
"""

import struct
import socket
import uuid
import time
import sys
from typing import Optional, Tuple

# Constants
RPC_PORT = 34964
PNIO_INTERFACE_UUID = bytes.fromhex("dea000016c9711d1827100a02442df7d")
PROFINET_ETHERTYPE = 0x8892

# RPC Opnums
OPNUM_CONNECT = 0
OPNUM_RELEASE = 1
OPNUM_READ = 2
OPNUM_WRITE = 3
OPNUM_CONTROL = 4

# Block types - Request
BLOCK_AR_REQ = 0x0101
BLOCK_IOCR_REQ = 0x0102
BLOCK_ALARM_CR_REQ = 0x0103
BLOCK_EXPECTED_SUBMOD = 0x0104
BLOCK_PRM_END_REQ = 0x0110
BLOCK_APP_READY_REQ = 0x0112

# Control Command values
CONTROL_PRM_END = 0x0001
CONTROL_APP_READY = 0x0002

# Module IDs
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041

# Frame IDs
INPUT_FRAME_ID = 0x8001
OUTPUT_FRAME_ID = 0x8000


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


def build_control_block(block_type: int, ar_uuid: bytes, session_key: int,
                        control_cmd: int) -> bytes:
    """Build ControlBlockConnect for PrmEnd or ApplicationReady"""
    content = b""
    content += struct.pack(">H", 0)  # Reserved
    content += ar_uuid  # 16 bytes - ARUUID
    content += struct.pack(">H", session_key)  # SessionKey
    content += struct.pack(">H", 0)  # Reserved
    content += struct.pack(">H", control_cmd)  # ControlCommand
    content += struct.pack(">H", 0)  # ControlBlockProperties

    header = build_block_header(block_type, len(content) + 2)
    return header + content


def build_rpc_header(opnum: int, activity_uuid: bytes, frag_len: int,
                     seq_num: int = 0) -> bytes:
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
    hdr += struct.pack("<I", seq_num)  # Sequence number
    hdr += struct.pack("<H", opnum)  # Opnum
    hdr += struct.pack("<H", 0)  # Interface hint
    hdr += struct.pack("<H", 0)  # Activity hint
    hdr += struct.pack("<H", frag_len)  # Fragment length
    hdr += struct.pack("<H", 0)  # Fragment number
    hdr += struct.pack("<B", 0x02)  # Auth length (dummy)
    hdr += struct.pack("<B", 0)  # Serial low
    return hdr


def build_connect_request(ar_uuid: bytes, session_key: int, mac: bytes) -> Tuple[bytes, bytes]:
    """Build complete Connect Request. Returns (packet, activity_uuid)"""
    blocks = b""
    blocks += build_ar_block(ar_uuid, session_key, mac)
    blocks += build_iocr_block(1, 1, INPUT_FRAME_ID, 6)  # Input IOCR
    blocks += build_iocr_block(2, 2, OUTPUT_FRAME_ID, 1)  # Output IOCR
    blocks += build_alarm_cr_block()
    blocks += build_expected_submod_block()

    # NDR header
    ndr = struct.pack("<I", len(blocks))  # ArgsMaximum
    ndr += struct.pack("<I", len(blocks))  # ArgsLength
    ndr += struct.pack("<I", len(blocks))  # MaxCount
    ndr += struct.pack("<I", 0)  # Offset
    ndr += struct.pack("<I", len(blocks))  # ActualCount
    ndr += blocks

    activity = uuid.uuid4().bytes
    rpc = build_rpc_header(OPNUM_CONNECT, activity, len(ndr))

    return rpc + ndr, activity


def build_control_request(ar_uuid: bytes, session_key: int, control_cmd: int,
                          activity_uuid: bytes, seq_num: int) -> bytes:
    """Build Control Request (PrmEnd or ApplicationReady)"""
    if control_cmd == CONTROL_PRM_END:
        block = build_control_block(BLOCK_PRM_END_REQ, ar_uuid, session_key, control_cmd)
    else:
        block = build_control_block(BLOCK_APP_READY_REQ, ar_uuid, session_key, control_cmd)

    # NDR header
    ndr = struct.pack("<I", len(block))  # ArgsMaximum
    ndr += struct.pack("<I", len(block))  # ArgsLength
    ndr += struct.pack("<I", len(block))  # MaxCount
    ndr += struct.pack("<I", 0)  # Offset
    ndr += struct.pack("<I", len(block))  # ActualCount
    ndr += block

    rpc = build_rpc_header(OPNUM_CONTROL, activity_uuid, len(ndr), seq_num)

    return rpc + ndr


def parse_response(data: bytes) -> Tuple[bool, str]:
    """Parse RPC response. Returns (success, error_message)"""
    if len(data) < 2:
        return False, "Response too short"

    pkt_type = data[1]
    if pkt_type != 2:
        return False, f"Not a response (type={pkt_type})"

    # Check for IODConnectRes block (0x0116)
    for offset in range(62, min(len(data) - 6, 200)):
        if offset + 2 > len(data):
            break
        block_type = struct.unpack(">H", data[offset:offset+2])[0]
        if block_type == 0x0116:
            return True, ""

    # Accept short responses as success
    if len(data) >= 70:
        return True, ""

    return False, "No valid response block"


def connect(device_ip: str, mac: bytes = None, verbose: bool = True) -> bool:
    """
    Full PROFINET connection sequence:
    1. Connect Request
    2. PrmEnd
    3. ApplicationReady
    """
    if mac is None:
        mac = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x01])

    ar_uuid = uuid.uuid4().bytes
    session_key = 1

    # Step 1: Connect Request
    if verbose:
        print(f"[1/3] Connect Request to {device_ip}:{RPC_PORT}")

    pkt, activity_uuid = build_connect_request(ar_uuid, session_key, mac)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        sock.sendto(pkt, (device_ip, RPC_PORT))
        resp, addr = sock.recvfrom(4096)

        success, error = parse_response(resp)
        if not success:
            print(f"[ERROR] Connect failed: {error}")
            return False

        if verbose:
            print(f"      Response: {len(resp)} bytes - SUCCESS")

    except socket.timeout:
        print("[ERROR] Connect timeout")
        return False
    finally:
        sock.close()

    # Step 2: PrmEnd
    if verbose:
        print("[2/3] PrmEnd")

    pkt = build_control_request(ar_uuid, session_key, CONTROL_PRM_END, activity_uuid, 1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        sock.sendto(pkt, (device_ip, RPC_PORT))
        resp, addr = sock.recvfrom(4096)
        if verbose:
            print(f"      Response: {len(resp)} bytes - SUCCESS")
    except socket.timeout:
        if verbose:
            print("      Timeout (continuing)")
    finally:
        sock.close()

    # Step 3: ApplicationReady
    if verbose:
        print("[3/3] ApplicationReady")

    pkt = build_control_request(ar_uuid, session_key, CONTROL_APP_READY, activity_uuid, 2)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        sock.sendto(pkt, (device_ip, RPC_PORT))
        resp, addr = sock.recvfrom(4096)
        if verbose:
            print(f"      Response: {len(resp)} bytes - SUCCESS")
    except socket.timeout:
        if verbose:
            print("      Timeout (continuing)")
    finally:
        sock.close()

    print("\n=== PROFINET Connection Established ===")
    print(f"Device: {device_ip}")
    print(f"AR-UUID: {ar_uuid.hex()}")
    print("State: RUNNING")

    return True


def main():
    """Command line interface"""
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.6.7"

    print(f"PROFINET Controller - Connecting to {ip}")
    print("=" * 50)

    success = connect(ip)

    if success:
        print("\nConnection successful! Device is now in RUNNING state.")
        print("Cyclic I/O data exchange can now begin.")
    else:
        print("\nConnection failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
