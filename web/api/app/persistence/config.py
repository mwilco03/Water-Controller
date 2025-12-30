"""
Water Treatment Controller - Config Persistence Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

System configuration: log forwarding, AD config, backups, import/export.
"""

import logging
from datetime import datetime
from typing import Any

from .audit import log_audit
from .base import get_db

logger = logging.getLogger(__name__)


# ============== Log Forwarding Config Operations ==============

def get_log_forwarding_config() -> dict[str, Any]:
    """Get log forwarding configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM log_forwarding_config WHERE id = 1')
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_log_forwarding_config(config: dict[str, Any]) -> bool:
    """Update log forwarding configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE log_forwarding_config
            SET enabled = ?, forward_type = ?, host = ?, port = ?, protocol = ?,
                index_name = ?, api_key = ?, tls_enabled = ?, tls_verify = ?,
                include_alarms = ?, include_events = ?, include_audit = ?,
                log_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (config.get('enabled', False), config.get('forward_type', 'syslog'),
              config.get('host', 'localhost'), config.get('port', 514),
              config.get('protocol', 'udp'), config.get('index_name'),
              config.get('api_key'), config.get('tls_enabled', False),
              config.get('tls_verify', True), config.get('include_alarms', True),
              config.get('include_events', True), config.get('include_audit', True),
              config.get('log_level', 'INFO')))
        conn.commit()
        log_audit('system', 'update', 'log_forwarding_config', '1',
                  f"Updated log forwarding config: enabled={config.get('enabled', False)}")
        return True


# ============== AD Config Operations ==============

def get_ad_config() -> dict[str, Any]:
    """Get Active Directory configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM ad_config WHERE id = 1')
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Don't expose bind password
            if result.get('bind_password'):
                result['bind_password'] = '********'
            return result
        return {}


def update_ad_config(config: dict[str, Any]) -> bool:
    """Update Active Directory configuration"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Handle bind_password - only update if a real value is provided
        bind_password = config.get('bind_password')
        if bind_password == '********':
            # Keep existing password
            cursor.execute('SELECT bind_password FROM ad_config WHERE id = 1')
            row = cursor.fetchone()
            bind_password = row['bind_password'] if row else None

        cursor.execute('''
            UPDATE ad_config
            SET enabled = ?, server = ?, port = ?, use_ssl = ?, base_dn = ?,
                admin_group = ?, bind_user = ?, bind_password = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (config.get('enabled', False), config.get('server', ''),
              config.get('port', 389), config.get('use_ssl', False),
              config.get('base_dn', ''), config.get('admin_group', 'WTC-Admins'),
              config.get('bind_user'), bind_password))
        conn.commit()
        log_audit('system', 'update', 'ad_config', '1',
                  f"Updated AD config: enabled={config.get('enabled', False)}")
        return True


# ============== Backup Metadata Operations ==============

def get_backups() -> list[dict[str, Any]]:
    """Get all backup records"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM backups ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]


def get_backup(backup_id: str) -> dict[str, Any] | None:
    """Get a specific backup record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM backups WHERE backup_id = ?', (backup_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_backup_record(backup_id: str, filename: str, description: str | None = None,
                         size_bytes: int = 0, includes_historian: bool = False) -> int:
    """Create a backup metadata record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO backups (backup_id, filename, description, size_bytes,
                includes_historian)
            VALUES (?, ?, ?, ?, ?)
        ''', (backup_id, filename, description, size_bytes,
              1 if includes_historian else 0))
        conn.commit()
        log_audit('system', 'create', 'backup', backup_id, f"Created backup {filename}")
        return cursor.lastrowid


def delete_backup_record(backup_id: str) -> bool:
    """Delete a backup metadata record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM backups WHERE backup_id = ?', (backup_id,))
        conn.commit()
        if cursor.rowcount > 0:
            log_audit('system', 'delete', 'backup', backup_id,
                      f"Deleted backup record {backup_id}")
            return True
        return False


# ============== Shared Import/Export Logic ==============

def import_configuration(config: dict[str, Any], user: str = "system") -> dict[str, int]:
    """
    Import configuration from a dictionary.
    This is the single source of truth for all import operations.
    """
    # Import these here to avoid circular imports
    from .alarms import create_alarm_rule, get_alarm_rule, update_alarm_rule
    from .historian import upsert_historian_tag, upsert_slot_config
    from .modbus import create_modbus_downstream_device, create_modbus_register_mapping, update_modbus_server_config
    from .pid import create_pid_loop, get_pid_loop, update_pid_loop
    from .rtu import create_rtu_device, get_rtu_device, update_rtu_device
    from .users import create_user, get_user_by_username

    imported = {
        "rtus": 0,
        "slot_configs": 0,
        "alarm_rules": 0,
        "pid_loops": 0,
        "historian_tags": 0,
        "modbus_devices": 0,
        "modbus_mappings": 0,
        "users": 0
    }

    # Import RTUs
    if "rtus" in config:
        for rtu_data in config["rtus"]:
            try:
                existing = get_rtu_device(rtu_data.get("station_name", ""))
                if existing:
                    update_rtu_device(rtu_data["station_name"], rtu_data)
                else:
                    create_rtu_device(rtu_data)
                imported["rtus"] += 1
            except Exception as e:
                # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
                logger.warning(
                    f"RTU import failed for {rtu_data.get('station_name')}: {e}. "
                    "RTU not restored from backup. "
                    "Manually add RTU or fix import file and retry."
                )

    # Import slot configs
    if "slot_configs" in config:
        for slot_data in config["slot_configs"]:
            try:
                upsert_slot_config(slot_data)
                imported["slot_configs"] += 1
            except Exception as e:
                logger.warning(
                    f"Slot config import failed: {e}. "
                    "Slot configuration not restored. "
                    "Manually configure slot or fix import file."
                )

    # Import alarm rules
    if "alarm_rules" in config:
        for rule_data in config["alarm_rules"]:
            try:
                rule_id = rule_data.get("id") or rule_data.get("rule_id")
                if rule_id:
                    existing = get_alarm_rule(rule_id)
                    if existing:
                        update_alarm_rule(rule_id, rule_data)
                    else:
                        create_alarm_rule(rule_data)
                else:
                    create_alarm_rule(rule_data)
                imported["alarm_rules"] += 1
            except Exception as e:
                logger.warning(
                    f"Alarm rule import failed: {e}. "
                    "Alarm monitoring may be incomplete. "
                    "Manually configure alarm rule or fix import file."
                )

    # Import PID loops
    if "pid_loops" in config:
        for pid_data in config["pid_loops"]:
            try:
                loop_id = pid_data.get("id") or pid_data.get("loop_id")
                if loop_id:
                    existing = get_pid_loop(loop_id)
                    if existing:
                        update_pid_loop(loop_id, pid_data)
                    else:
                        create_pid_loop(pid_data)
                else:
                    create_pid_loop(pid_data)
                imported["pid_loops"] += 1
            except Exception as e:
                logger.warning(
                    f"PID loop import failed: {e}. "
                    "Control loop not restored. "
                    "Manually configure PID loop or fix import file."
                )

    # Import historian tags
    if "historian_tags" in config:
        for tag_data in config["historian_tags"]:
            try:
                upsert_historian_tag(tag_data)
                imported["historian_tags"] += 1
            except Exception as e:
                logger.warning(
                    f"Historian tag import failed: {e}. "
                    "Data trending may be incomplete. "
                    "Manually configure historian tag or fix import file."
                )

    # Import modbus downstream devices
    if "modbus_devices" in config:
        for device_data in config["modbus_devices"]:
            try:
                create_modbus_downstream_device(device_data)
                imported["modbus_devices"] += 1
            except Exception as e:
                logger.warning(
                    f"Modbus device import failed: {e}. "
                    "Downstream device not restored. "
                    "Manually configure modbus device or fix import file."
                )

    # Import modbus register mappings
    if "modbus_mappings" in config:
        for mapping_data in config["modbus_mappings"]:
            try:
                create_modbus_register_mapping(mapping_data)
                imported["modbus_mappings"] += 1
            except Exception as e:
                logger.warning(
                    f"Modbus mapping import failed: {e}. "
                    "Register mapping not restored. "
                    "Manually configure mapping or fix import file."
                )

    # Import modbus server config (singleton)
    if "modbus_server" in config:
        try:
            update_modbus_server_config(config["modbus_server"])
        except Exception as e:
            logger.warning(
                f"Modbus server config import failed: {e}. "
                "Server config not restored. "
                "Manually configure modbus server settings."
            )

    # Import log forwarding config (singleton)
    if "log_forwarding" in config:
        try:
            update_log_forwarding_config(config["log_forwarding"])
        except Exception as e:
            logger.warning(
                f"Log forwarding config import failed: {e}. "
                "Log forwarding not restored. "
                "Manually configure log forwarding settings."
            )

    # Import AD config (singleton)
    if "ad_config" in config:
        try:
            update_ad_config(config["ad_config"])
        except Exception as e:
            logger.warning(
                f"AD config import failed: {e}. "
                "Directory integration not restored. "
                "Manually configure AD settings."
            )

    # Import users (without passwords - they must be reset)
    if "users" in config:
        for user_data in config["users"]:
            try:
                existing = get_user_by_username(user_data.get("username", ""))
                if not existing:
                    create_user({
                        "username": user_data["username"],
                        "password": "changeme",  # Must be changed by user
                        "role": user_data.get("role", "viewer"),
                        "active": user_data.get("active", True),
                        "sync_to_rtus": user_data.get("sync_to_rtus", True)
                    })
                    imported["users"] += 1
            except Exception as e:
                logger.warning(
                    f"User import failed for {user_data.get('username')}: {e}. "
                    "User account not restored. "
                    "Manually create user or fix import file."
                )

    log_audit(user, 'import', 'configuration', None, f"Imported: {imported}")
    return imported


def export_configuration() -> dict[str, Any]:
    """
    Export all configuration to a dictionary.
    This is the single source of truth for all export operations.
    """
    # Import these here to avoid circular imports
    from .alarms import get_alarm_rules
    from .historian import get_all_slot_configs, get_historian_tags
    from .modbus import get_modbus_downstream_devices, get_modbus_register_mappings, get_modbus_server_config
    from .pid import get_pid_loops
    from .rtu import get_rtu_devices
    from .users import get_users

    # Get users without password hashes for export
    users = get_users(include_inactive=True)
    users_export = [{
        "username": u["username"],
        "role": u["role"],
        "active": bool(u.get("active", True)),
        "sync_to_rtus": bool(u.get("sync_to_rtus", True))
    } for u in users if u["username"] != "admin"]  # Don't export admin

    return {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "rtus": get_rtu_devices(),
        "slot_configs": get_all_slot_configs(),
        "alarm_rules": get_alarm_rules(),
        "pid_loops": get_pid_loops(),
        "historian_tags": get_historian_tags(),
        "modbus_server": get_modbus_server_config(),
        "modbus_devices": get_modbus_downstream_devices(),
        "modbus_mappings": get_modbus_register_mappings(),
        "log_forwarding": get_log_forwarding_config(),
        "ad_config": get_ad_config(),
        "users": users_export
    }
