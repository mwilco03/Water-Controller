"""
Water Treatment Controller - RTU-Facing API Endpoints
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Endpoints designed for RTU consumption (not web UI).
These support RTU self-registration and device binding protocol.
"""

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.errors import build_success_response
from ...models.base import get_db
from ...models.rtu import RTU, RtuState
from ...schemas.rtu import RtuRegisterRequest, RtuRegisterResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Controller identification
CONTROLLER_NAME = "water-treat-controller"
CONFIG_VERSION = 1


def generate_enrollment_token() -> str:
    """Generate cryptographically secure enrollment token."""
    return f"wtc-enroll-{secrets.token_hex(16)}"


@router.post("/register", status_code=201)
async def register_rtu(
    request: RtuRegisterRequest,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    RTU self-registration endpoint.

    Called by RTU on first boot or when controller IP is configured.
    If enrollment_token matches a pre-created RTU, auto-approved.
    Otherwise:
      - If station_name exists: update with registration data, queue for approval
      - If station_name is new: create new RTU, queue for approval

    Returns:
        201: Registration successful (may require approval)
        409: Conflict (duplicate MAC address with different station_name)
    """
    logger.info(
        f"RTU registration request: station={request.station_name}, "
        f"serial={request.serial_number}, mac={request.mac_address}"
    )

    # Check for existing RTU by station_name
    existing_rtu = db.query(RTU).filter(
        RTU.station_name == request.station_name
    ).first()

    # Check for MAC address conflict (different station_name, same MAC)
    mac_conflict = db.query(RTU).filter(
        RTU.mac_address == request.mac_address,
        RTU.station_name != request.station_name
    ).first()

    if mac_conflict:
        logger.warning(
            f"MAC address conflict: {request.mac_address} already assigned to "
            f"{mac_conflict.station_name}, registration from {request.station_name}"
        )
        raise HTTPException(
            status_code=409,
            detail=f"MAC address {request.mac_address} already registered to "
                   f"station {mac_conflict.station_name}"
        )

    # Determine approval status
    auto_approved = False
    requires_approval = True

    if request.enrollment_token:
        # Check if token matches existing RTU
        token_match = db.query(RTU).filter(
            RTU.enrollment_token == request.enrollment_token
        ).first()

        if token_match:
            # Token matches - auto-approve and link
            if token_match.station_name != request.station_name:
                # Token was generated for a different station name
                # Update the existing record to match the registering RTU
                logger.info(
                    f"Token match with different name: {token_match.station_name} -> "
                    f"{request.station_name}, updating record"
                )
            existing_rtu = token_match
            auto_approved = True
            requires_approval = False
            logger.info(f"Auto-approving RTU {request.station_name} via enrollment token")

    if existing_rtu:
        # Update existing RTU with registration data
        existing_rtu.serial_number = request.serial_number
        existing_rtu.mac_address = request.mac_address
        existing_rtu.rtu_version = request.firmware_version
        existing_rtu.vendor_id = f"0x{request.vendor_id:04X}"
        existing_rtu.device_id = f"0x{request.device_id:04X}"
        existing_rtu.slot_count = request.sensor_count + request.actuator_count

        if auto_approved:
            existing_rtu.approved = True
            existing_rtu.update_state(
                RtuState.OFFLINE,
                reason="RTU registered with valid enrollment token"
            )
        else:
            existing_rtu.update_state(
                RtuState.OFFLINE,
                reason="RTU registered, awaiting admin approval"
            )

        db.commit()
        db.refresh(existing_rtu)

        response = RtuRegisterResponse(
            rtu_id=existing_rtu.id,
            enrollment_token=existing_rtu.enrollment_token,
            controller_name=CONTROLLER_NAME,
            approved=existing_rtu.approved,
            requires_approval=requires_approval,
            config_version=CONFIG_VERSION
        )

        logger.info(
            f"RTU {request.station_name} registration updated, "
            f"approved={existing_rtu.approved}"
        )
        return build_success_response(response.model_dump())

    else:
        # Create new RTU record
        new_token = generate_enrollment_token()

        new_rtu = RTU(
            station_name=request.station_name,
            ip_address="0.0.0.0",  # Will be updated on PROFINET connect
            vendor_id=f"0x{request.vendor_id:04X}",
            device_id=f"0x{request.device_id:04X}",
            slot_count=request.sensor_count + request.actuator_count,
            state=RtuState.OFFLINE,
            serial_number=request.serial_number,
            mac_address=request.mac_address,
            rtu_version=request.firmware_version,
            enrollment_token=new_token,
            approved=False,  # New RTUs require approval
        )
        new_rtu.update_state(
            RtuState.OFFLINE,
            reason="New RTU registered, awaiting admin approval"
        )

        db.add(new_rtu)
        db.commit()
        db.refresh(new_rtu)

        response = RtuRegisterResponse(
            rtu_id=new_rtu.id,
            enrollment_token=new_token,
            controller_name=CONTROLLER_NAME,
            approved=False,
            requires_approval=True,
            config_version=CONFIG_VERSION
        )

        logger.info(
            f"New RTU {request.station_name} registered, "
            f"token={new_token[:20]}..., awaiting approval"
        )
        return build_success_response(response.model_dump())


@router.get("/enrollment/{token}")
async def validate_enrollment_token(
    token: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Validate an enrollment token.

    Used by RTU to verify a token before attempting to bind.

    Returns:
        200: Token valid, includes station_name if assigned
        404: Token not found
    """
    rtu = db.query(RTU).filter(RTU.enrollment_token == token).first()

    if not rtu:
        raise HTTPException(status_code=404, detail="Enrollment token not found")

    return build_success_response({
        "valid": True,
        "station_name": rtu.station_name,
        "approved": rtu.approved,
        "controller_name": CONTROLLER_NAME,
    })


@router.get("/config/{station_name}")
async def get_rtu_config(
    station_name: str,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get current configuration for an RTU.

    RTU calls this to fetch its configuration from controller.
    Only returns config if RTU is approved.

    Returns:
        200: Configuration data
        403: RTU not approved
        404: RTU not found
    """
    rtu = db.query(RTU).filter(RTU.station_name == station_name).first()

    if not rtu:
        raise HTTPException(status_code=404, detail=f"RTU {station_name} not found")

    if not rtu.approved:
        raise HTTPException(
            status_code=403,
            detail=f"RTU {station_name} not approved. Contact administrator."
        )

    # Build config response
    # In full implementation, this would include sensor/actuator configs
    config = {
        "station_name": rtu.station_name,
        "config_version": CONFIG_VERSION,
        "slot_count": rtu.slot_count,
        "sensors": [],  # Populated when RTU reports sensor submodules via PROFINET
        "actuators": [],  # Populated when RTU reports actuator submodules via PROFINET
        "authority_mode": "SUPERVISED",
        "watchdog_ms": 3000,
    }

    return build_success_response(config)


@router.post("/{station_name}/status")
async def report_rtu_status(
    station_name: str,
    status: dict[str, Any],
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    RTU status report endpoint.

    RTU can report its health status here (optional - primary channel is PROFINET).

    Returns:
        200: Status received
        404: RTU not found
    """
    rtu = db.query(RTU).filter(RTU.station_name == station_name).first()

    if not rtu:
        raise HTTPException(status_code=404, detail=f"RTU {station_name} not found")

    logger.debug(f"RTU {station_name} status report: {status}")

    # Could update RTU last_seen, health metrics, etc.
    # For now, just acknowledge receipt

    return build_success_response({
        "acknowledged": True,
        "station_name": station_name,
    })
