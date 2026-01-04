"""Add performance indexes for foreign keys and lookup columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-04

Adds indexes to improve query performance:
- Foreign key indexes on slots, sensors, controls (rtu_id, slot_id)
- Lookup indexes on pid_loops (name, input_rtu, output_rtu)
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes."""
    # Slots table - FK index
    op.create_index("ix_slots_rtu_id", "slots", ["rtu_id"])

    # Sensors table - FK indexes
    op.create_index("ix_sensors_rtu_id", "sensors", ["rtu_id"])
    op.create_index("ix_sensors_slot_id", "sensors", ["slot_id"])

    # Controls table - FK indexes
    op.create_index("ix_controls_rtu_id", "controls", ["rtu_id"])
    op.create_index("ix_controls_slot_id", "controls", ["slot_id"])

    # PID loops table - lookup indexes
    op.create_index("ix_pid_loops_name", "pid_loops", ["name"])
    op.create_index("ix_pid_loops_input_rtu", "pid_loops", ["input_rtu"])
    op.create_index("ix_pid_loops_output_rtu", "pid_loops", ["output_rtu"])


def downgrade() -> None:
    """Remove performance indexes."""
    # PID loops indexes
    op.drop_index("ix_pid_loops_output_rtu", "pid_loops")
    op.drop_index("ix_pid_loops_input_rtu", "pid_loops")
    op.drop_index("ix_pid_loops_name", "pid_loops")

    # Controls indexes
    op.drop_index("ix_controls_slot_id", "controls")
    op.drop_index("ix_controls_rtu_id", "controls")

    # Sensors indexes
    op.drop_index("ix_sensors_slot_id", "sensors")
    op.drop_index("ix_sensors_rtu_id", "sensors")

    # Slots index
    op.drop_index("ix_slots_rtu_id", "slots")
