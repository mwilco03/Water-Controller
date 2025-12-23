"""
Water Treatment Controller - Persistence Layer
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Modular database persistence layer.

This package provides SQLite-based persistence for all controller configurations,
split into focused modules for maintainability:

  base.py      - Database connection, schema initialization
  rtu.py       - RTU devices, sensors, controls
  alarms.py    - Alarm rules, shelved alarms (ISA-18.2)
  pid.py       - PID control loops
  modbus.py    - Modbus server config, devices, mappings
  sessions.py  - User session management
  users.py     - User management, authentication
  historian.py - Historian tags, slot configurations
  config.py    - Log forwarding, AD config, backups, import/export
  discovery.py - DCP discovery cache
  audit.py     - Audit log, command log
"""

import os
import logging

# Re-export everything for backward compatibility
from .base import (
    DB_PATH,
    get_db,
    init_database,
    initialize,
    is_initialized,
)

from .audit import (
    log_audit,
    get_audit_log,
    log_command,
    update_command_result,
    get_command_log,
    get_command_log_count,
    clear_old_command_logs,
)

from .rtu import (
    get_rtu_devices,
    get_rtu_device,
    create_rtu_device,
    update_rtu_device,
    delete_rtu_device,
    get_rtu_sensors,
    upsert_rtu_sensor,
    update_sensor_value,
    delete_rtu_sensor,
    clear_rtu_sensors,
    get_rtu_controls,
    upsert_rtu_control,
    update_control_state,
    delete_rtu_control,
    clear_rtu_controls,
    get_rtu_inventory,
)

from .alarms import (
    get_alarm_rules,
    get_alarm_rule,
    create_alarm_rule,
    update_alarm_rule,
    delete_alarm_rule,
    get_shelved_alarms,
    is_alarm_shelved,
    shelve_alarm,
    unshelve_alarm,
    cleanup_expired_shelves,
    get_shelved_alarm,
)

from .pid import (
    get_pid_loops,
    get_pid_loop,
    create_pid_loop,
    update_pid_loop,
    update_pid_setpoint,
    update_pid_mode,
    delete_pid_loop,
)

from .modbus import (
    get_modbus_server_config,
    update_modbus_server_config,
    get_modbus_downstream_devices,
    create_modbus_downstream_device,
    update_modbus_downstream_device,
    delete_modbus_downstream_device,
    get_modbus_register_mappings,
    create_modbus_register_mapping,
    update_modbus_register_mapping,
    delete_modbus_register_mapping,
)

from .sessions import (
    create_session,
    get_session,
    update_session_activity,
    delete_session,
    delete_session_by_prefix,
    cleanup_expired_sessions,
    get_active_sessions,
)

from .users import (
    USER_SYNC_SALT,
    hash_password,
    verify_password,
    get_users,
    get_user,
    get_user_by_username,
    create_user,
    update_user,
    delete_user,
    authenticate_user,
    get_users_for_sync,
    ensure_default_admin,
)

from .historian import (
    get_all_slot_configs,
    get_slot_configs_by_rtu,
    get_slot_config,
    upsert_slot_config,
    delete_slot_config,
    get_historian_tags,
    get_historian_tag,
    get_historian_tag_by_name,
    upsert_historian_tag,
    delete_historian_tag,
)

from .config import (
    get_log_forwarding_config,
    update_log_forwarding_config,
    get_ad_config,
    update_ad_config,
    get_backups,
    get_backup,
    create_backup_record,
    delete_backup_record,
    import_configuration,
    export_configuration,
)

from .discovery import (
    get_discovered_devices,
    upsert_discovered_device,
    mark_device_as_added,
    clear_discovery_cache,
)


logger = logging.getLogger(__name__)


def full_initialize() -> bool:
    """
    Full initialization including default admin user.
    Call this from application startup.
    """
    if not initialize():
        return False

    ensure_default_admin()
    return True


# Auto-initialize for backward compatibility (can be disabled via env var)
if os.environ.get('WTC_DB_AUTO_INIT', '1') == '1':
    full_initialize()
