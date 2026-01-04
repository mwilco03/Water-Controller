"""
Water Treatment Controller - State Machine Tests
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Unit tests for the RTU state machine.
"""

import pytest
from transitions import MachineError

from app.core.state_machine import (
    RtuStateMachine,
    RtuStateMachineManager,
    get_state_machine_manager,
)
from app.models.rtu import RtuState


class TestRtuStateMachine:
    """Tests for RtuStateMachine transitions."""

    def test_initial_state_offline(self):
        """State machine should start in OFFLINE state by default."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        assert sm.current_state == RtuState.OFFLINE

    def test_initial_state_custom(self):
        """State machine should accept custom initial state."""
        sm = RtuStateMachine(rtu_name="test-rtu", initial_state=RtuState.ERROR)
        assert sm.current_state == RtuState.ERROR

    def test_normal_connection_flow(self):
        """Test the normal connection flow: OFFLINE -> CONNECTING -> DISCOVERY -> RUNNING."""
        sm = RtuStateMachine(rtu_name="test-rtu")

        sm.connect()
        assert sm.current_state == RtuState.CONNECTING

        sm.ar_established()
        assert sm.current_state == RtuState.DISCOVERY

        sm.discovery_complete()
        assert sm.current_state == RtuState.RUNNING

    def test_disconnect_from_running(self):
        """Should be able to disconnect from RUNNING state."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.ar_established()
        sm.discovery_complete()
        assert sm.current_state == RtuState.RUNNING

        sm.disconnect(reason="Operator request")
        assert sm.current_state == RtuState.OFFLINE
        assert sm.transition_reason == "Operator request"

    def test_connection_failure(self):
        """Connection failure should transition to ERROR."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        assert sm.current_state == RtuState.CONNECTING

        sm.connection_failed(error="Timeout waiting for AR")
        assert sm.current_state == RtuState.ERROR
        assert sm.last_error == "Timeout waiting for AR"

    def test_comm_failure_from_running(self):
        """Communication failure should transition RUNNING -> ERROR."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.ar_established()
        sm.discovery_complete()
        assert sm.current_state == RtuState.RUNNING

        sm.comm_failure(error="Network cable unplugged")
        assert sm.current_state == RtuState.ERROR
        assert sm.last_error == "Network cable unplugged"

    def test_recovery_from_error(self):
        """Should be able to reconnect from ERROR state."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.connection_failed(error="Timeout")
        assert sm.current_state == RtuState.ERROR

        # Retry connection
        sm.connect()
        assert sm.current_state == RtuState.CONNECTING
        assert sm.last_error is None  # Cleared on retry

    def test_disconnect_from_error(self):
        """Should be able to disconnect from ERROR state."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.connection_failed(error="Timeout")
        assert sm.current_state == RtuState.ERROR

        sm.disconnect()
        assert sm.current_state == RtuState.OFFLINE

    def test_abort_connection(self):
        """Should be able to abort during CONNECTING."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        assert sm.current_state == RtuState.CONNECTING

        sm.abort(reason="User cancelled")
        assert sm.current_state == RtuState.OFFLINE
        assert sm.transition_reason == "User cancelled"

    def test_abort_discovery(self):
        """Should be able to abort during DISCOVERY."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.ar_established()
        assert sm.current_state == RtuState.DISCOVERY

        sm.abort()
        assert sm.current_state == RtuState.OFFLINE

    def test_invalid_transition_raises_error(self):
        """Invalid transitions should raise MachineError."""
        sm = RtuStateMachine(rtu_name="test-rtu")

        # Can't disconnect when OFFLINE
        with pytest.raises(MachineError):
            sm.disconnect()

        # Can't complete discovery when OFFLINE
        with pytest.raises(MachineError):
            sm.discovery_complete()

    def test_invalid_transition_from_running(self):
        """Invalid transitions from RUNNING should raise error."""
        sm = RtuStateMachine(rtu_name="test-rtu")
        sm.connect()
        sm.ar_established()
        sm.discovery_complete()
        assert sm.current_state == RtuState.RUNNING

        # Can't connect when already RUNNING
        with pytest.raises(MachineError):
            sm.connect()

        # Can't establish AR when already RUNNING
        with pytest.raises(MachineError):
            sm.ar_established()

    def test_can_transition(self):
        """can_transition() should correctly report valid transitions."""
        sm = RtuStateMachine(rtu_name="test-rtu")

        # OFFLINE can connect
        assert sm.can_transition("connect") is True
        assert sm.can_transition("disconnect") is False

        sm.connect()

        # CONNECTING can ar_established or connection_failed
        assert sm.can_transition("ar_established") is True
        assert sm.can_transition("connection_failed") is True
        assert sm.can_transition("connect") is False

    def test_can_delete(self):
        """can_delete() should only allow deletion in OFFLINE or ERROR."""
        sm = RtuStateMachine(rtu_name="test-rtu")

        assert sm.can_delete() is True  # OFFLINE

        sm.connect()
        assert sm.can_delete() is False  # CONNECTING

        sm.ar_established()
        assert sm.can_delete() is False  # DISCOVERY

        sm.discovery_complete()
        assert sm.can_delete() is False  # RUNNING

        sm.comm_failure(error="test")
        assert sm.can_delete() is True  # ERROR

    def test_state_change_callback(self):
        """State change callback should be called on transitions."""
        changes = []

        def on_change(rtu_name, old_state, new_state, reason):
            changes.append((rtu_name, old_state, new_state, reason))

        sm = RtuStateMachine(
            rtu_name="test-rtu",
            on_state_change=on_change,
        )

        sm.connect()
        sm.ar_established()

        assert len(changes) == 2
        assert changes[0][0] == "test-rtu"
        assert changes[0][1] == RtuState.OFFLINE
        assert changes[0][2] == RtuState.CONNECTING

        assert changes[1][1] == RtuState.CONNECTING
        assert changes[1][2] == RtuState.DISCOVERY


class TestRtuStateMachineManager:
    """Tests for RtuStateMachineManager."""

    def test_get_or_create(self):
        """Should create state machine on first access."""
        manager = RtuStateMachineManager()

        sm1 = manager.get_or_create("rtu-1")
        sm2 = manager.get_or_create("rtu-1")

        assert sm1 is sm2  # Same instance

        sm3 = manager.get_or_create("rtu-2")
        assert sm3 is not sm1  # Different RTU

    def test_remove(self):
        """Should remove state machine."""
        manager = RtuStateMachineManager()
        manager.get_or_create("rtu-1")

        assert manager.remove("rtu-1") is True
        assert manager.remove("rtu-1") is False  # Already removed

    def test_single_connecting_invariant(self):
        """Only one RTU should be able to connect at a time."""
        manager = RtuStateMachineManager()

        # First RTU can start connecting
        can_connect, blocking = manager.can_start_connecting("rtu-1")
        assert can_connect is True
        assert blocking is None

        manager.set_connecting("rtu-1")

        # Second RTU cannot connect while first is connecting
        can_connect, blocking = manager.can_start_connecting("rtu-2")
        assert can_connect is False
        assert blocking == "rtu-1"

        # First RTU can still check (it's the one connecting)
        can_connect, blocking = manager.can_start_connecting("rtu-1")
        assert can_connect is True

        # After clearing, second RTU can connect
        manager.clear_connecting("rtu-1")
        can_connect, blocking = manager.can_start_connecting("rtu-2")
        assert can_connect is True

    def test_get_all_states(self):
        """Should return states of all RTUs."""
        manager = RtuStateMachineManager()

        sm1 = manager.get_or_create("rtu-1")
        sm2 = manager.get_or_create("rtu-2", initial_state=RtuState.RUNNING)

        states = manager.get_all_states()

        assert states["rtu-1"] == RtuState.OFFLINE
        assert states["rtu-2"] == RtuState.RUNNING

    def test_global_manager_singleton(self):
        """get_state_machine_manager() should return same instance."""
        manager1 = get_state_machine_manager()
        manager2 = get_state_machine_manager()

        assert manager1 is manager2
