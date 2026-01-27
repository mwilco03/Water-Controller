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

# PROFINET Ethertype
PROFINET_ETHERTYPE = 0x8892

# DCP Multicast Address
DCP_MULTICAST_MAC = "01:0e:cf:00:00:00"

# DCP Service IDs
DCP_SERVICE_IDENTIFY = 0x05
DCP_SERVICE_TYPE_REQUEST = 0x00
DCP_SERVICE_TYPE_RESPONSE = 0x01

# RPC Operation Numbers
RPC_OPNUM_CONNECT = 0
RPC_OPNUM_RELEASE = 1
RPC_OPNUM_READ = 2
RPC_OPNUM_WRITE = 3
RPC_OPNUM_CONTROL = 4

# RPC Flags
RPC_FLAGS_IDEMPOTENT = 0x20

# RPC Header
RPC_HEADER_SIZE = 80
PNIO_STATUS_OFFSET = 80
PNIO_STATUS_SIZE = 4
PNIO_STATUS_OK = b"\x00\x00\x00\x00"

# AR Types
AR_TYPE_IOCAR = 0x0001

# IOCR Types
IOCR_TYPE_INPUT = 0x0001
IOCR_TYPE_OUTPUT = 0x0002

# IOCR Frame IDs
FRAME_ID_OUTPUT = 0x8000
FRAME_ID_INPUT = 0x8001

# IOCR Properties
IOCR_PROPERTIES_RT_CLASS_1 = 0x00000000
IOCR_TAG_HEADER = 0xC000
FRAME_SEND_OFFSET_ANY = 0xFFFFFFFF

# AlarmCR Types
ALARM_CR_TYPE_ALARM = 0x0001

# Control Commands
CONTROL_CMD_PRM_END = 0x0001
CONTROL_CMD_APP_READY = 0x0002
CONTROL_CMD_RELEASE = 0x0003

# Submodule Properties
SUBMOD_PROP_NO_IO = 0x0000
SUBMOD_PROP_INPUT = 0x0002
SUBMOD_PROP_OUTPUT = 0x0001

# Data Description Types
DATA_DESC_INPUT = 1
DATA_DESC_OUTPUT = 2

# RTU Module IDs
MOD_DAP = 0x00000001
SUBMOD_DAP = 0x00000001
MOD_TEMP = 0x00000040
SUBMOD_TEMP = 0x00000041

# Timeouts
RPC_TIMEOUT_S = 5.0
DCP_TIMEOUT_S = 3.0

# Buffer sizes
PNIO_ARGS_MAX = 16384
UDP_RECV_BUFFER = 4096
MAX_ALARM_DATA_LENGTH = 128


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

    def dcp_discover(self, station_name: str = "water-treat-rtu", timeout: float = DCP_TIMEOUT_S):
        """Discover device using DCP Identify"""
        print(f"[DCP] Discovering '{station_name}'...")

        # DCP Identify All
        dcp = Ether(dst=DCP_MULTICAST_MAC, src=self.mac, type=PROFINET_ETHERTYPE) / \
              ProfinetDCP(service_id=DCP_SERVICE_IDENTIFY, service_type=DCP_SERVICE_TYPE_REQUEST,
                         xid=0x1234, reserved=0, dcp_data_length=4) / \
              DCPNameOfStationBlock(option=2, sub_option=1)

        result = {}

        def handle_resp(pkt):
            if ProfinetDCP in pkt and pkt[ProfinetDCP].service_type == DCP_SERVICE_TYPE_RESPONSE:
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
            ARType=AR_TYPE_IOCAR,
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
            CMInitiatorUDPRTPort=PROFINET_ETHERTYPE,
            StationNameLength=10,
            CMInitiatorStationName=b"controller"
        )

        # Input IOCR - receive data from device
        iocr_input = IOCRBlockReq(
            IOCRType=IOCR_TYPE_INPUT,
            IOCRReference=0x0001,
            LT=PROFINET_ETHERTYPE,
            IOCRProperties=IOCR_PROPERTIES_RT_CLASS_1,
            DataLength=6,  # 5 bytes data + 1 IOPS
            FrameID=FRAME_ID_INPUT,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            Sequence=0,
            FrameSendOffset=FRAME_SEND_OFFSET_ANY,
            WatchdogFactor=10,
            DataHoldFactor=10,
            IOCRTagHeader=IOCR_TAG_HEADER,
            IOCRMulticastMACAdd=DCP_MULTICAST_MAC
        )

        # Output IOCR - send data to device
        iocr_output = IOCRBlockReq(
            IOCRType=IOCR_TYPE_OUTPUT,
            IOCRReference=0x0002,
            LT=PROFINET_ETHERTYPE,
            IOCRProperties=IOCR_PROPERTIES_RT_CLASS_1,
            DataLength=4,
            FrameID=FRAME_ID_OUTPUT,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            Sequence=0,
            FrameSendOffset=FRAME_SEND_OFFSET_ANY,
            WatchdogFactor=10,
            DataHoldFactor=10,
            IOCRTagHeader=IOCR_TAG_HEADER,
            IOCRMulticastMACAdd=DCP_MULTICAST_MAC
        )

        # Alarm CR
        alarm_cr = AlarmCRBlockReq(
            AlarmCRType=ALARM_CR_TYPE_ALARM,
            LT=PROFINET_ETHERTYPE,
            AlarmCRProperties=0x00000000,
            RTATimeoutFactor=100,
            RTARetries=3,
            LocalAlarmReference=0x0001,
            MaxAlarmDataLength=MAX_ALARM_DATA_LENGTH
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
                    'SubmoduleProperties': SUBMOD_PROP_NO_IO,
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
                    'SubmoduleProperties': SUBMOD_PROP_INPUT,
                    'DataDescription': [{
                        'DataDescription': DATA_DESC_INPUT,
                        'SubmoduleDataLength': 5,
                        'LengthIOCS': 1,
                        'LengthIOPS': 1
                    }]
                }]
            }]
        )

        # Assemble PNIO service request
        pnio = PNIOServiceReqPDU(
            args_max=PNIO_ARGS_MAX,
            blocks=[ar_block, iocr_input, iocr_output, alarm_cr, exp_submod]
        )

        # Wrap in DCE/RPC
        rpc = DceRpc4(
            type="request",
            flags1=RPC_FLAGS_IDEMPOTENT,
            opnum=RPC_OPNUM_CONNECT,
            if_id=PNIO_UUID,
            act_id=self.activity_uuid
        ) / pnio

        # Send via UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_S)

        try:
            pkt_bytes = bytes(rpc)
            print(f"[RPC] Sending {len(pkt_bytes)} bytes")
            sock.sendto(pkt_bytes, (device_ip, RPC_PORT))

            resp, addr = sock.recvfrom(UDP_RECV_BUFFER)
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
        min_response_len = PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE
        if len(data) < min_response_len:
            print("[RPC] Response too short")
            return False

        # PNIO Status at offset 80 (after RPC header)
        status = data[PNIO_STATUS_OFFSET:PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE]
        print(f"[RPC] PNIO Status: {status.hex()}")

        if status == PNIO_STATUS_OK:
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
            ControlCommand=CONTROL_CMD_PRM_END
        )

        pnio = PNIOServiceReqPDU(args_max=PNIO_ARGS_MAX, blocks=[ctrl])

        rpc = DceRpc4(
            type="request",
            flags1=RPC_FLAGS_IDEMPOTENT,
            opnum=RPC_OPNUM_CONTROL,
            if_id=PNIO_UUID,
            act_id=uuid4().bytes
        ) / pnio

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_S)

        try:
            sock.sendto(bytes(rpc), (self.device_ip, RPC_PORT))
            resp, _ = sock.recvfrom(UDP_RECV_BUFFER)
            min_len = PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE
            status = resp[PNIO_STATUS_OFFSET:PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE] if len(resp) >= min_len else b"\xff\xff\xff\xff"
            if status == PNIO_STATUS_OK:
                print("[RPC] PrmEnd SUCCESS!")
                return True
            print(f"[RPC] PrmEnd failed: {status.hex()}")
            return False
        except socket.timeout:
            print("[RPC] PrmEnd timeout")
            return False
        finally:
            sock.close()

    def application_ready(self) -> bool:
        """Send ApplicationReady to device"""
        if not self.connected:
            print("[RPC] Not connected")
            return False

        print("[RPC] Sending ApplicationReady...")

        ctrl = IODControlReq(
            ARUUID=self.ar_uuid,
            SessionKey=self.session_key,
            ControlCommand=CONTROL_CMD_APP_READY
        )

        pnio = PNIOServiceReqPDU(args_max=PNIO_ARGS_MAX, blocks=[ctrl])

        rpc = DceRpc4(
            type="request",
            flags1=RPC_FLAGS_IDEMPOTENT,
            opnum=RPC_OPNUM_CONTROL,
            if_id=PNIO_UUID,
            act_id=uuid4().bytes
        ) / pnio

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(RPC_TIMEOUT_S)

        try:
            sock.sendto(bytes(rpc), (self.device_ip, RPC_PORT))
            resp, _ = sock.recvfrom(UDP_RECV_BUFFER)
            min_len = PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE
            status = resp[PNIO_STATUS_OFFSET:PNIO_STATUS_OFFSET + PNIO_STATUS_SIZE] if len(resp) >= min_len else b"\xff\xff\xff\xff"
            if status == PNIO_STATUS_OK:
                print("[RPC] ApplicationReady SUCCESS!")
                return True
            print(f"[RPC] ApplicationReady failed: {status.hex()}")
            return False
        except socket.timeout:
            print("[RPC] ApplicationReady timeout")
            return False
        finally:
            sock.close()


def main():
    if not SCAPY_AVAILABLE:
        print("Running fallback mode without Scapy")
        return 1

    if len(sys.argv) < 3:
        print("Usage: python pn_scapy_controller.py <interface> <device_ip>")
        print("Get device IP from DCP discovery: POST /api/v1/discover/rtu")
        return 1
    iface = sys.argv[1]
    device_ip = sys.argv[2]

    ctrl = ProfinetController(interface=iface)

    # Discover device
    ctrl.dcp_discover()

    # Connect
    if ctrl.connect(device_ip):
        # Complete handshake: PrmEnd then ApplicationReady
        if ctrl.parameter_end():
            ctrl.application_ready()

    return 0


if __name__ == "__main__":
    sys.exit(main())
