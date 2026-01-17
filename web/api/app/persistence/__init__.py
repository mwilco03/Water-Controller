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

import logging
import os

from .alarms import (
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
from .audit import (
    clear_old_command_logs,
    get_audit_log,
    get_command_log,
    get_command_log_count,
    log_audit,
    log_command,
    update_command_result,
)

# Re-export everything for backward compatibility
from .base import (
    DB_PATH,
    get_db,
    init_database,
    initialize,
    is_initialized,
)
from .config import (
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
from .discovery import (
    clear_discovery_cache,
    get_discovered_devices,
    mark_device_as_added,
    upsert_discovered_device,
)
from .historian import (
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
from .modbus import (
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
from .pid import (
    create_pid_loop,
    delete_pid_loop,
    get_pid_loop,
    get_pid_loops,
    update_pid_loop,
    update_pid_mode,
    update_pid_setpoint,
)
from .rtu import (
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
    update_rtu_state,
    update_rtu_device,
    upsert_rtu_control,
    upsert_rtu_sensor,
)
from .sessions import (
    cleanup_expired_sessions,
    create_session,
    delete_session,
    delete_session_by_prefix,
    get_active_sessions,
    get_session,
    update_session_activity,
)
from .users import (
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
