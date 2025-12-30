"""
Water Treatment Controller - Database Persistence Layer (Compatibility Shim)
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

DEPRECATED: This module is kept for backward compatibility.
Use `from app.persistence import ...` instead.

The persistence layer has been refactored into focused modules:
  app/persistence/base.py      - Database connection, schema initialization
  app/persistence/rtu.py       - RTU devices, sensors, controls
  app/persistence/alarms.py    - Alarm rules, shelved alarms
  app/persistence/pid.py       - PID control loops
  app/persistence/modbus.py    - Modbus server config, devices, mappings
  app/persistence/sessions.py  - User session management
  app/persistence/users.py     - User management, authentication
  app/persistence/historian.py - Historian tags, slot configurations
  app/persistence/config.py    - Log forwarding, AD config, backups, import/export
  app/persistence/discovery.py - DCP discovery cache
  app/persistence/audit.py     - Audit log, command log
"""

# Re-export everything from the new modular package with explicit imports
# to satisfy linters (ruff F403/F405)

# Base
from app.persistence import (
    DB_PATH,
    get_db,
    init_database,
    initialize,
    is_initialized,
)

# Audit
from app.persistence import (
    clear_old_command_logs,
    get_audit_log,
    get_command_log,
    get_command_log_count,
    log_audit,
    log_command,
    update_command_result,
)

# RTU
from app.persistence import (
    clear_rtu_controls,
    clear_rtu_sensors,
    create_rtu_device,
    delete_rtu_control,
    delete_rtu_device,
    delete_rtu_sensor,
    get_rtu_controls,
    get_rtu_device,
    get_rtu_devices,
    get_rtu_inventory,
    get_rtu_sensors,
    update_control_state,
    update_rtu_device,
    update_sensor_value,
    upsert_rtu_control,
    upsert_rtu_sensor,
)

# Alarms
from app.persistence import (
    cleanup_expired_shelves,
    create_alarm_rule,
    delete_alarm_rule,
    get_alarm_rule,
    get_alarm_rules,
    get_shelved_alarm,
    get_shelved_alarms,
    is_alarm_shelved,
    shelve_alarm,
    unshelve_alarm,
    update_alarm_rule,
)

# PID
from app.persistence import (
    create_pid_loop,
    delete_pid_loop,
    get_pid_loop,
    get_pid_loops,
    update_pid_loop,
    update_pid_mode,
    update_pid_setpoint,
)

# Modbus
from app.persistence import (
    create_modbus_downstream_device,
    create_modbus_register_mapping,
    delete_modbus_downstream_device,
    delete_modbus_register_mapping,
    get_modbus_downstream_devices,
    get_modbus_register_mappings,
    get_modbus_server_config,
    update_modbus_downstream_device,
    update_modbus_register_mapping,
    update_modbus_server_config,
)

# Sessions
from app.persistence import (
    cleanup_expired_sessions,
    create_session,
    delete_session,
    delete_session_by_prefix,
    get_active_sessions,
    get_session,
    update_session_activity,
)

# Users
from app.persistence import (
    USER_SYNC_SALT,
    authenticate_user,
    create_user,
    delete_user,
    ensure_default_admin,
    get_user,
    get_user_by_username,
    get_users,
    get_users_for_sync,
    hash_password,
    update_user,
    verify_password,
)

# Historian
from app.persistence import (
    delete_historian_tag,
    delete_slot_config,
    get_all_slot_configs,
    get_historian_tag,
    get_historian_tag_by_name,
    get_historian_tags,
    get_slot_config,
    get_slot_configs_by_rtu,
    upsert_historian_tag,
    upsert_slot_config,
)

# Config
from app.persistence import (
    create_backup_record,
    delete_backup_record,
    export_configuration,
    get_ad_config,
    get_backup,
    get_backups,
    get_log_forwarding_config,
    import_configuration,
    update_ad_config,
    update_log_forwarding_config,
)

# Discovery
from app.persistence import (
    clear_discovery_cache,
    get_discovered_devices,
    mark_device_as_added,
    upsert_discovered_device,
)

# Explicit __all__ for tools that check it (sorted alphabetically)
__all__ = [
    # Alarms
    "cleanup_expired_shelves",
    "create_alarm_rule",
    "delete_alarm_rule",
    "get_alarm_rule",
    "get_alarm_rules",
    "get_shelved_alarm",
    "get_shelved_alarms",
    "is_alarm_shelved",
    "shelve_alarm",
    "unshelve_alarm",
    "update_alarm_rule",
    # Audit
    "clear_old_command_logs",
    "get_audit_log",
    "get_command_log",
    "get_command_log_count",
    "log_audit",
    "log_command",
    "update_command_result",
    # Base
    "DB_PATH",
    "get_db",
    "init_database",
    "initialize",
    "is_initialized",
    # Config
    "create_backup_record",
    "delete_backup_record",
    "export_configuration",
    "get_ad_config",
    "get_backup",
    "get_backups",
    "get_log_forwarding_config",
    "import_configuration",
    "update_ad_config",
    "update_log_forwarding_config",
    # Discovery
    "clear_discovery_cache",
    "get_discovered_devices",
    "mark_device_as_added",
    "upsert_discovered_device",
    # Historian
    "delete_historian_tag",
    "delete_slot_config",
    "get_all_slot_configs",
    "get_historian_tag",
    "get_historian_tag_by_name",
    "get_historian_tags",
    "get_slot_config",
    "get_slot_configs_by_rtu",
    "upsert_historian_tag",
    "upsert_slot_config",
    # Modbus
    "create_modbus_downstream_device",
    "create_modbus_register_mapping",
    "delete_modbus_downstream_device",
    "delete_modbus_register_mapping",
    "get_modbus_downstream_devices",
    "get_modbus_register_mappings",
    "get_modbus_server_config",
    "update_modbus_downstream_device",
    "update_modbus_register_mapping",
    "update_modbus_server_config",
    # PID
    "create_pid_loop",
    "delete_pid_loop",
    "get_pid_loop",
    "get_pid_loops",
    "update_pid_loop",
    "update_pid_mode",
    "update_pid_setpoint",
    # RTU
    "clear_rtu_controls",
    "clear_rtu_sensors",
    "create_rtu_device",
    "delete_rtu_control",
    "delete_rtu_device",
    "delete_rtu_sensor",
    "get_rtu_controls",
    "get_rtu_device",
    "get_rtu_devices",
    "get_rtu_inventory",
    "get_rtu_sensors",
    "update_control_state",
    "update_rtu_device",
    "update_sensor_value",
    "upsert_rtu_control",
    "upsert_rtu_sensor",
    # Sessions
    "cleanup_expired_sessions",
    "create_session",
    "delete_session",
    "delete_session_by_prefix",
    "get_active_sessions",
    "get_session",
    "update_session_activity",
    # Users
    "USER_SYNC_SALT",
    "authenticate_user",
    "create_user",
    "delete_user",
    "ensure_default_admin",
    "get_user",
    "get_user_by_username",
    "get_users",
    "get_users_for_sync",
    "hash_password",
    "update_user",
    "verify_password",
]
