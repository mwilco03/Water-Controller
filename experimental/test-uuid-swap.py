#!/usr/bin/env python3
"""
Test PROFINET RPC Header UUID Swap Logic

This script verifies that the UUID swap logic in the Water Controller
produces the correct byte order for PROFINET DCE/RPC packets.

Expected behavior:
- PNIO_DEVICE_INTERFACE_UUID constant is in big-endian: DE A0 00 01 6C 97...
- After uuid_swap_fields(), first 8 bytes become:     01 00 A0 DE 97 6C D1 11
- p-net validates this against its internal constant: {0xDEA00001, 0x6C97, 0x11D1, ...}

Based on PCAP analysis showing Interface UUID corruption as root cause of RPC timeouts.
"""

import struct
import sys

def uuid_swap_fields(uuid_bytes):
    """
    Python implementation of uuid_swap_fields() from rpc_strategy.c

    Swaps first 3 fields of UUID from BE to LE (or LE to BE):
    - time_low (4 bytes): reverse
    - time_mid (2 bytes): reverse
    - time_hi_and_version (2 bytes): reverse
    - clock_seq + node (8 bytes): unchanged
    """
    uuid = bytearray(uuid_bytes)

    # time_low (bytes 0-3): reverse 4 bytes
    uuid[0], uuid[3] = uuid[3], uuid[0]
    uuid[1], uuid[2] = uuid[2], uuid[1]

    # time_mid (bytes 4-5): reverse 2 bytes
    uuid[4], uuid[5] = uuid[5], uuid[4]

    # time_hi_and_version (bytes 6-7): reverse 2 bytes
    uuid[6], uuid[7] = uuid[7], uuid[6]

    # clock_seq + node (bytes 8-15): unchanged

    return bytes(uuid)

def test_pnio_interface_uuid():
    """Test PROFINET IO Device Interface UUID swap"""

    # From src/profinet/profinet_rpc.c:44-47
    PNIO_DEVICE_INTERFACE_UUID = bytes([
        0xDE, 0xA0, 0x00, 0x01, 0x6C, 0x97, 0x11, 0xD1,
        0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
    ])

    # Expected result after swap (LE wire format per DREP=0x10)
    EXPECTED_AFTER_SWAP = bytes([
        0x01, 0x00, 0xA0, 0xDE, 0x97, 0x6C, 0xD1, 0x11,
        0x82, 0x71, 0x00, 0xA0, 0x24, 0x42, 0xDF, 0x7D
    ])

    # What p-net expects to decode (host byte order values)
    # From p-net source: pf_uuid_t constant = {0xDEA00001, 0x6C97, 0x11D1, ...}
    PNET_EXPECTED = {
        'time_low': 0xDEA00001,
        'time_mid': 0x6C97,
        'time_hi_and_version': 0x11D1,
    }

    print("=" * 70)
    print("PROFINET Interface UUID Swap Test")
    print("=" * 70)

    print("\n1. Original UUID (big-endian storage):")
    print(f"   {PNIO_DEVICE_INTERFACE_UUID.hex(' ')}")
    print(f"   {PNIO_DEVICE_INTERFACE_UUID[:4].hex()} = time_low (BE)")
    print(f"   {PNIO_DEVICE_INTERFACE_UUID[4:6].hex()} = time_mid (BE)")
    print(f"   {PNIO_DEVICE_INTERFACE_UUID[6:8].hex()} = time_hi_and_version (BE)")

    # Perform swap
    swapped = uuid_swap_fields(PNIO_DEVICE_INTERFACE_UUID)

    print("\n2. After uuid_swap_fields() (little-endian wire format):")
    print(f"   {swapped.hex(' ')}")
    print(f"   {swapped[:4].hex()} = time_low (LE)")
    print(f"   {swapped[4:6].hex()} = time_mid (LE)")
    print(f"   {swapped[6:8].hex()} = time_hi_and_version (LE)")

    print("\n3. What p-net decodes (using pf_get_uuid with DREP=0x10):")
    # Decode as LE
    time_low_decoded = struct.unpack('<I', swapped[:4])[0]
    time_mid_decoded = struct.unpack('<H', swapped[4:6])[0]
    time_hi_decoded = struct.unpack('<H', swapped[6:8])[0]

    print(f"   time_low = 0x{time_low_decoded:08X} (expected: 0x{PNET_EXPECTED['time_low']:08X})")
    print(f"   time_mid = 0x{time_mid_decoded:04X} (expected: 0x{PNET_EXPECTED['time_mid']:04X})")
    print(f"   time_hi  = 0x{time_hi_decoded:04X} (expected: 0x{PNET_EXPECTED['time_hi_and_version']:04X})")

    print("\n4. Validation:")
    if swapped == EXPECTED_AFTER_SWAP:
        print("   ✅ Wire format matches expected")
    else:
        print("   ❌ Wire format MISMATCH!")
        print(f"   Expected: {EXPECTED_AFTER_SWAP.hex(' ')}")
        print(f"   Got:      {swapped.hex(' ')}")
        return False

    if (time_low_decoded == PNET_EXPECTED['time_low'] and
        time_mid_decoded == PNET_EXPECTED['time_mid'] and
        time_hi_decoded == PNET_EXPECTED['time_hi_and_version']):
        print("   ✅ Decoded values match p-net expectations")
    else:
        print("   ❌ Decoded values MISMATCH p-net expectations!")
        return False

    # Compare against PCAP
    print("\n5. PCAP Analysis (df93bc5.pcapng packet #13, offset 24-39):")
    PCAP_INTERFACE_UUID = bytes.fromhex('df7d1279e8b001ec4f59a6036aa32393')
    print(f"   Actual in packet: {PCAP_INTERFACE_UUID.hex(' ')}")
    print(f"   Expected:         {EXPECTED_AFTER_SWAP.hex(' ')}")

    if PCAP_INTERFACE_UUID == EXPECTED_AFTER_SWAP:
        print("   ✅ PCAP matches expected (packet is correct)")
    else:
        print("   ❌ PCAP MISMATCH - THIS IS THE BUG!")
        print("   This explains why p-net rejects the packet!")

    return True

def test_struct_size():
    """Verify RPC header struct size"""
    print("\n" + "=" * 70)
    print("RPC Header Structure Size Test")
    print("=" * 70)

    # From profinet_frame.h:84-104
    fields = [
        ('version', 1),
        ('packet_type', 1),
        ('flags1', 1),
        ('flags2', 1),
        ('drep', 3),
        ('serial_high', 1),
        ('object_uuid', 16),
        ('interface_uuid', 16),
        ('activity_uuid', 16),
        ('server_boot', 4),
        ('interface_version', 4),
        ('sequence_number', 4),
        ('opnum', 2),
        ('interface_hint', 2),
        ('activity_hint', 2),
        ('fragment_length', 2),
        ('fragment_number', 2),
        ('auth_protocol', 1),
        ('serial_low', 1),
    ]

    total_size = sum(size for _, size in fields)

    print("\nField breakdown:")
    offset = 0
    for name, size in fields:
        print(f"  {offset:2d}-{offset+size-1:2d} ({size:2d} bytes): {name}")
        offset += size

    print(f"\nTotal size: {total_size} bytes")

    if total_size == 80:
        print("✅ Struct size is correct (80 bytes)")
        return True
    else:
        print(f"❌ Struct size WRONG! Expected 80, got {total_size}")
        return False

def main():
    print("\nPROFINET RPC Header Validation Test")
    print("Based on PCAP analysis from df93bc5.pcapng")
    print("=" * 70)

    all_pass = True

    # Test UUID swap
    if not test_pnio_interface_uuid():
        all_pass = False

    # Test struct size
    if not test_struct_size():
        all_pass = False

    print("\n" + "=" * 70)
    if all_pass:
        print("✅ All logic tests PASS - code is correct!")
        print("\nHowever, PCAP shows Interface UUID is corrupted in actual packet.")
        print("Possible causes:")
        print("  1. Compiler struct padding despite __attribute__((packed))")
        print("  2. Memory corruption during packet construction")
        print("  3. Buffer pointer arithmetic error")
        print("  4. uuid_swap_fields() not being called")
        return 0
    else:
        print("❌ Logic tests FAILED - UUID swap implementation has bugs!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
