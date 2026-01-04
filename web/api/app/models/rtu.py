"""
Water Treatment Controller - RTU Models
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

SQLAlchemy models for RTU, Slot, Sensor, and Control entities.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


class RtuState:
    """
    RTU connection state constants and state machine documentation.

    State Machine:
    ==============

        OFFLINE ────┬──────────────────────────────────┐
           │        │                                   │
           │ /connect                                   │ /connect (retry)
           ▼        │                                   │
      CONNECTING ───┴──────────► ERROR ◄───────────────┘
           │                       │
           │ AR established        │ /disconnect
           ▼                       ▼
       DISCOVERY                 OFFLINE
           │
           │ Modules enumerated
           ▼
        RUNNING ────────► ERROR ────► OFFLINE
                  │       ▲
                  │       │ comm failure
                  └───────┘

    Valid Transitions:
    ------------------
    - OFFLINE -> CONNECTING: POST /connect
    - CONNECTING -> RUNNING: AR established (automatic)
    - CONNECTING -> ERROR: Timeout or connection failure
    - RUNNING -> OFFLINE: POST /disconnect
    - RUNNING -> ERROR: Communication failure (automatic)
    - ERROR -> OFFLINE: POST /disconnect
    - ERROR -> CONNECTING: POST /connect (retry)

    Invariants:
    -----------
    1. Only one RTU can be in CONNECTING state at a time
       (prevents DCP/ARP conflicts during discovery)
    2. RUNNING state requires valid AR with PROFINET controller
    3. ERROR state preserves last_error for diagnostics
    4. state_since is updated on every state transition
    5. DELETE requires OFFLINE or ERROR state (no active connection)

    Recovery Behavior:
    ------------------
    - Watchdog restarts: RTUs return to OFFLINE, require reconnection
    - Power cycle: Same as watchdog - explicit reconnection needed
    - Network partition: RTU transitions to ERROR, then OFFLINE on disconnect
    """

    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    DISCOVERY = "DISCOVERY"
    RUNNING = "RUNNING"
    ERROR = "ERROR"

    @classmethod
    def can_connect(cls, current_state: str) -> bool:
        """Check if RTU can transition to CONNECTING."""
        return current_state in (cls.OFFLINE, cls.ERROR)

    @classmethod
    def can_disconnect(cls, current_state: str) -> bool:
        """Check if RTU can transition to OFFLINE."""
        return current_state in (cls.RUNNING, cls.ERROR)

    @classmethod
    def can_delete(cls, current_state: str) -> bool:
        """Check if RTU can be deleted."""
        return current_state in (cls.OFFLINE, cls.ERROR)

    @classmethod
    def requires_connection(cls, current_state: str) -> bool:
        """Check if state requires active connection."""
        return current_state == cls.RUNNING


class SlotStatus:
    """Slot status constants."""

    OK = "OK"
    EMPTY = "EMPTY"
    FAULT = "FAULT"
    PULLED = "PULLED"
    WRONG_MODULE = "WRONG_MODULE"


class ControlType:
    """Control type constants."""

    DISCRETE = "discrete"
    ANALOG = "analog"


class RTU(Base):
    """RTU device configuration and state."""

    __tablename__ = "rtus"

    id = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(32), unique=True, nullable=False, index=True)
    ip_address = Column(String(15), unique=True, nullable=False)
    vendor_id = Column(String(6), nullable=False)  # e.g., "0x002A"
    device_id = Column(String(6), nullable=False)  # e.g., "0x0405"
    slot_count = Column(Integer, nullable=False, default=8)

    # State tracking
    state = Column(String(20), nullable=False, default=RtuState.OFFLINE)
    state_since = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    transition_reason = Column(String(256), nullable=True)  # Why the last state change occurred
    last_error = Column(Text, nullable=True)

    # Version tracking (for version mismatch detection)
    rtu_version = Column(String(32), nullable=True)  # Reported RTU firmware version
    version_mismatch = Column(Boolean, default=False)  # True if version mismatch detected

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    slots = relationship("Slot", back_populates="rtu", cascade="all, delete-orphan")
    sensors = relationship("Sensor", back_populates="rtu", cascade="all, delete-orphan")
    controls = relationship("Control", back_populates="rtu", cascade="all, delete-orphan")

    def update_state(self, new_state: str, error: str | None = None,
                     reason: str | None = None):
        """Update RTU state with timestamp and transition reason.

        Per HARMONIOUS_SYSTEM_DESIGN.md Principle 4:
        Every state transition is logged with context explaining WHY.

        Args:
            new_state: The new state to transition to
            error: Optional error message (stored in last_error)
            reason: Why this transition occurred (stored in transition_reason)
                   Examples: "PROFINET AR established", "Watchdog timeout",
                            "Operator requested disconnect", "Network cable unplugged"
        """
        import logging
        logger = logging.getLogger(__name__)

        old_state = self.state
        self.state = new_state
        self.state_since = datetime.now(UTC)

        # Store transition reason
        if reason:
            self.transition_reason = reason
        elif error:
            self.transition_reason = f"Error: {error}"
        else:
            # Generate default reason based on transition
            self.transition_reason = f"Transition from {old_state}"

        # Handle error state
        if error:
            self.last_error = error
        elif new_state == RtuState.RUNNING:
            self.last_error = None

        # Log state transition with context (Principle 4)
        if old_state != new_state:
            logger.info(
                f"RTU {self.station_name}: {old_state} → {new_state} "
                f"(reason: {self.transition_reason})"
            )


class Slot(Base):
    """RTU slot configuration."""

    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_number = Column(Integer, nullable=False)

    # Module information
    module_id = Column(String(6), nullable=True)  # e.g., "0x0032"
    module_type = Column(String(32), nullable=True)  # e.g., "AI-8"
    status = Column(String(20), default=SlotStatus.EMPTY)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="slots")
    sensors = relationship("Sensor", back_populates="slot", cascade="all, delete-orphan")
    controls = relationship("Control", back_populates="slot", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("rtu_id", "slot_number", name="uix_rtu_slot"),
        Index("ix_slots_rtu_id", "rtu_id"),
    )


class Sensor(Base):
    """Sensor configuration."""

    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)

    tag = Column(String(32), unique=True, nullable=False, index=True)
    channel = Column(Integer, nullable=False)
    sensor_type = Column(String(32), nullable=False)  # level, flow, temp, pressure, etc.
    unit = Column(String(16), nullable=True)

    # Scaling
    scale_min = Column(Float, default=0.0)
    scale_max = Column(Float, default=100.0)
    eng_min = Column(Float, default=0.0)
    eng_max = Column(Float, default=100.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="sensors")
    slot = relationship("Slot", back_populates="sensors")

    # Indexes for foreign key lookups
    __table_args__ = (
        Index("ix_sensors_rtu_id", "rtu_id"),
        Index("ix_sensors_slot_id", "slot_id"),
    )


class Control(Base):
    """Control/actuator configuration."""

    __tablename__ = "controls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rtu_id = Column(Integer, ForeignKey("rtus.id", ondelete="CASCADE"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)

    tag = Column(String(32), unique=True, nullable=False, index=True)
    channel = Column(Integer, nullable=False)
    control_type = Column(String(16), nullable=False)  # discrete, analog
    equipment_type = Column(String(32), nullable=True)  # pump, valve, vfd, etc.

    # For analog controls
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    unit = Column(String(16), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    rtu = relationship("RTU", back_populates="controls")
    slot = relationship("Slot", back_populates="controls")

    # Indexes for foreign key lookups
    __table_args__ = (
        Index("ix_controls_rtu_id", "rtu_id"),
        Index("ix_controls_slot_id", "slot_id"),
    )
