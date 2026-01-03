"""Initial schema with consolidated models

Revision ID: 0001
Revises: None
Create Date: 2026-01-03

This migration consolidates the dual-model system:
- Legacy tables (rtu_devices, rtu_sensors, rtu_controls) are migrated to ORM tables
- ORM tables (rtus, slots, sensors, controls) become the single source of truth
- Legacy tables are dropped after data migration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Consolidate legacy models to ORM models.

    Migration strategy:
    1. Create ORM tables if they don't exist
    2. Migrate data from legacy tables to ORM tables
    3. Drop legacy tables
    """
    conn = op.get_bind()

    # Check which tables exist
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # ========================================================================
    # Step 1: Create ORM tables if they don't exist
    # ========================================================================

    # Create rtus table (ORM version)
    if "rtus" not in existing_tables:
        op.create_table(
            "rtus",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("station_name", sa.String(32), nullable=False),
            sa.Column("ip_address", sa.String(15), nullable=False),
            sa.Column("vendor_id", sa.String(6), nullable=False),
            sa.Column("device_id", sa.String(6), nullable=False),
            sa.Column("slot_count", sa.Integer(), nullable=False, server_default="8"),
            sa.Column("state", sa.String(20), nullable=False, server_default="OFFLINE"),
            sa.Column("state_since", sa.DateTime(timezone=True), nullable=True),
            sa.Column("transition_reason", sa.String(256), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("rtu_version", sa.String(32), nullable=True),
            sa.Column("version_mismatch", sa.Boolean(), server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("station_name"),
            sa.UniqueConstraint("ip_address"),
        )
        op.create_index("ix_rtus_station_name", "rtus", ["station_name"])

    # Create slots table
    if "slots" not in existing_tables:
        op.create_table(
            "slots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rtu_id", sa.Integer(), nullable=False),
            sa.Column("slot_number", sa.Integer(), nullable=False),
            sa.Column("module_id", sa.String(6), nullable=True),
            sa.Column("module_type", sa.String(32), nullable=True),
            sa.Column("status", sa.String(20), server_default="EMPTY"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["rtu_id"], ["rtus.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("rtu_id", "slot_number", name="uix_rtu_slot"),
        )

    # Create sensors table (ORM version)
    if "sensors" not in existing_tables:
        op.create_table(
            "sensors",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rtu_id", sa.Integer(), nullable=False),
            sa.Column("slot_id", sa.Integer(), nullable=False),
            sa.Column("tag", sa.String(32), nullable=False),
            sa.Column("channel", sa.Integer(), nullable=False),
            sa.Column("sensor_type", sa.String(32), nullable=False),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("scale_min", sa.Float(), server_default="0.0"),
            sa.Column("scale_max", sa.Float(), server_default="100.0"),
            sa.Column("eng_min", sa.Float(), server_default="0.0"),
            sa.Column("eng_max", sa.Float(), server_default="100.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["rtu_id"], ["rtus.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tag"),
        )
        op.create_index("ix_sensors_tag", "sensors", ["tag"])

    # Create controls table (ORM version)
    if "controls" not in existing_tables:
        op.create_table(
            "controls",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rtu_id", sa.Integer(), nullable=False),
            sa.Column("slot_id", sa.Integer(), nullable=False),
            sa.Column("tag", sa.String(32), nullable=False),
            sa.Column("channel", sa.Integer(), nullable=False),
            sa.Column("control_type", sa.String(16), nullable=False),
            sa.Column("equipment_type", sa.String(32), nullable=True),
            sa.Column("min_value", sa.Float(), nullable=True),
            sa.Column("max_value", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["rtu_id"], ["rtus.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tag"),
        )
        op.create_index("ix_controls_tag", "controls", ["tag"])

    # ========================================================================
    # Step 2: Migrate data from legacy tables to ORM tables
    # ========================================================================

    # Migrate rtu_devices -> rtus
    if "rtu_devices" in existing_tables and "rtus" in existing_tables:
        # Check if rtus is empty before migrating
        result = conn.execute(text("SELECT COUNT(*) FROM rtus"))
        rtus_count = result.scalar()

        if rtus_count == 0:
            # Migrate legacy RTU devices to ORM rtus table
            conn.execute(text("""
                INSERT INTO rtus (station_name, ip_address, vendor_id, device_id,
                                  slot_count, state, created_at, updated_at)
                SELECT station_name, ip_address,
                       printf('0x%04X', vendor_id), printf('0x%04X', device_id),
                       slot_count, 'OFFLINE', created_at, updated_at
                FROM rtu_devices
            """))

            # Create default slots for each migrated RTU
            rtus_result = conn.execute(text("SELECT id, slot_count FROM rtus"))
            for row in rtus_result:
                rtu_id, slot_count = row
                for slot_num in range(1, slot_count + 1):
                    conn.execute(text("""
                        INSERT INTO slots (rtu_id, slot_number, status)
                        VALUES (:rtu_id, :slot_num, 'EMPTY')
                    """), {"rtu_id": rtu_id, "slot_num": slot_num})

    # Migrate rtu_sensors -> sensors (mapping via station_name)
    if "rtu_sensors" in existing_tables and "sensors" in existing_tables:
        result = conn.execute(text("SELECT COUNT(*) FROM sensors"))
        sensors_count = result.scalar()

        if sensors_count == 0:
            # Get RTU and slot mappings
            # Note: Legacy sensors don't have slot info, so we put them in slot 1
            conn.execute(text("""
                INSERT INTO sensors (rtu_id, slot_id, tag, channel, sensor_type,
                                     unit, scale_min, scale_max, eng_min, eng_max, created_at)
                SELECT r.id, s.id, rs.sensor_id, 0, rs.sensor_type,
                       rs.unit, rs.scale_min, rs.scale_max, rs.scale_min, rs.scale_max, rs.created_at
                FROM rtu_sensors rs
                JOIN rtus r ON r.station_name = rs.rtu_station
                JOIN slots s ON s.rtu_id = r.id AND s.slot_number = 1
            """))

    # Migrate rtu_controls -> controls (mapping via station_name)
    if "rtu_controls" in existing_tables and "controls" in existing_tables:
        result = conn.execute(text("SELECT COUNT(*) FROM controls"))
        controls_count = result.scalar()

        if controls_count == 0:
            conn.execute(text("""
                INSERT INTO controls (rtu_id, slot_id, tag, channel, control_type,
                                      min_value, max_value, unit, created_at)
                SELECT r.id, s.id, rc.control_id, 0,
                       CASE WHEN rc.command_type = 'on_off' THEN 'discrete' ELSE 'analog' END,
                       rc.range_min, rc.range_max, rc.unit, rc.created_at
                FROM rtu_controls rc
                JOIN rtus r ON r.station_name = rc.rtu_station
                JOIN slots s ON s.rtu_id = r.id AND s.slot_number = 1
            """))

    # ========================================================================
    # Step 3: Drop legacy tables
    # ========================================================================

    if "rtu_controls" in existing_tables:
        op.drop_table("rtu_controls")

    if "rtu_sensors" in existing_tables:
        op.drop_table("rtu_sensors")

    if "rtu_devices" in existing_tables:
        op.drop_table("rtu_devices")


def downgrade() -> None:
    """
    Restore legacy tables from ORM tables.

    Note: This recreates the legacy schema but data fidelity may not be 100%
    due to schema differences (e.g., vendor_id format, missing slot info).
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Recreate legacy tables
    if "rtu_devices" not in existing_tables:
        op.create_table(
            "rtu_devices",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("station_name", sa.String(32), nullable=False),
            sa.Column("ip_address", sa.String(45), nullable=False),
            sa.Column("vendor_id", sa.Integer(), server_default="1171"),
            sa.Column("device_id", sa.Integer(), server_default="1"),
            sa.Column("slot_count", sa.Integer(), server_default="16"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("station_name"),
        )
        op.create_index("ix_rtu_devices_station_name", "rtu_devices", ["station_name"])

    if "rtu_sensors" not in existing_tables:
        op.create_table(
            "rtu_sensors",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rtu_station", sa.String(32), nullable=False),
            sa.Column("sensor_id", sa.String(32), nullable=False),
            sa.Column("sensor_type", sa.String(32), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("register_address", sa.Integer(), nullable=True),
            sa.Column("data_type", sa.String(16), server_default="FLOAT32"),
            sa.Column("scale_min", sa.Float(), server_default="0"),
            sa.Column("scale_max", sa.Float(), server_default="100"),
            sa.Column("last_value", sa.Float(), nullable=True),
            sa.Column("last_quality", sa.Integer(), server_default="0"),
            sa.Column("last_update", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("rtu_station", "sensor_id", name="uix_rtu_sensor"),
        )
        op.create_index("ix_rtu_sensors_rtu_station", "rtu_sensors", ["rtu_station"])

    if "rtu_controls" not in existing_tables:
        op.create_table(
            "rtu_controls",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rtu_station", sa.String(32), nullable=False),
            sa.Column("control_id", sa.String(32), nullable=False),
            sa.Column("control_type", sa.String(32), nullable=False),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("command_type", sa.String(16), server_default="on_off"),
            sa.Column("register_address", sa.Integer(), nullable=True),
            sa.Column("feedback_register", sa.Integer(), nullable=True),
            sa.Column("range_min", sa.Float(), nullable=True),
            sa.Column("range_max", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("last_state", sa.String(32), nullable=True),
            sa.Column("last_update", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("rtu_station", "control_id", name="uix_rtu_control"),
        )
        op.create_index("ix_rtu_controls_rtu_station", "rtu_controls", ["rtu_station"])

    # Migrate data back from ORM to legacy
    if "rtus" in existing_tables:
        conn.execute(text("""
            INSERT INTO rtu_devices (station_name, ip_address, vendor_id, device_id,
                                     slot_count, created_at, updated_at)
            SELECT station_name, ip_address,
                   CAST(REPLACE(vendor_id, '0x', '') AS INTEGER),
                   CAST(REPLACE(device_id, '0x', '') AS INTEGER),
                   slot_count, created_at, updated_at
            FROM rtus
        """))

    if "sensors" in existing_tables:
        conn.execute(text("""
            INSERT INTO rtu_sensors (rtu_station, sensor_id, sensor_type, name,
                                     unit, scale_min, scale_max, created_at)
            SELECT r.station_name, s.tag, s.sensor_type, s.tag,
                   s.unit, s.scale_min, s.scale_max, s.created_at
            FROM sensors s
            JOIN rtus r ON r.id = s.rtu_id
        """))

    if "controls" in existing_tables:
        conn.execute(text("""
            INSERT INTO rtu_controls (rtu_station, control_id, control_type, name,
                                      command_type, range_min, range_max, unit, created_at)
            SELECT r.station_name, c.tag, c.control_type, c.tag,
                   CASE WHEN c.control_type = 'discrete' THEN 'on_off' ELSE 'analog' END,
                   c.min_value, c.max_value, c.unit, c.created_at
            FROM controls c
            JOIN rtus r ON r.id = c.rtu_id
        """))
