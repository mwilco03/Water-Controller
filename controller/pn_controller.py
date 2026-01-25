#!/usr/bin/env python3
"""
PROFINET IO Controller using Scapy
Connects to p-net RTU devices
"""

import uuid
import struct
import socket
import time
from typing import Optional, Tuple

from scapy.all import conf, get_if_hwaddr, sendp, sniff, Ether
from scapy.contrib.pnio_dcp import ProfinetDCP, DCPIdentifyBlock
from scapy.contrib.pnio_rpc import (
    PNIOServiceReqPDU, PNIOServiceResPDU,
    ARBlockReq, IOCRBlockReq, AlarmCRBlockReq,
    ExpectedSubmoduleBlockReq, ExpectedSubmoduleDataDescription,
    IODControlReq, Block
)
from scapy.contrib.dce_rpc import DceRpc4

# PROFINET constants
PNIO_INTERFACE_UUID = "dea00001-6c97-11d1-8271-00a02442df7d"
PNIO_OBJECT_UUID = "dea00000-6c97-11d1-8271-00a02442df7d"
RPC_PORT = 34964

# Module IDs for RTU
GSDML_MOD_DAP = 0x00000001
GSDML_SUBMOD_DAP = 0x00000001
GSDML_MOD_TEMPERATURE = 0x00000040
GSDML_SUBMOD_TEMPERATURE = 0x00000041


class PNController:
    """PROFINET IO Controller"""

    def __init__(self, interface: str = "eth0"):
        self.interface = interface
        self.mac = get_if_hwaddr(interface)
        self.ar_uuid = uuid.uuid4().bytes
        self.session_key = 1
        self.device_ip: Optional[str] = None
        self.device_mac: Optional[str] = None

    def discover(self, station_name: str = "water-treat-rtu", timeout: float = 5.0) -> Optional[dict]:
        """DCP Identify to find device"""
        print(f"[DCP] Discovering {station_name}...")

        # Build DCP Identify request
        dcp = Ether(dst="01:0e:cf:00:00:00", src=self.mac, type=0x8892) / \
              ProfinetDCP(service_id=0x05, service_type=0x00, xid=0x1234) / \
              DCPIdentifyBlock(option=0x02, sub_option=0x02)  # NameOfStation

        result = None

        def handle_response(pkt):
            nonlocal result
            if ProfinetDCP in pkt and pkt[ProfinetDCP].service_type == 0x01:
                # Parse response
                result = {
                    "mac": pkt.src,
                    "ip": None,  # Extract from DCP blocks
                    "station_name": station_name
                }
                return True
            return False

        sendp(dcp, iface=self.interface, verbose=False)
        sniff(iface=self.interface, timeout=timeout, store=False,
              stop_filter=handle_response, filter="ether proto 0x8892")

        if result:
            self.device_mac = result["mac"]
            print(f"[DCP] Found device: MAC={result['mac']}")
        return result

    def connect(self, device_ip: str) -> bool:
        """RPC Connect to device"""
        self.device_ip = device_ip
        print(f"[RPC] Connecting to {device_ip}...")

        # Build Connect Request blocks
        ar_block = ARBlockReq(
            ARType=0x0001,  # IOCAR
            ARUUID=self.ar_uuid,
            SessionKey=self.session_key,
            CMInitiatorMac=bytes.fromhex(self.mac.replace(":", "")),
            CMInitiatorObjectUUID=uuid.UUID(PNIO_OBJECT_UUID).bytes,
            StationNameLength=len("controller"),
            CMInitiatorStationName=b"controller"
        )

        # Input IOCR (receive from device)
        iocr_input = IOCRBlockReq(
            IOCRType=0x0001,  # Input
            IOCRReference=0x0001,
            LT=0x8892,
            IOCRProperties=0x00000000,
            DataLength=5 + 1,  # 5 bytes data + 1 IOPS
            FrameID=0x8001,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            FrameSendOffset=0xFFFFFFFF,
            WatchdogFactor=10,
            DataHoldFactor=10
        )

        # Output IOCR (send to device)
        iocr_output = IOCRBlockReq(
            IOCRType=0x0002,  # Output
            IOCRReference=0x0002,
            LT=0x8892,
            IOCRProperties=0x00000000,
            DataLength=1,  # Minimal
            FrameID=0x8000,
            SendClockFactor=32,
            ReductionRatio=32,
            Phase=1,
            FrameSendOffset=0xFFFFFFFF,
            WatchdogFactor=10,
            DataHoldFactor=10
        )

        # Alarm CR
        alarm_cr = AlarmCRBlockReq(
            AlarmCRType=0x0001,
            LT=0x8892,
            AlarmCRProperties=0x00000000,
            RTATimeoutFactor=100,
            RTARetries=3,
            LocalAlarmReference=0x0001,
            MaxAlarmDataLength=128  # Fixed: was 200
        )

        # Expected Submodules - DAP + CPU Temp
        exp_submod = ExpectedSubmoduleBlockReq(
            NumberOfAPIs=1,
            API=0,
            SlotNumber=0,
            ModuleIdentNumber=GSDML_MOD_DAP,
            ModuleProperties=0,
            NumberOfSubmodules=1,
            SubmoduleBlocks=[
                ExpectedSubmoduleDataDescription(
                    SubslotNumber=1,
                    SubmoduleIdentNumber=GSDML_SUBMOD_DAP,
                    SubmoduleProperties=0,
                    DataDescription=[]
                )
            ]
        )

        # TODO: Add slot 1 (CPU Temp) to ExpectedSubmodules

        # Build RPC request
        pnio_req = PNIOServiceReqPDU(
            args_max=16384,
            blocks=[ar_block, iocr_input, iocr_output, alarm_cr, exp_submod]
        )

        rpc = DceRpc4(
            type="request",
            flags1=0x20,  # First frag
            opnum=0,  # Connect
            if_uuid=PNIO_INTERFACE_UUID,
            act_uuid=uuid.uuid4().bytes,
            payload=pnio_req
        )

        # Send via UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5.0)
        sock.sendto(bytes(rpc), (device_ip, RPC_PORT))

        try:
            resp_data, addr = sock.recvfrom(4096)
            print(f"[RPC] Response: {len(resp_data)} bytes from {addr}")
            # TODO: Parse response
            return True
        except socket.timeout:
            print("[RPC] Timeout waiting for response")
            return False
        finally:
            sock.close()


def main():
    """Main entry point"""
    import sys

    iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
    device_ip = sys.argv[2] if len(sys.argv) > 2 else "192.168.6.7"

    ctrl = PNController(interface=iface)

    # Try discovery first
    ctrl.discover()

    # Connect to known IP
    ctrl.connect(device_ip)


if __name__ == "__main__":
    main()
