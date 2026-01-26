#!/usr/bin/env python3
"""
PROFINET IO Controller using Scapy
Based on scapy.contrib.pnio_rpc documented examples
"""

import sys
import time
import struct
import socket
from uuid import uuid4

# Scapy imports - must be in container with working scapy
try:
    from scapy.all import conf, Ether, Raw, sendp, sniff, get_if_hwaddr
    from scapy.contrib.pnio import ProfinetIO
    from scapy.contrib.pnio_dcp import ProfinetDCP, DCPNameOfStationBlock
    from scapy.contrib.pnio_rpc import (
        Block, ARBlockReq, IOCRBlockReq, AlarmCRBlockReq,
        ExpectedSubmoduleBlockReq, IODControlReq,
        PNIOServiceReqPDU, PNIOServiceResPDU
    )
    from scapy.layers.dcerpc import DceRpc4
    SCAPY_AVAILABLE = True
except ImportError as e:
    print(f"Scapy import failed: {e}")
    print("Run in Docker container or fix IPv6 routing")
    SCAPY_AVAILABLE = False

# Constants
PNIO_UUID = "dea00001-6c97-11d1-8271-00a02442df7d"
RPC_PORT = 34964

# RTU Module IDs
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041


class ProfinetController:
    """PROFINET IO Controller using Scapy"""

    def __init__(self, interface: str = "eth0"):
        self.interface = interface
        self.mac = get_if_hwaddr(interface) if SCAPY_AVAILABLE else "02:00:00:00:00:01"
        self.ar_uuid = uuid4().bytes
        self.session_key = 1
        self.activity_uuid = uuid4().bytes

        # Connection state
        self.device_ip = None
        self.device_mac = None
        self.connected = False

    def dcp_discover(self, station_name: str = "water-treat-rtu", timeout: float = 3.0):
        """Discover device using DCP Identify"""
        print(f"[DCP] Discovering '{station_name}'...")

        # DCP Identify All
        dcp = Ether(dst="01:0e:cf:00:00:00", src=self.mac, type=0x8892) / \
              ProfinetDCP(service_id=5, service_type=0, xid=0x1234,
                         reserved=0, dcp_data_length=4) / \
              DCPNameOfStationBlock(option=2, sub_option=1)

        result = {}

        def handle_resp(pkt):
            if ProfinetDCP in pkt and pkt[ProfinetDCP].service_type == 1:
                result['mac'] = pkt.src
                # Parse IP from response blocks if available
                print(f"[DCP] Found device: {pkt.src}")
                return True
            return False

        sendp(dcp, iface=self.interface, verbose=False)
        sniff(iface=self.interface, timeout=timeout, store=False,
              stop_filter=handle_resp, filter="ether proto 0x8892")

        if result:
            self.device_mac = result.get('mac')
        return result

    def connect(self, device_ip: str) -> bool:
        """Establish PROFINET connection"""
        self.device_ip = device_ip
        print(f"[RPC] Connecting to {device_ip}...")

        # Build blocks using Scapy classes
        ar_block = ARBlockReq(
            ARType=0x0001,  # IOCAR
            ARUUID=self.ar_uuid,
            SessionKey=self.session_key,
            CMInitiatorMacAdd=self.mac.replace(":", ""),
            CMInitiatorObjectUUID=uuid4().bytes,
            ARProperties_ParameterizationServer=0,
            ARProperties_DeviceAccess=0,
            ARProperties_CompanionAR=0,
            ARProperties_AcknowledgeCompanionAR=0,
            ARProperties_Reserved1=0,
            ARProperties_CMInitiator=1,
            ARProperties_SupervisorTakeoverAllowed=0,
            ARProperties_State=1,
            CMInitiatorActivityTimeoutFactor=1000,
            CMInitiatorUDPRTPort=0x8892,
            StationNameLength=10,
            CMInitiatorStationName=b"controller"
        )

        # Input IOCR - receive data from device
        iocr_input = IOCRBlockReq(
            IOCRType=0x0001,
            IOCRReference=0x0001,
            LT=0x8892,
            IOCRProperties=0x00000000,
            DataLength=6,  # 5 bytes data + 1 IOPS
            FrameID=0x8001,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            Sequence=0,
            FrameSendOffset=0xFFFFFFFF,
            WatchdogFactor=10,
            DataHoldFactor=10,
            IOCRTagHeader=0xC000,
            IOCRMulticastMACAdd="01:0e:cf:00:00:00"
        )

        # Output IOCR - send data to device
        iocr_output = IOCRBlockReq(
            IOCRType=0x0002,
            IOCRReference=0x0002,
            LT=0x8892,
            IOCRProperties=0x00000000,
            DataLength=4,
            FrameID=0x8000,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            Sequence=0,
            FrameSendOffset=0xFFFFFFFF,
            WatchdogFactor=10,
            DataHoldFactor=10,
            IOCRTagHeader=0xC000,
            IOCRMulticastMACAdd="01:0e:cf:00:00:00"
        )

        # Alarm CR
        alarm_cr = AlarmCRBlockReq(
            AlarmCRType=0x0001,
            LT=0x8892,
            AlarmCRProperties=0x00000000,
            RTATimeoutFactor=100,
            RTARetries=3,
            LocalAlarmReference=0x0001,
            MaxAlarmDataLength=128  # Not 200!
        )

        # Expected Submodules - DAP + CPU Temp
        exp_submod = ExpectedSubmoduleBlockReq(
            NumberOfAPIs=1,
            APIs=[{
                'API': 0,
                'SlotNumber': 0,
                'ModuleIdentNumber': MOD_DAP,
                'ModuleProperties': 0,
                'Submodules': [{
                    'SubslotNumber': 1,
                    'SubmoduleIdentNumber': SUBMOD_DAP,
                    'SubmoduleProperties': 0,
                    'DataDescription': []
                }]
            }, {
                'API': 0,
                'SlotNumber': 1,
                'ModuleIdentNumber': MOD_TEMP,
                'ModuleProperties': 0,
                'Submodules': [{
                    'SubslotNumber': 1,
                    'SubmoduleIdentNumber': SUBMOD_TEMP,
                    'SubmoduleProperties': 0x0002,  # Input
                    'DataDescription': [{
                        'DataDescription': 1,  # Input
                        'SubmoduleDataLength': 5,
                        'LengthIOCS': 1,
                        'LengthIOPS': 1
                    }]
                }]
            }]
        )

        # Assemble PNIO service request
        pnio = PNIOServiceReqPDU(
            args_max=16384,
            blocks=[ar_block, iocr_input, iocr_output, alarm_cr, exp_submod]
        )

        # Wrap in DCE/RPC
        rpc = DceRpc4(
            type="request",
            flags1=0x20,
            opnum=0,  # Connect
            if_id=PNIO_UUID,
            act_id=self.activity_uuid
        ) / pnio

        # Send via UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            pkt_bytes = bytes(rpc)
            print(f"[RPC] Sending {len(pkt_bytes)} bytes")
            sock.sendto(pkt_bytes, (device_ip, RPC_PORT))

            resp, addr = sock.recvfrom(4096)
            print(f"[RPC] Response: {len(resp)} bytes from {addr}")

            # Parse response
            return self._parse_connect_response(resp)

        except socket.timeout:
            print("[RPC] Timeout waiting for response")
            return False
        finally:
            sock.close()

    def _parse_connect_response(self, data: bytes) -> bool:
        """Parse Connect Response"""
        if len(data) < 84:
            print("[RPC] Response too short")
            return False

        # PNIO Status at offset 80 (after RPC header)
        status = data[80:84]
        print(f"[RPC] PNIO Status: {status.hex()}")

        if status == b"\x00\x00\x00\x00":
            print("[RPC] Connect SUCCESS!")
            self.connected = True
            return True
        else:
            code, decode, code1, code2 = status
            blocks = {1: "ARBlock", 2: "IOCRBlock", 3: "AlarmCRBlock", 4: "ExpectedSubmod"}
            print(f"[RPC] Error in {blocks.get(code1, 'Unknown')}: decode=0x{decode:02x} err=0x{code2:02x}")
            return False

    def parameter_end(self) -> bool:
        """Send PrmEnd to device"""
        if not self.connected:
            print("[RPC] Not connected")
            return False

        print("[RPC] Sending ParameterEnd...")

        ctrl = IODControlReq(
            ARUUID=self.ar_uuid,
            SessionKey=self.session_key,
            ControlCommand=0x0001  # PrmEnd
        )

        pnio = PNIOServiceReqPDU(args_max=16384, blocks=[ctrl])

        rpc = DceRpc4(
            type="request",
            flags1=0x20,
            opnum=4,  # Control (NOT 2 - that's Read!)
            if_id=PNIO_UUID,
            act_id=uuid4().bytes
        ) / pnio

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)

        try:
            sock.sendto(bytes(rpc), (self.device_ip, RPC_PORT))
            resp, _ = sock.recvfrom(4096)
            status = resp[80:84] if len(resp) >= 84 else b"\xff\xff\xff\xff"
            if status == b"\x00\x00\x00\x00":
                print("[RPC] PrmEnd SUCCESS!")
                return True
            print(f"[RPC] PrmEnd failed: {status.hex()}")
            return False
        except socket.timeout:
            print("[RPC] PrmEnd timeout")
            return False
        finally:
            sock.close()

    def wait_for_app_ready(self, timeout: float = 30.0) -> bool:
        """
        Wait for ApplicationReady request from device and send response.

        After PrmEnd, the DEVICE sends ApplicationReady to the controller.
        The controller must receive it and respond with ApplicationReady Response.
        This is the correct PROFINET handshake sequence.
        """
        if not self.connected:
            print("[RPC] Not connected")
            return False

        print("[RPC] Waiting for ApplicationReady from device...")

        # Open UDP socket to receive incoming RPC request from device
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        try:
            # Bind to RPC port to receive incoming requests
            sock.bind(("0.0.0.0", RPC_PORT))

            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    print(f"[RPC] Received {len(data)} bytes from {addr}")

                    # Check if this is an RPC request with Control opnum
                    if len(data) < 24:
                        continue

                    # Check RPC type (byte 2) - 0x00 = request
                    rpc_type = data[2]
                    if rpc_type != 0x00:
                        continue

                    # Check opnum (bytes 22-23, little-endian) - 4 = Control
                    opnum = struct.unpack("<H", data[22:24])[0]
                    if opnum != 4:
                        continue

                    # This looks like a Control request - check for ApplicationReady
                    # IODControlReq block starts after RPC header + PNIO header
                    # Look for ControlCommand = 0x0002 (ApplicationReady)
                    print("[RPC] Received Control request - parsing for ApplicationReady...")

                    # Send ApplicationReady Response
                    if self._send_app_ready_response(sock, addr, data):
                        print("[RPC] ApplicationReady handshake SUCCESS!")
                        return True

                except socket.timeout:
                    continue

            print("[RPC] Timeout waiting for ApplicationReady from device")
            return False

        except OSError as e:
            print(f"[RPC] Socket error: {e}")
            return False
        finally:
            sock.close()

    def _send_app_ready_response(self, sock: socket.socket, addr: tuple, request_data: bytes) -> bool:
        """
        Send ApplicationReady response to device.

        Build an RPC response with IODControlRes block (0x8110).
        """
        print(f"[RPC] Sending ApplicationReady response to {addr}...")

        # Extract activity UUID from request (bytes 40-56)
        if len(request_data) < 56:
            print("[RPC] Request too short to extract activity UUID")
            return False

        activity_uuid = request_data[40:56]

        # Build RPC Response header
        # DCE/RPC Response with PNIO status = OK
        rpc_response = bytearray()

        # RPC header (80 bytes)
        rpc_response.extend([
            0x04,  # Version
            0x00,  # Version minor
            0x02,  # Type = response
            0x20,  # Flags1
            0x00, 0x00, 0x00, 0x00,  # Data representation (little-endian)
            0x00, 0x00,  # Serial high
            # Object UUID (16 bytes) - copy from request
        ])
        rpc_response.extend(request_data[8:24])  # Object UUID
        # Interface UUID (16 bytes)
        rpc_response.extend(bytes.fromhex("dea000016c9711d1827100a02442df7d"))
        # Activity UUID (16 bytes) - from request
        rpc_response.extend(activity_uuid)
        # Server boot time, interface version, sequence, opnum, interface hint, activity hint
        rpc_response.extend([
            0x00, 0x00, 0x00, 0x00,  # Server boot time
            0x00, 0x00, 0x00, 0x01,  # Interface version
            0x00, 0x00, 0x00, 0x00,  # Sequence
            0x04, 0x00,  # Opnum = 4 (Control)
            0xFF, 0xFF,  # Interface hint
            0xFF, 0xFF,  # Activity hint
            0x00, 0x00,  # Fragment length (fill later)
            0x00, 0x00,  # Fragment number
            0x03,  # Flags (no frag, last frag)
            0x00,  # Serial low
        ])

        # PNIO response body
        # Status = OK (0x00000000)
        # args_max, args_length, max_count, offset, actual_count
        pnio_body = bytearray()
        pnio_body.extend([
            0x00, 0x00, 0x00, 0x00,  # PNIO Status = OK
            0x00, 0x00, 0x40, 0x00,  # args_max = 16384
            0x00, 0x00, 0x00, 0x28,  # args_length = 40
            0x00, 0x00, 0x40, 0x00,  # max_count
            0x00, 0x00, 0x00, 0x00,  # offset
            0x00, 0x00, 0x00, 0x28,  # actual_count = 40
        ])

        # IODControlRes block (0x8110) for ApplicationReady
        # Block type = 0x8110, length = 28
        iod_control_res = bytearray([
            0x81, 0x10,  # Block type (IODControlRes)
            0x00, 0x1C,  # Block length = 28
            0x01, 0x00,  # Version 1.0
        ])
        # AR UUID
        iod_control_res.extend(self.ar_uuid)
        # Session key
        iod_control_res.extend(struct.pack(">H", self.session_key))
        # Alarm sequence (2 bytes)
        iod_control_res.extend([0x00, 0x00])
        # Control command (2 bytes) - 0x0002 = ApplicationReady
        iod_control_res.extend([0x00, 0x02])
        # Control block properties (2 bytes)
        iod_control_res.extend([0x00, 0x00])

        pnio_body.extend(iod_control_res)

        # Update fragment length in RPC header
        frag_len = len(pnio_body)
        rpc_response[74] = frag_len & 0xFF
        rpc_response[75] = (frag_len >> 8) & 0xFF

        # Combine RPC header and PNIO body
        full_response = bytes(rpc_response) + bytes(pnio_body)

        try:
            sock.sendto(full_response, addr)
            print(f"[RPC] Sent {len(full_response)} byte ApplicationReady response")
            return True
        except OSError as e:
            print(f"[RPC] Failed to send response: {e}")
            return False


def main():
    if not SCAPY_AVAILABLE:
        print("Running fallback mode without Scapy")
        return 1

    iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
    device_ip = sys.argv[2] if len(sys.argv) > 2 else "192.168.6.7"

    ctrl = ProfinetController(interface=iface)

    # Discover device
    ctrl.dcp_discover()

    # Connect
    if ctrl.connect(device_ip):
        # Complete handshake: PrmEnd then wait for ApplicationReady from device
        if ctrl.parameter_end():
            # Device sends ApplicationReady to us, we respond
            ctrl.wait_for_app_ready(timeout=30.0)

    return 0


if __name__ == "__main__":
    sys.exit(main())
