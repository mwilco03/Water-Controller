"""
Water Treatment Controller - RTU Service Layer
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Business logic for RTU operations, extracted from route handlers.
This service layer enables testability and reusability across endpoints.
"""

import secrets
from datetime import UTC, datetime

from sqlalchemy.orm import Session


def generate_enrollment_token() -> str:
    """Generate cryptographically secure enrollment token."""
    return f"wtc-enroll-{secrets.token_hex(16)}"

from ..core.exceptions import (
    RtuAlreadyExistsError,
    RtuBusyError,
    RtuNotConnectedError,
    RtuNotFoundError,
)
from ..models.alarm import AlarmEvent, AlarmRule
from ..models.historian import HistorianSample
from ..models.rtu import RTU, Control, RtuState, Sensor
from ..schemas.rtu import RtuCreate, RtuStats


class RtuService:
    """
    Service layer for RTU operations.

    Encapsulates business logic separate from HTTP concerns,
    enabling easier testing and reuse.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: str) -> RTU:
        """Get RTU by station name or raise 404."""
        rtu = self.db.query(RTU).filter(RTU.station_name == name).first()
        if not rtu:
            raise RtuNotFoundError(name)
        return rtu

    def get_by_name_optional(self, name: str) -> RTU | None:
        """Get RTU by station name or return None."""
        return self.db.query(RTU).filter(RTU.station_name == name).first()

    def list_all(self, state_filter: str | None = None) -> list[RTU]:
        """List all RTUs with optional state filter."""
        query = self.db.query(RTU)
        if state_filter:
            query = query.filter(RTU.state == state_filter.upper())
        return query.order_by(RTU.station_name).all()

    def create(self, request: RtuCreate) -> RTU:
        """
        Create a new RTU configuration.

        Validates uniqueness of station_name and ip_address,
        creates the RTU record, and initializes empty slots.

        If station_name is not provided, auto-generates from IP address.
        """
        # Check for duplicate IP first
        existing_ip = self.db.query(RTU).filter(RTU.ip_address == request.ip_address).first()
        if existing_ip:
            raise RtuAlreadyExistsError("ip_address", request.ip_address)

        # Auto-generate station_name from IP if not provided
        station_name = request.station_name
        if not station_name:
            station_name = f"rtu-{request.ip_address.replace('.', '-')}"

        # Check for duplicate station_name
        existing = self.db.query(RTU).filter(RTU.station_name == station_name).first()
        if existing:
            raise RtuAlreadyExistsError("station_name", station_name)

        # Create RTU with enrollment token for device binding
        enrollment_token = generate_enrollment_token()

        rtu = RTU(
            station_name=station_name,
            ip_address=request.ip_address,
            vendor_id=request.vendor_id,
            device_id=request.device_id,
            slot_count=request.slot_count,
            state=RtuState.OFFLINE,
            state_since=datetime.now(UTC),
            enrollment_token=enrollment_token,
            approved=True,  # RTUs created via web UI are pre-approved
        )
        self.db.add(rtu)
        self.db.commit()
        self.db.refresh(rtu)
        return rtu

    def delete(self, name: str) -> dict:
        """
        Delete RTU and all associated resources.

        RTU must be OFFLINE or ERROR.
        Returns count of deleted resources.
        """
        rtu = self.get_by_name(name)

        # Check state - must be offline
        if rtu.state not in [RtuState.OFFLINE, RtuState.ERROR]:
            raise RtuBusyError(name, rtu.state)

        # Count resources for response
        deletion_counts = self._count_resources(rtu)

        # Delete RTU (cascade handles related records)
        self.db.delete(rtu)
        self.db.commit()

        return deletion_counts

    def _count_resources(self, rtu: RTU) -> dict:
        """Count resources associated with an RTU."""
        sensor_count = self.db.query(Sensor).filter(Sensor.rtu_id == rtu.id).count()
        control_count = self.db.query(Control).filter(Control.rtu_id == rtu.id).count()
        alarm_count = self.db.query(AlarmRule).filter(AlarmRule.rtu_station == rtu.station_name).count()
        historian_count = self.db.query(HistorianSample).join(Sensor).filter(
            Sensor.rtu_id == rtu.id
        ).count()

        return {
            "sensors": sensor_count,
            "controls": control_count,
            "alarms": alarm_count,
            "pid_loops": 0,
            "historian_samples": historian_count,
        }

    def get_deletion_impact(self, name: str) -> dict:
        """
        Get deletion impact preview for an RTU.

        Returns resource counts and estimated data size.
        """
        rtu = self.get_by_name(name)
        counts = self._count_resources(rtu)

        # Estimate data size (rough approximation: 16 bytes per sample)
        estimated_mb = counts["historian_samples"] * 16 / (1024 * 1024)
        counts["estimated_data_size_mb"] = round(estimated_mb, 2)

        return counts

    def get_stats(self, rtu: RTU) -> RtuStats:
        """Build statistics for an RTU."""
        sensor_count = self.db.query(Sensor).filter(Sensor.rtu_id == rtu.id).count()
        control_count = self.db.query(Control).filter(Control.rtu_id == rtu.id).count()

        alarm_count = self.db.query(AlarmRule).filter(AlarmRule.rtu_station == rtu.station_name).count()
        active_alarms = self.db.query(AlarmEvent).filter(
            AlarmEvent.rtu_station == rtu.station_name,
            AlarmEvent.state == "ACTIVE"
        ).count()

        return RtuStats(
            slot_count=rtu.slot_count or 0,
            configured_slots=0,  # Slots are PROFINET frame metadata, not database entities
            sensor_count=sensor_count,
            control_count=control_count,
            alarm_count=alarm_count,
            active_alarms=active_alarms,
            pid_loop_count=0,
        )

    def connect(self, name: str) -> RTU:
        """
        Initiate connection to RTU.

        RTU must be OFFLINE.
        """
        rtu = self.get_by_name(name)

        if rtu.state != RtuState.OFFLINE:
            raise RtuBusyError(name, rtu.state)

        # Update state to CONNECTING
        rtu.update_state(RtuState.CONNECTING)
        self.db.commit()

        return rtu

    def disconnect(self, name: str) -> RTU:
        """
        Disconnect from RTU.

        RTU must be RUNNING or ERROR.
        """
        rtu = self.get_by_name(name)

        if rtu.state == RtuState.OFFLINE:
            raise RtuNotConnectedError(name, rtu.state)

        if rtu.state == RtuState.CONNECTING:
            raise RtuBusyError(name, rtu.state)

        # Update state to OFFLINE
        rtu.update_state(RtuState.OFFLINE)
        self.db.commit()

        return rtu


def get_rtu_service(db: Session) -> RtuService:
    """Factory function for dependency injection."""
    return RtuService(db)
