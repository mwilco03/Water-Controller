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
            opnum=2,  # Control
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
        # Send PrmEnd
        ctrl.parameter_end()

    return 0


if __name__ == "__main__":
    sys.exit(main())
