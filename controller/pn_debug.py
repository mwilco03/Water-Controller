#!/usr/bin/env python3
"""
PROFINET Debug Tool - Validate protocol against RTU
Use to debug C implementation issues
"""

import struct
import socket
import uuid
import sys

RPC_PORT = 34964

# PROFINET UUIDs (little-endian for DCE/RPC)
PNIO_IF_UUID = bytes([
    0x01, 0x00, 0xa0, 0xde, 0x97, 0x6c, 0xd1, 0x11,
    0x82, 0x71, 0x00, 0xa0, 0x24, 0x42, 0xdf, 0x7d
])

class PNIOBlock:
    """PNIO Block builder with hex dump"""

    @staticmethod
    def header(block_type: int, content_len: int) -> bytes:
        # BlockLength = version(2) + content
        block_len = content_len + 2
        return struct.pack(">HHbb", block_type, block_len, 1, 0)

    @staticmethod
    def ar_block(ar_uuid: bytes, session_key: int, mac: bytes, station: bytes) -> bytes:
        content = b""
        content += struct.pack(">H", 0x0001)  # ARType: IOCAR
        content += ar_uuid
        content += struct.pack(">H", session_key)
        content += mac
        content += struct.pack(">H", 0x0001)  # CMInitiatorObjectUUIDVersion
        content += PNIO_IF_UUID  # CMInitiatorActivityUUID
        content += uuid.uuid4().bytes  # CMInitiatorObjectUUID
        content += struct.pack(">I", 0x00000001)  # ARProperties: Supervisor
        content += struct.pack(">H", 100)  # CMInitiatorTimeout
        content += struct.pack(">H", len(station))
        content += station
        return PNIOBlock.header(0x0101, len(content)) + content

    @staticmethod
    def iocr_block(iocr_type: int, ref: int, frame_id: int,
                   data_len: int, api_data: bytes = b"") -> bytes:
        content = b""
        content += struct.pack(">H", iocr_type)
        content += struct.pack(">H", ref)
        content += struct.pack(">H", 0x8892)  # LT
        content += struct.pack(">I", 0x00000000)  # Properties RT_CLASS_1
        content += struct.pack(">H", data_len)
        content += struct.pack(">H", frame_id)
        content += struct.pack(">H", 32)  # SendClockFactor
        content += struct.pack(">H", 32)  # ReductionRatio
        content += struct.pack(">H", 1)   # Phase
        content += struct.pack(">I", 0xFFFFFFFF)  # FrameSendOffset
        content += struct.pack(">H", 10)  # WatchdogFactor
        content += struct.pack(">H", 10)  # DataHoldFactor
        content += struct.pack(">H", 0xC000)  # IOCRTagHeader (prio 6)
        content += b"\x00" * 6  # CMInitiatorMACAdd
        content += struct.pack(">H", 0)  # NumberOfAPIs
        content += api_data
        return PNIOBlock.header(0x0102, len(content)) + content

    @staticmethod
    def alarm_cr_block(with_tags: bool = True) -> bytes:
        """AlarmCRBlockReq - with or without tag headers"""
        content = b""
        content += struct.pack(">H", 0x0001)  # AlarmCRType
        content += struct.pack(">H", 0x8892)  # LT
        content += struct.pack(">I", 0x00000000)  # Properties
        content += struct.pack(">H", 100)  # RTATimeoutFactor
        content += struct.pack(">H", 3)    # RTARetries
        content += struct.pack(">H", 0x0001)  # LocalAlarmReference
        content += struct.pack(">H", 200)  # MaxAlarmDataLength
        if with_tags:
            content += struct.pack(">H", 0xC000)  # TagHeaderHigh
            content += struct.pack(">H", 0xA000)  # TagHeaderLow
        return PNIOBlock.header(0x0103, len(content)) + content

    @staticmethod
    def expected_submod_block() -> bytes:
        """2-slot config: DAP + CPU Temp"""
        content = b""
        content += struct.pack(">H", 1)  # NumberOfAPIs
        content += struct.pack(">I", 0)  # API
        content += struct.pack(">H", 2)  # NumberOfSlots

        # Slot 0: DAP
        content += struct.pack(">H", 0)  # SlotNumber
        content += struct.pack(">I", 0x00000001)  # ModuleIdentNumber
        content += struct.pack(">H", 0)  # ModuleProperties
        content += struct.pack(">H", 1)  # NumberOfSubmodules
        content += struct.pack(">H", 1)  # SubslotNumber
        content += struct.pack(">I", 0x00000001)  # SubmoduleIdentNumber
        content += struct.pack(">H", 0)  # SubmoduleProperties
        content += struct.pack(">H", 0)  # DataDescriptionCount

        # Slot 1: CPU Temp
        content += struct.pack(">H", 1)  # SlotNumber
        content += struct.pack(">I", 0x00000040)  # ModuleIdentNumber
        content += struct.pack(">H", 0)  # ModuleProperties
        content += struct.pack(">H", 1)  # NumberOfSubmodules
        content += struct.pack(">H", 1)  # SubslotNumber
        content += struct.pack(">I", 0x00000041)  # SubmoduleIdentNumber
        content += struct.pack(">H", 0x0002)  # SubmoduleProperties: INPUT
        content += struct.pack(">H", 1)  # DataDescriptionCount
        # DataDescription
        content += struct.pack(">H", 0x0001)  # Type: Input
        content += struct.pack(">H", 5)  # SubmoduleDataLength (Float32 + Quality)
        content += struct.pack(">B", 1)  # LengthIOCS
        content += struct.pack(">B", 1)  # LengthIOPS

        return PNIOBlock.header(0x0104, len(content)) + content


def build_rpc_request(opnum: int, payload: bytes) -> bytes:
    """Build DCE/RPC request"""
    activity = uuid.uuid4().bytes

    hdr = b""
    hdr += struct.pack("<B", 4)  # Version
    hdr += struct.pack("<B", 0)  # Type: Request
    hdr += struct.pack("<BB", 0x20, 0x00)  # Flags
    hdr += struct.pack("<BBbb", 0x10, 0, 0, 0)  # DataRep
    hdr += struct.pack("<H", 0)  # SerialHigh
    hdr += PNIO_IF_UUID
    hdr += activity
    hdr += struct.pack("<I", 0)  # ServerBootTime
    hdr += struct.pack("<I", 1)  # InterfaceVersion
    hdr += struct.pack("<I", 0)  # SequenceNumber
    hdr += struct.pack("<H", opnum)
    hdr += struct.pack("<HH", 0xFFFF, 0xFFFF)  # InterfaceHint, ActivityHint
    hdr += struct.pack("<H", len(payload))  # FragmentLength
    hdr += struct.pack("<H", 0)  # FragmentNumber
    hdr += struct.pack("<BB", 0, 0)  # AuthLength, SerialLow

    return hdr + payload


def build_connect(with_alarm_tags: bool = True) -> bytes:
    """Build complete Connect Request"""
    ar_uuid = uuid.uuid4().bytes
    mac = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x01])
    station = b"controller"

    blocks = b""
    blocks += PNIOBlock.ar_block(ar_uuid, 1, mac, station)
    blocks += PNIOBlock.iocr_block(1, 1, 0x8001, 6)  # Input
    blocks += PNIOBlock.iocr_block(2, 2, 0x8000, 4)  # Output
    blocks += PNIOBlock.alarm_cr_block(with_tags)
    blocks += PNIOBlock.expected_submod_block()

    # NDR wrapper
    ndr = struct.pack("<IIIII",
        len(blocks),  # ArgsMaximum
        len(blocks),  # ArgsLength
        len(blocks),  # MaxCount
        0,            # Offset
        len(blocks))  # ActualCount
    ndr += blocks

    return build_rpc_request(0, ndr), ar_uuid


def hexdump(data: bytes, prefix: str = "") -> None:
    """Print hex dump"""
    for i in range(0, len(data), 16):
        hex_part = " ".join(f"{b:02x}" for b in data[i:i+16])
        print(f"{prefix}{i:04x}: {hex_part}")


def parse_error(status: bytes) -> str:
    """Parse PNIO Status error"""
    code, decode, code1, code2 = status

    blocks = {0x01: "ARBlock", 0x02: "IOCRBlock", 0x03: "AlarmCRBlock",
              0x04: "ExpectedSubmod", 0x05: "PrmServer"}

    errors = {
        (0x03, 0x00): "Invalid AlarmCR type",
        (0x03, 0x01): "Invalid block length",
        (0x03, 0x02): "Invalid LT",
        (0x04, 0x00): "Invalid API",
        (0x04, 0x01): "Invalid slot",
        (0x04, 0x02): "Invalid subslot",
        (0x04, 0x03): "Invalid module",
        (0x04, 0x04): "Invalid submodule",
    }

    block = blocks.get(code1, f"Block-0x{code1:02x}")
    err = errors.get((code1, code2), f"Error-0x{code2:02x}")

    return f"{block}: {err}"


def test_connect(ip: str, with_alarm_tags: bool = True):
    """Test Connect Request"""
    print(f"\n{'='*60}")
    print(f"Testing Connect to {ip}")
    print(f"AlarmCR tag headers: {'YES (BlockLength=22)' if with_alarm_tags else 'NO (BlockLength=18)'}")
    print(f"{'='*60}\n")

    pkt, ar_uuid = build_connect(with_alarm_tags)

    print(f"Request size: {len(pkt)} bytes")
    print(f"AR UUID: {ar_uuid.hex()}")

    # Find AlarmCR block and show its length
    # Block header: type(2) + length(2) + version(2)
    data = pkt[80:]  # Skip RPC header + NDR header
    pos = 0
    while pos < len(data) - 4:
        btype = struct.unpack(">H", data[pos:pos+2])[0]
        blen = struct.unpack(">H", data[pos+2:pos+4])[0]
        if btype == 0x0103:
            print(f"\nAlarmCRBlockReq at offset {pos}:")
            print(f"  BlockType: 0x{btype:04x}")
            print(f"  BlockLength: {blen} (expected: {'22' if with_alarm_tags else '18'})")
            hexdump(data[pos:pos+6+blen-2], "  ")
            break
        pos += 6 + blen - 2
        # Align to 4
        pos = (pos + 3) & ~3

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        sock.sendto(pkt, (ip, RPC_PORT))
        resp, addr = sock.recvfrom(4096)

        print(f"\nResponse: {len(resp)} bytes from {addr}")

        # RPC header is 80 bytes, then NDR, then PNIO Status
        if len(resp) >= 84:
            status = resp[80:84]
            print(f"PNIO Status: {status.hex()}")

            if status == b"\x00\x00\x00\x00":
                print("\n*** SUCCESS! ***")
                return True
            else:
                print(f"\n*** ERROR: {parse_error(status)} ***")
                print("\nFull response:")
                hexdump(resp)
        return False

    except socket.timeout:
        print("\n*** TIMEOUT ***")
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.6.7"

    # Test with tag headers first (BlockLength=22)
    if not test_connect(ip, with_alarm_tags=True):
        print("\n\nRetrying WITHOUT tag headers...")
        test_connect(ip, with_alarm_tags=False)
