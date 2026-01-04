"""
Water Treatment Controller - RTU State Machine
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Formal state machine for RTU connection states using the transitions library.

This module implements the RTU state machine documented in models/rtu.py,
providing proper transition validation and callbacks.

State Machine Diagram:
======================

    OFFLINE ────┬──────────────────────────────────┐
       │        │                                   │
       │ connect                                    │ connect (retry)
       ▼        │                                   │
  CONNECTING ───┴──────────► ERROR ◄───────────────┘
       │                       │
       │ ar_established        │ disconnect
       ▼                       ▼
   DISCOVERY                 OFFLINE
       │
       │ discovery_complete
       ▼
    RUNNING ────────► ERROR ────► OFFLINE
              │       ▲
              │       │ comm_failure
              └───────┘

Invariants:
-----------
1. Only one RTU can be in CONNECTING state at a time
2. RUNNING state requires valid AR with PROFINET controller
3. ERROR state preserves last_error for diagnostics
4. DELETE requires OFFLINE or ERROR state
"""

import logging
from datetime import UTC, datetime
from typing import Any, Callable

from transitions import Machine, MachineError

from ..models.rtu import RtuState

logger = logging.getLogger(__name__)


class RtuStateMachine:
    """
    Formal state machine for RTU connection lifecycle.

    Uses the transitions library to enforce valid state transitions
    and provide callbacks for state change events.

    Example:
        rtu_sm = RtuStateMachine(
            rtu_name="RTU-001",
            initial_state=RtuState.OFFLINE,
            on_state_change=lambda rtu, old, new, reason: log_transition(...)
        )

        rtu_sm.connect()  # OFFLINE -> CONNECTING
        rtu_sm.ar_established()  # CONNECTING -> DISCOVERY
        rtu_sm.discovery_complete()  # DISCOVERY -> RUNNING

        # Invalid transitions raise MachineError
        rtu_sm.connect()  # Raises: Can't trigger connect from RUNNING
    """

    # Define states
    states = [
        RtuState.OFFLINE,
        RtuState.CONNECTING,
        RtuState.DISCOVERY,
        RtuState.RUNNING,
        RtuState.ERROR,
    ]

    # Define transitions
    # Format: [trigger, source, dest, conditions, unless, before, after, prepare]
    transitions = [
        # Normal connection flow
        {
            "trigger": "connect",
            "source": RtuState.OFFLINE,
            "dest": RtuState.CONNECTING,
            "before": "_before_connect",
            "after": "_after_connect",
        },
        {
            "trigger": "ar_established",
            "source": RtuState.CONNECTING,
            "dest": RtuState.DISCOVERY,
            "after": "_after_ar_established",
        },
        {
            "trigger": "discovery_complete",
            "source": RtuState.DISCOVERY,
            "dest": RtuState.RUNNING,
            "after": "_after_discovery_complete",
        },

        # Disconnection
        {
            "trigger": "disconnect",
            "source": RtuState.RUNNING,
            "dest": RtuState.OFFLINE,
            "before": "_before_disconnect",
            "after": "_after_disconnect",
        },

        # Error handling
        {
            "trigger": "connection_failed",
            "source": RtuState.CONNECTING,
            "dest": RtuState.ERROR,
            "after": "_after_error",
        },
        {
            "trigger": "comm_failure",
            "source": RtuState.RUNNING,
            "dest": RtuState.ERROR,
            "after": "_after_error",
        },
        {
            "trigger": "discovery_failed",
            "source": RtuState.DISCOVERY,
            "dest": RtuState.ERROR,
            "after": "_after_error",
        },

        # Recovery from error
        {
            "trigger": "connect",
            "source": RtuState.ERROR,
            "dest": RtuState.CONNECTING,
            "before": "_before_connect",
            "after": "_after_connect",
        },
        {
            "trigger": "disconnect",
            "source": RtuState.ERROR,
            "dest": RtuState.OFFLINE,
            "after": "_after_disconnect",
        },

        # Abort during connection/discovery
        {
            "trigger": "abort",
            "source": [RtuState.CONNECTING, RtuState.DISCOVERY],
            "dest": RtuState.OFFLINE,
            "after": "_after_abort",
        },
    ]

    def __init__(
        self,
        rtu_name: str,
        initial_state: str = RtuState.OFFLINE,
        on_state_change: Callable[[str, str, str, str], None] | None = None,
    ):
        """
        Initialize RTU state machine.

        Args:
            rtu_name: Name of the RTU (for logging and callbacks)
            initial_state: Initial state (default OFFLINE)
            on_state_change: Callback when state changes.
                             Signature: (rtu_name, old_state, new_state, reason) -> None
        """
        self.rtu_name = rtu_name
        self.on_state_change = on_state_change
        self.last_error: str | None = None
        self.transition_reason: str | None = None
        self.state_since = datetime.now(UTC)

        # Track the previous state for callbacks
        self._previous_state: str | None = None

        # Initialize the state machine
        self.machine = Machine(
            model=self,
            states=self.states,
            transitions=self.transitions,
            initial=initial_state,
            auto_transitions=False,  # Disable automatic transitions
            ignore_invalid_triggers=False,  # Raise on invalid transitions
            send_event=True,  # Pass event data to callbacks
        )

    @property
    def current_state(self) -> str:
        """Get current state."""
        return self.state

    def can_transition(self, trigger: str) -> bool:
        """Check if a transition is valid from current state."""
        return self.machine.get_triggers(self.state).__contains__(trigger)

    def can_delete(self) -> bool:
        """Check if RTU can be deleted (must be OFFLINE or ERROR)."""
        return self.state in (RtuState.OFFLINE, RtuState.ERROR)

    def can_connect(self) -> bool:
        """Check if RTU can start connection."""
        return self.state in (RtuState.OFFLINE, RtuState.ERROR)

    def requires_connection(self) -> bool:
        """Check if current state requires active connection."""
        return self.state == RtuState.RUNNING

    # ========== Callback Methods ==========

    def _before_connect(self, event: Any) -> None:
        """Called before connect transition."""
        self._previous_state = self.state
        self.last_error = None
        self.transition_reason = event.kwargs.get("reason", "Connection requested")
        logger.info(f"RTU {self.rtu_name}: Starting connection...")

    def _after_connect(self, event: Any) -> None:
        """Called after connect transition."""
        self._notify_state_change("Connection initiated")

    def _after_ar_established(self, event: Any) -> None:
        """Called after AR (Application Relationship) is established."""
        self.transition_reason = "PROFINET AR established"
        self._notify_state_change("AR established, starting discovery")

    def _after_discovery_complete(self, event: Any) -> None:
        """Called after module discovery completes."""
        self.transition_reason = "Module discovery complete"
        self._notify_state_change("RTU now running")

    def _before_disconnect(self, event: Any) -> None:
        """Called before disconnect transition."""
        self._previous_state = self.state
        self.transition_reason = event.kwargs.get("reason", "Disconnect requested")

    def _after_disconnect(self, event: Any) -> None:
        """Called after disconnect transition."""
        self._notify_state_change("Disconnected")

    def _after_error(self, event: Any) -> None:
        """Called after error transition."""
        self.last_error = event.kwargs.get("error", "Unknown error")
        self.transition_reason = f"Error: {self.last_error}"
        self._notify_state_change(f"Error occurred: {self.last_error}")

    def _after_abort(self, event: Any) -> None:
        """Called after abort transition."""
        self.transition_reason = event.kwargs.get("reason", "Connection aborted")
        self._notify_state_change("Connection aborted")

    def _notify_state_change(self, reason: str) -> None:
        """Notify callback of state change."""
        self.state_since = datetime.now(UTC)
        if self.on_state_change and self._previous_state != self.state:
            self.on_state_change(
                self.rtu_name,
                self._previous_state or RtuState.OFFLINE,
                self.state,
                reason,
            )
        self._previous_state = self.state


class RtuStateMachineManager:
    """
    Manager for RTU state machines.

    Enforces invariants like "only one RTU can be CONNECTING at a time".
    Provides a registry of state machines for all RTUs.
    """

    def __init__(self):
        """Initialize the manager."""
        self._machines: dict[str, RtuStateMachine] = {}
        self._connecting_rtu: str | None = None

    def get_or_create(
        self,
        rtu_name: str,
        initial_state: str = RtuState.OFFLINE,
        on_state_change: Callable[[str, str, str, str], None] | None = None,
    ) -> RtuStateMachine:
        """
        Get or create a state machine for an RTU.

        Args:
            rtu_name: Name of the RTU
            initial_state: Initial state (only used if creating new)
            on_state_change: Callback for state changes

        Returns:
            RtuStateMachine instance
        """
        if rtu_name not in self._machines:
            self._machines[rtu_name] = RtuStateMachine(
                rtu_name=rtu_name,
                initial_state=initial_state,
                on_state_change=on_state_change,
            )
        return self._machines[rtu_name]

    def remove(self, rtu_name: str) -> bool:
        """
        Remove a state machine for an RTU.

        Args:
            rtu_name: Name of the RTU

        Returns:
            True if removed, False if not found
        """
        if rtu_name in self._machines:
            if self._connecting_rtu == rtu_name:
                self._connecting_rtu = None
            del self._machines[rtu_name]
            return True
        return False

    def can_start_connecting(self, rtu_name: str) -> tuple[bool, str | None]:
        """
        Check if an RTU can start connecting (enforces single-connecting invariant).

        Args:
            rtu_name: Name of the RTU wanting to connect

        Returns:
            Tuple of (can_connect, blocking_rtu_name)
        """
        if self._connecting_rtu is None:
            return (True, None)
        if self._connecting_rtu == rtu_name:
            return (True, None)
        return (False, self._connecting_rtu)

    def set_connecting(self, rtu_name: str) -> None:
        """Mark an RTU as currently connecting."""
        self._connecting_rtu = rtu_name

    def clear_connecting(self, rtu_name: str) -> None:
        """Clear the connecting lock for an RTU."""
        if self._connecting_rtu == rtu_name:
            self._connecting_rtu = None

    def get_all_states(self) -> dict[str, str]:
        """Get current states of all RTUs."""
        return {name: sm.current_state for name, sm in self._machines.items()}


# Global manager instance
_manager: RtuStateMachineManager | None = None


def get_state_machine_manager() -> RtuStateMachineManager:
    """Get the global state machine manager instance."""
    global _manager
    if _manager is None:
        _manager = RtuStateMachineManager()
    return _manager
