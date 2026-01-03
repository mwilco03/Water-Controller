"""Initial schema - baseline for existing tables

Revision ID: 0001
Revises:
Create Date: 2025-01-03

This migration establishes a baseline from the existing schema.
Running 'alembic stamp head' on existing databases will mark them
as up-to-date without running the actual migrations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema.

    Note: These tables may already exist. This migration serves as a
    baseline for future migrations. For existing databases, run:
        alembic stamp head
    """
    # RTU table
    op.create_table(
        'rtus',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('station_name', sa.String(64), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=False),
        sa.Column('vendor_id', sa.String(10), nullable=True),
        sa.Column('device_id', sa.String(10), nullable=True),
        sa.Column('slot_count', sa.Integer(), nullable=True, default=16),
        sa.Column('firmware_version', sa.String(32), nullable=True),
        sa.Column('state', sa.String(16), nullable=True),
        sa.Column('state_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('station_name'),
    )
    op.create_index('ix_rtus_station_name', 'rtus', ['station_name'])

    # Slots table
    op.create_table(
        'slots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rtu_id', sa.Integer(), nullable=False),
        sa.Column('slot_number', sa.Integer(), nullable=False),
        sa.Column('module_type', sa.String(32), nullable=True),
        sa.Column('module_id', sa.String(32), nullable=True),
        sa.Column('status', sa.String(16), nullable=True),
        sa.Column('error_code', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['rtu_id'], ['rtus.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rtu_id', 'slot_number', name='uq_slot_rtu_number'),
    )

    # Sensors table
    op.create_table(
        'sensors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rtu_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=True),
        sa.Column('tag', sa.String(64), nullable=False),
        sa.Column('channel', sa.Integer(), nullable=False, default=0),
        sa.Column('sensor_type', sa.String(32), nullable=True),
        sa.Column('unit', sa.String(16), nullable=True),
        sa.Column('scale_min', sa.Float(), nullable=True, default=0.0),
        sa.Column('scale_max', sa.Float(), nullable=True, default=65535.0),
        sa.Column('eng_min', sa.Float(), nullable=True, default=0.0),
        sa.Column('eng_max', sa.Float(), nullable=True, default=100.0),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rtu_id'], ['rtus.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sensors_tag', 'sensors', ['tag'])

    # Controls table
    op.create_table(
        'controls',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rtu_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=True),
        sa.Column('tag', sa.String(64), nullable=False),
        sa.Column('channel', sa.Integer(), nullable=False, default=0),
        sa.Column('control_type', sa.String(32), nullable=True),
        sa.Column('equipment_type', sa.String(32), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['rtu_id'], ['rtus.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_controls_tag', 'controls', ['tag'])

    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('role', sa.String(16), nullable=False, default='viewer'),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('sync_to_rtus', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_index('ix_users_username', 'users', ['username'])

    # User sessions table
    op.create_table(
        'user_sessions',
        sa.Column('token', sa.String(256), nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('role', sa.String(16), nullable=False, default='viewer'),
        sa.Column('groups', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(256), nullable=True),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index('ix_user_sessions_expires', 'user_sessions', ['expires_at'])
    op.create_index('ix_user_sessions_username', 'user_sessions', ['username'])

    # Audit log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user', sa.String(64), nullable=True),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('resource_type', sa.String(32), nullable=True),
        sa.Column('resource_id', sa.String(64), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_timestamp', 'audit_log', ['timestamp'])
    op.create_index('ix_audit_log_user', 'audit_log', ['user'])
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])

    # PID loops table
    op.create_table(
        'pid_loops',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rtu_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('pv_sensor_tag', sa.String(64), nullable=False),
        sa.Column('cv_control_tag', sa.String(64), nullable=False),
        sa.Column('setpoint', sa.Float(), nullable=False, default=0.0),
        sa.Column('kp', sa.Float(), nullable=False, default=1.0),
        sa.Column('ki', sa.Float(), nullable=False, default=0.0),
        sa.Column('kd', sa.Float(), nullable=False, default=0.0),
        sa.Column('output_min', sa.Float(), nullable=True, default=0.0),
        sa.Column('output_max', sa.Float(), nullable=True, default=100.0),
        sa.Column('mode', sa.String(16), nullable=True),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rtu_id'], ['rtus.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Alarm rules table
    op.create_table(
        'alarm_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rtu_id', sa.Integer(), nullable=False),
        sa.Column('sensor_tag', sa.String(64), nullable=False),
        sa.Column('alarm_type', sa.String(16), nullable=False),
        sa.Column('priority', sa.String(16), nullable=False, default='MEDIUM'),
        sa.Column('setpoint', sa.Float(), nullable=False),
        sa.Column('deadband', sa.Float(), nullable=True, default=0.0),
        sa.Column('delay_seconds', sa.Integer(), nullable=True, default=0),
        sa.Column('message_template', sa.String(256), nullable=True),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rtu_id'], ['rtus.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alarm_rules_sensor', 'alarm_rules', ['sensor_tag'])

    # Alarm events table
    op.create_table(
        'alarm_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=True),
        sa.Column('rtu_name', sa.String(64), nullable=False),
        sa.Column('sensor_tag', sa.String(64), nullable=False),
        sa.Column('alarm_type', sa.String(16), nullable=False),
        sa.Column('priority', sa.String(16), nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('setpoint', sa.Float(), nullable=True),
        sa.Column('message', sa.String(256), nullable=True),
        sa.Column('state', sa.String(16), nullable=False, default='ACTIVE'),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(64), nullable=True),
        sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shelved_until', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['rule_id'], ['alarm_rules.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alarm_events_state', 'alarm_events', ['state'])
    op.create_index('ix_alarm_events_triggered', 'alarm_events', ['triggered_at'])

    # Config templates table
    op.create_table(
        'config_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(32), nullable=True),
        sa.Column('vendor_id', sa.Integer(), nullable=True),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('slot_count', sa.Integer(), nullable=True),
        sa.Column('config_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table('config_templates')
    op.drop_table('alarm_events')
    op.drop_table('alarm_rules')
    op.drop_table('pid_loops')
    op.drop_table('audit_log')
    op.drop_table('user_sessions')
    op.drop_table('users')
    op.drop_table('controls')
    op.drop_table('sensors')
    op.drop_table('slots')
    op.drop_table('rtus')
