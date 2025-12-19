"""
Water Treatment Controller - Database Persistence Layer
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

This module provides SQLite-based persistence for all controller configurations.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('WTC_DB_PATH', '/var/lib/water-controller/wtc.db')


@contextmanager
def get_db():
    """Context manager for database connections"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize the database schema"""
    with get_db() as conn:
        cursor = conn.cursor()

        # RTU Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rtu_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_name TEXT UNIQUE NOT NULL,
                ip_address TEXT NOT NULL,
                vendor_id INTEGER DEFAULT 1171,
                device_id INTEGER DEFAULT 1,
                slot_count INTEGER DEFAULT 16,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Slot Configurations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS slot_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rtu_station TEXT NOT NULL,
                slot INTEGER NOT NULL,
                subslot INTEGER DEFAULT 1,
                slot_type TEXT NOT NULL,
                name TEXT,
                unit TEXT,
                measurement_type TEXT,
                actuator_type TEXT,
                scale_min REAL DEFAULT 0,
                scale_max REAL DEFAULT 100,
                alarm_low REAL,
                alarm_high REAL,
                alarm_low_low REAL,
                alarm_high_high REAL,
                warning_low REAL,
                warning_high REAL,
                deadband REAL DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rtu_station, slot),
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name)
            )
        ''')

        # Alarm Rules table
        # NOTE: Alarm rules generate NOTIFICATIONS only.
        # Interlocks are configured and executed on the RTU directly.
        # The controller does NOT execute interlock logic.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alarm_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rtu_station TEXT NOT NULL,
                slot INTEGER NOT NULL,
                condition TEXT NOT NULL,
                threshold REAL NOT NULL,
                severity TEXT NOT NULL,
                delay_ms INTEGER DEFAULT 0,
                message TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name)
            )
        ''')

        # PID Loops table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pid_loops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                input_rtu TEXT NOT NULL,
                input_slot INTEGER NOT NULL,
                output_rtu TEXT NOT NULL,
                output_slot INTEGER NOT NULL,
                kp REAL DEFAULT 1.0,
                ki REAL DEFAULT 0.0,
                kd REAL DEFAULT 0.0,
                setpoint REAL DEFAULT 0,
                output_min REAL DEFAULT 0,
                output_max REAL DEFAULT 100,
                deadband REAL DEFAULT 0,
                integral_limit REAL DEFAULT 100,
                derivative_filter REAL DEFAULT 0.1,
                mode TEXT DEFAULT 'AUTO',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Historian Tags table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historian_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rtu_station TEXT NOT NULL,
                slot INTEGER NOT NULL,
                tag_name TEXT UNIQUE NOT NULL,
                unit TEXT,
                sample_rate_ms INTEGER DEFAULT 1000,
                deadband REAL DEFAULT 0.1,
                compression TEXT DEFAULT 'swinging_door',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rtu_station, slot),
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name)
            )
        ''')

        # Modbus Server Config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modbus_server_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                tcp_enabled INTEGER DEFAULT 1,
                tcp_port INTEGER DEFAULT 502,
                tcp_bind_address TEXT DEFAULT '0.0.0.0',
                rtu_enabled INTEGER DEFAULT 0,
                rtu_device TEXT DEFAULT '/dev/ttyUSB0',
                rtu_baud_rate INTEGER DEFAULT 9600,
                rtu_parity TEXT DEFAULT 'N',
                rtu_data_bits INTEGER DEFAULT 8,
                rtu_stop_bits INTEGER DEFAULT 1,
                rtu_slave_addr INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Modbus Downstream Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modbus_downstream_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                transport TEXT NOT NULL,
                tcp_host TEXT,
                tcp_port INTEGER DEFAULT 502,
                rtu_device TEXT,
                rtu_baud_rate INTEGER DEFAULT 9600,
                slave_addr INTEGER NOT NULL,
                poll_interval_ms INTEGER DEFAULT 1000,
                timeout_ms INTEGER DEFAULT 1000,
                enabled INTEGER DEFAULT 1,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Modbus Register Mappings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS modbus_register_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modbus_addr INTEGER NOT NULL,
                register_type TEXT NOT NULL,
                data_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                rtu_station TEXT NOT NULL,
                slot INTEGER NOT NULL,
                description TEXT,
                scaling_enabled INTEGER DEFAULT 0,
                scale_raw_min REAL DEFAULT 0,
                scale_raw_max REAL DEFAULT 65535,
                scale_eng_min REAL DEFAULT 0,
                scale_eng_max REAL DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(modbus_addr, register_type)
            )
        ''')

        # Log Forwarding Config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS log_forwarding_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 0,
                forward_type TEXT DEFAULT 'syslog',
                host TEXT DEFAULT 'localhost',
                port INTEGER DEFAULT 514,
                protocol TEXT DEFAULT 'udp',
                index_name TEXT,
                api_key TEXT,
                tls_enabled INTEGER DEFAULT 0,
                tls_verify INTEGER DEFAULT 1,
                include_alarms INTEGER DEFAULT 1,
                include_events INTEGER DEFAULT 1,
                include_audit INTEGER DEFAULT 1,
                log_level TEXT DEFAULT 'INFO',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Active Directory Config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ad_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 0,
                server TEXT DEFAULT '',
                port INTEGER DEFAULT 389,
                use_ssl INTEGER DEFAULT 0,
                base_dn TEXT DEFAULT '',
                admin_group TEXT DEFAULT 'WTC-Admins',
                bind_user TEXT,
                bind_password TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Backups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                description TEXT,
                size_bytes INTEGER DEFAULT 0,
                includes_historian INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Users table (for controller-managed users synced to RTUs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                active INTEGER DEFAULT 1,
                sync_to_rtus INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')

        # User Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                groups TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                user_agent TEXT
            )
        ''')

        # Audit Log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT
            )
        ''')

        # Initialize default modbus server config
        cursor.execute('''
            INSERT OR IGNORE INTO modbus_server_config (id) VALUES (1)
        ''')

        # Initialize default log forwarding config
        cursor.execute('''
            INSERT OR IGNORE INTO log_forwarding_config (id) VALUES (1)
        ''')

        # Initialize default AD config
        cursor.execute('''
            INSERT OR IGNORE INTO ad_config (id) VALUES (1)
        ''')

        conn.commit()
        logger.info("Database initialized successfully")


# ============== RTU Device Operations ==============

def get_rtu_devices() -> List[Dict[str, Any]]:
    """Get all RTU devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rtu_devices ORDER BY station_name')
        return [dict(row) for row in cursor.fetchall()]


def get_rtu_device(station_name: str) -> Optional[Dict[str, Any]]:
    """Get a single RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM rtu_devices WHERE station_name = ?', (station_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_rtu_device(device: Dict[str, Any]) -> int:
    """Create a new RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rtu_devices (station_name, ip_address, vendor_id, device_id, slot_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (device['station_name'], device['ip_address'], device.get('vendor_id', 1171),
              device.get('device_id', 1), device.get('slot_count', 16)))
        conn.commit()
        log_audit('system', 'create', 'rtu_device', device['station_name'], f"Created RTU {device['station_name']}")
        return cursor.lastrowid


def update_rtu_device(station_name: str, device: Dict[str, Any]) -> bool:
    """Update an RTU device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE rtu_devices
            SET ip_address = ?, vendor_id = ?, device_id = ?, slot_count = ?, updated_at = CURRENT_TIMESTAMP
            WHERE station_name = ?
        ''', (device['ip_address'], device.get('vendor_id', 1171),
              device.get('device_id', 1), device.get('slot_count', 16), station_name))
        conn.commit()
        return cursor.rowcount > 0


def delete_rtu_device(station_name: str) -> bool:
    """Delete an RTU device and all related configurations"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Delete related records
        cursor.execute('DELETE FROM slot_configs WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM alarm_rules WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM historian_tags WHERE rtu_station = ?', (station_name,))
        cursor.execute('DELETE FROM modbus_register_mappings WHERE rtu_station = ?', (station_name,))
        # Delete the RTU
        cursor.execute('DELETE FROM rtu_devices WHERE station_name = ?', (station_name,))
        conn.commit()
        log_audit('system', 'delete', 'rtu_device', station_name, f"Deleted RTU {station_name} with cascade")
        return cursor.rowcount > 0


# ============== Alarm Rules Operations ==============

def get_alarm_rules() -> List[Dict[str, Any]]:
    """Get all alarm rules"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alarm_rules ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def get_alarm_rule(rule_id: int) -> Optional[Dict[str, Any]]:
    """Get a single alarm rule"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM alarm_rules WHERE id = ?', (rule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_alarm_rule(rule: Dict[str, Any]) -> int:
    """
    Create a new alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alarm_rules (name, rtu_station, slot, condition, threshold, severity, delay_ms, message, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (rule['name'], rule['rtu_station'], rule['slot'], rule['condition'], rule['threshold'],
              rule['severity'], rule.get('delay_ms', 0), rule.get('message', ''), rule.get('enabled', True)))
        conn.commit()
        log_audit('system', 'create', 'alarm_rule', str(cursor.lastrowid), f"Created alarm rule {rule['name']}")
        return cursor.lastrowid


def update_alarm_rule(rule_id: int, rule: Dict[str, Any]) -> bool:
    """
    Update an alarm rule.

    NOTE: Alarm rules generate NOTIFICATIONS only.
    Interlocks are configured on the RTU directly.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE alarm_rules
            SET name = ?, rtu_station = ?, slot = ?, condition = ?, threshold = ?, severity = ?,
                delay_ms = ?, message = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (rule['name'], rule['rtu_station'], rule['slot'], rule['condition'], rule['threshold'],
              rule['severity'], rule.get('delay_ms', 0), rule.get('message', ''), rule.get('enabled', True), rule_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_alarm_rule(rule_id: int) -> bool:
    """Delete an alarm rule"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM alarm_rules WHERE id = ?', (rule_id,))
        conn.commit()
        log_audit('system', 'delete', 'alarm_rule', str(rule_id), f"Deleted alarm rule {rule_id}")
        return cursor.rowcount > 0


# ============== PID Loop Operations ==============

def get_pid_loops() -> List[Dict[str, Any]]:
    """Get all PID control loops"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pid_loops ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def get_pid_loop(loop_id: int) -> Optional[Dict[str, Any]]:
    """Get a single PID loop by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM pid_loops WHERE id = ?', (loop_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_pid_loop(loop: Dict[str, Any]) -> int:
    """Create a new PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO pid_loops (name, enabled, input_rtu, input_slot, output_rtu, output_slot,
                                   kp, ki, kd, setpoint, output_min, output_max, deadband,
                                   integral_limit, derivative_filter, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (loop['name'], loop.get('enabled', True), loop['input_rtu'], loop['input_slot'],
              loop['output_rtu'], loop['output_slot'], loop.get('kp', 1.0), loop.get('ki', 0.0),
              loop.get('kd', 0.0), loop.get('setpoint', 0), loop.get('output_min', 0),
              loop.get('output_max', 100), loop.get('deadband', 0), loop.get('integral_limit', 100),
              loop.get('derivative_filter', 0.1), loop.get('mode', 'AUTO')))
        conn.commit()
        log_audit('system', 'create', 'pid_loop', str(cursor.lastrowid), f"Created PID loop {loop['name']}")
        return cursor.lastrowid


def update_pid_loop(loop_id: int, loop: Dict[str, Any]) -> bool:
    """Update a PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops
            SET name = ?, enabled = ?, input_rtu = ?, input_slot = ?, output_rtu = ?, output_slot = ?,
                kp = ?, ki = ?, kd = ?, setpoint = ?, output_min = ?, output_max = ?, deadband = ?,
                integral_limit = ?, derivative_filter = ?, mode = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (loop['name'], loop.get('enabled', True), loop['input_rtu'], loop['input_slot'],
              loop['output_rtu'], loop['output_slot'], loop.get('kp', 1.0), loop.get('ki', 0.0),
              loop.get('kd', 0.0), loop.get('setpoint', 0), loop.get('output_min', 0),
              loop.get('output_max', 100), loop.get('deadband', 0), loop.get('integral_limit', 100),
              loop.get('derivative_filter', 0.1), loop.get('mode', 'AUTO'), loop_id))
        conn.commit()
        return cursor.rowcount > 0


def update_pid_setpoint(loop_id: int, setpoint: float) -> bool:
    """Update only the setpoint for a PID loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops SET setpoint = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        ''', (setpoint, loop_id))
        conn.commit()
        return cursor.rowcount > 0


def update_pid_mode(loop_id: int, mode: str) -> bool:
    """Update only the mode for a PID loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pid_loops SET mode = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        ''', (mode, loop_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_pid_loop(loop_id: int) -> bool:
    """Delete a PID control loop"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pid_loops WHERE id = ?', (loop_id,))
        conn.commit()
        log_audit('system', 'delete', 'pid_loop', str(loop_id), f"Deleted PID loop {loop_id}")
        return cursor.rowcount > 0


# ============== Modbus Operations ==============

def get_modbus_server_config() -> Dict[str, Any]:
    """Get Modbus server configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_server_config WHERE id = 1')
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_modbus_server_config(config: Dict[str, Any]) -> bool:
    """Update Modbus server configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_server_config
            SET tcp_enabled = ?, tcp_port = ?, tcp_bind_address = ?, rtu_enabled = ?,
                rtu_device = ?, rtu_baud_rate = ?, rtu_parity = ?, rtu_data_bits = ?,
                rtu_stop_bits = ?, rtu_slave_addr = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (config.get('tcp_enabled', True), config.get('tcp_port', 502), config.get('tcp_bind_address', '0.0.0.0'),
              config.get('rtu_enabled', False), config.get('rtu_device', '/dev/ttyUSB0'),
              config.get('rtu_baud_rate', 9600), config.get('rtu_parity', 'N'), config.get('rtu_data_bits', 8),
              config.get('rtu_stop_bits', 1), config.get('rtu_slave_addr', 1)))
        conn.commit()
        return True


def get_modbus_downstream_devices() -> List[Dict[str, Any]]:
    """Get all downstream Modbus devices"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_downstream_devices ORDER BY id')
        return [dict(row) for row in cursor.fetchall()]


def create_modbus_downstream_device(device: Dict[str, Any]) -> int:
    """Create a new downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO modbus_downstream_devices (name, transport, tcp_host, tcp_port, rtu_device,
                                                   rtu_baud_rate, slave_addr, poll_interval_ms, timeout_ms, enabled, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (device['name'], device['transport'], device.get('tcp_host'), device.get('tcp_port', 502),
              device.get('rtu_device'), device.get('rtu_baud_rate', 9600), device['slave_addr'],
              device.get('poll_interval_ms', 1000), device.get('timeout_ms', 1000),
              device.get('enabled', True), device.get('description', '')))
        conn.commit()
        log_audit('system', 'create', 'modbus_device', device['name'], f"Created Modbus device {device['name']}")
        return cursor.lastrowid


def update_modbus_downstream_device(device_id: int, device: Dict[str, Any]) -> bool:
    """Update a downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_downstream_devices
            SET name = ?, transport = ?, tcp_host = ?, tcp_port = ?, rtu_device = ?,
                rtu_baud_rate = ?, slave_addr = ?, poll_interval_ms = ?, timeout_ms = ?,
                enabled = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (device['name'], device['transport'], device.get('tcp_host'), device.get('tcp_port', 502),
              device.get('rtu_device'), device.get('rtu_baud_rate', 9600), device['slave_addr'],
              device.get('poll_interval_ms', 1000), device.get('timeout_ms', 1000),
              device.get('enabled', True), device.get('description', ''), device_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_modbus_downstream_device(device_id: int) -> bool:
    """Delete a downstream Modbus device"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM modbus_downstream_devices WHERE id = ?', (device_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_modbus_register_mappings() -> List[Dict[str, Any]]:
    """Get all Modbus register mappings"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM modbus_register_mappings ORDER BY modbus_addr')
        return [dict(row) for row in cursor.fetchall()]


def create_modbus_register_mapping(mapping: Dict[str, Any]) -> int:
    """Create a new Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO modbus_register_mappings (modbus_addr, register_type, data_type, source_type,
                                                  rtu_station, slot, description, scaling_enabled,
                                                  scale_raw_min, scale_raw_max, scale_eng_min, scale_eng_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (mapping['modbus_addr'], mapping['register_type'], mapping['data_type'], mapping['source_type'],
              mapping['rtu_station'], mapping['slot'], mapping.get('description', ''),
              mapping.get('scaling_enabled', False), mapping.get('scale_raw_min', 0),
              mapping.get('scale_raw_max', 65535), mapping.get('scale_eng_min', 0),
              mapping.get('scale_eng_max', 100)))
        conn.commit()
        return cursor.lastrowid


def update_modbus_register_mapping(mapping_id: int, mapping: Dict[str, Any]) -> bool:
    """Update a Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE modbus_register_mappings
            SET modbus_addr = ?, register_type = ?, data_type = ?, source_type = ?,
                rtu_station = ?, slot = ?, description = ?, scaling_enabled = ?,
                scale_raw_min = ?, scale_raw_max = ?, scale_eng_min = ?, scale_eng_max = ?
            WHERE id = ?
        ''', (mapping['modbus_addr'], mapping['register_type'], mapping['data_type'], mapping['source_type'],
              mapping['rtu_station'], mapping['slot'], mapping.get('description', ''),
              mapping.get('scaling_enabled', False), mapping.get('scale_raw_min', 0),
              mapping.get('scale_raw_max', 65535), mapping.get('scale_eng_min', 0),
              mapping.get('scale_eng_max', 100), mapping_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_modbus_register_mapping(mapping_id: int) -> bool:
    """Delete a Modbus register mapping"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM modbus_register_mappings WHERE id = ?', (mapping_id,))
        conn.commit()
        return cursor.rowcount > 0


# ============== Audit Log ==============

def log_audit(user: str, action: str, resource_type: str, resource_id: str, details: str, ip_address: str = None):
    """Log an audit event"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO audit_log (user, action, resource_type, resource_id, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user, action, resource_type, resource_id, details, ip_address))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")


def get_audit_log(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get audit log entries"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in cursor.fetchall()]


# ============== Session Management ==============

def create_session(token: str, username: str, role: str, groups: List[str],
                   expires_at: datetime, ip_address: str = None, user_agent: str = None) -> bool:
    """Create a new user session"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO user_sessions (token, username, role, groups, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (token, username, role, json.dumps(groups), expires_at.isoformat(),
                  ip_address, user_agent))
            conn.commit()
            log_audit(username, 'login', 'session', token[:8], f"User {username} logged in", ip_address)
            return True
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return False


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """Get session by token"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_sessions
            WHERE token = ? AND expires_at > datetime('now')
        ''', (token,))
        row = cursor.fetchone()
        if row:
            session = dict(row)
            # Parse groups from JSON
            if session.get('groups'):
                try:
                    session['groups'] = json.loads(session['groups'])
                except:
                    session['groups'] = []
            return session
        return None


def update_session_activity(token: str) -> bool:
    """Update session last activity time"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_sessions SET last_activity = CURRENT_TIMESTAMP
            WHERE token = ?
        ''', (token,))
        conn.commit()
        return cursor.rowcount > 0


def delete_session(token: str) -> bool:
    """Delete a session (logout)"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get username for audit log
        cursor.execute('SELECT username FROM user_sessions WHERE token = ?', (token,))
        row = cursor.fetchone()
        username = row['username'] if row else 'unknown'

        cursor.execute('DELETE FROM user_sessions WHERE token = ?', (token,))
        conn.commit()

        if cursor.rowcount > 0:
            log_audit(username, 'logout', 'session', token[:8], f"User {username} logged out")
            return True
        return False


def cleanup_expired_sessions() -> int:
    """Remove expired sessions"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM user_sessions WHERE expires_at < datetime('now')
        ''')
        conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired sessions")
        return deleted


def get_active_sessions(username: str = None) -> List[Dict[str, Any]]:
    """Get all active sessions, optionally filtered by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        if username:
            cursor.execute('''
                SELECT token, username, role, created_at, last_activity, ip_address
                FROM user_sessions
                WHERE username = ? AND expires_at > datetime('now')
                ORDER BY last_activity DESC
            ''', (username,))
        else:
            cursor.execute('''
                SELECT token, username, role, created_at, last_activity, ip_address
                FROM user_sessions
                WHERE expires_at > datetime('now')
                ORDER BY last_activity DESC
            ''')
        sessions = []
        for row in cursor.fetchall():
            session = dict(row)
            # Mask token for security
            session['token'] = session['token'][:8] + '...'
            sessions.append(session)
        return sessions


# ============== User Management ==============

# DJB2 hash constants (must match C implementation and RTU)
USER_SYNC_SALT = "NaCl4Life"


def _djb2_hash(s: str) -> int:
    """DJB2 hash algorithm by Dan Bernstein"""
    hash_val = 5381
    for c in s:
        hash_val = ((hash_val << 5) + hash_val) + ord(c)
        hash_val &= 0xFFFFFFFF  # Keep as 32-bit
    return hash_val


def hash_password(password: str) -> str:
    """
    Hash password using DJB2 with salt.
    Format: "DJB2:<salt_hash>:<password_hash>"
    This matches the RTU implementation for user sync.
    """
    salted = USER_SYNC_SALT + password
    hash_val = _djb2_hash(salted)
    salt_hash = _djb2_hash(USER_SYNC_SALT)
    return f"DJB2:{salt_hash:08X}:{hash_val:08X}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash"""
    computed = hash_password(password)
    return computed == stored_hash


def get_users(include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get all users"""
    with get_db() as conn:
        cursor = conn.cursor()
        if include_inactive:
            cursor.execute('SELECT * FROM users ORDER BY username')
        else:
            cursor.execute('SELECT * FROM users WHERE active = 1 ORDER BY username')
        return [dict(row) for row in cursor.fetchall()]


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Get a single user by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get a user by username"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user(user: Dict[str, Any]) -> int:
    """Create a new user"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Hash the password
        password_hash = hash_password(user['password'])
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, active, sync_to_rtus)
            VALUES (?, ?, ?, ?, ?)
        ''', (user['username'], password_hash, user.get('role', 'viewer'),
              user.get('active', True), user.get('sync_to_rtus', True)))
        conn.commit()
        log_audit('system', 'create', 'user', user['username'],
                  f"Created user {user['username']} with role {user.get('role', 'viewer')}")
        return cursor.lastrowid


def update_user(user_id: int, user: Dict[str, Any]) -> bool:
    """Update a user"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Build update fields
        fields = []
        values = []

        if 'role' in user:
            fields.append('role = ?')
            values.append(user['role'])

        if 'active' in user:
            fields.append('active = ?')
            values.append(1 if user['active'] else 0)

        if 'sync_to_rtus' in user:
            fields.append('sync_to_rtus = ?')
            values.append(1 if user['sync_to_rtus'] else 0)

        # Handle password change
        if 'password' in user and user['password']:
            fields.append('password_hash = ?')
            values.append(hash_password(user['password']))

        if not fields:
            return False

        fields.append('updated_at = CURRENT_TIMESTAMP')
        values.append(user_id)

        cursor.execute(f'''
            UPDATE users SET {', '.join(fields)} WHERE id = ?
        ''', tuple(values))
        conn.commit()
        return cursor.rowcount > 0


def delete_user(user_id: int) -> bool:
    """Delete a user (or deactivate)"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get username for audit log
        cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        username = row['username'] if row else 'unknown'

        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        if cursor.rowcount > 0:
            log_audit('system', 'delete', 'user', username, f"Deleted user {username}")
            return True
        return False


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user with username and password"""
    user = get_user_by_username(username)
    if not user:
        return None

    if not user.get('active', False):
        return None

    if not verify_password(password, user['password_hash']):
        return None

    # Update last login
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?
        ''', (user['id'],))
        conn.commit()

    return user


def get_users_for_sync() -> List[Dict[str, Any]]:
    """Get all users that should be synced to RTUs"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, role, active
            FROM users
            WHERE sync_to_rtus = 1
            ORDER BY username
        ''')
        return [dict(row) for row in cursor.fetchall()]


def ensure_default_admin():
    """Ensure default admin user exists"""
    admin = get_user_by_username('admin')
    if not admin:
        create_user({
            'username': 'admin',
            'password': 'H2OhYeah!',
            'role': 'admin',
            'active': True,
            'sync_to_rtus': True
        })
        logger.info("Created default admin user (username: admin)")


# ============== Slot Configuration Operations ==============

def get_all_slot_configs() -> List[Dict[str, Any]]:
    """Get all slot configurations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs ORDER BY rtu_station, slot')
        return [dict(row) for row in cursor.fetchall()]


def get_slot_configs_by_rtu(rtu_station: str) -> List[Dict[str, Any]]:
    """Get slot configurations for a specific RTU"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs WHERE rtu_station = ? ORDER BY slot', (rtu_station,))
        return [dict(row) for row in cursor.fetchall()]


def get_slot_config(rtu_station: str, slot: int) -> Optional[Dict[str, Any]]:
    """Get a specific slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slot_configs WHERE rtu_station = ? AND slot = ?', (rtu_station, slot))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_slot_config(config: Dict[str, Any]) -> int:
    """Create or update a slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO slot_configs (rtu_station, slot, subslot, slot_type, name, unit,
                                       measurement_type, actuator_type, scale_min, scale_max,
                                       alarm_low, alarm_high, alarm_low_low, alarm_high_high,
                                       warning_low, warning_high, deadband, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, slot) DO UPDATE SET
                subslot = excluded.subslot,
                slot_type = excluded.slot_type,
                name = excluded.name,
                unit = excluded.unit,
                measurement_type = excluded.measurement_type,
                actuator_type = excluded.actuator_type,
                scale_min = excluded.scale_min,
                scale_max = excluded.scale_max,
                alarm_low = excluded.alarm_low,
                alarm_high = excluded.alarm_high,
                alarm_low_low = excluded.alarm_low_low,
                alarm_high_high = excluded.alarm_high_high,
                warning_low = excluded.warning_low,
                warning_high = excluded.warning_high,
                deadband = excluded.deadband,
                enabled = excluded.enabled
        ''', (config['rtu_station'], config['slot'], config.get('subslot', 1),
              config['slot_type'], config.get('name'), config.get('unit'),
              config.get('measurement_type'), config.get('actuator_type'),
              config.get('scale_min', 0), config.get('scale_max', 100),
              config.get('alarm_low'), config.get('alarm_high'),
              config.get('alarm_low_low'), config.get('alarm_high_high'),
              config.get('warning_low'), config.get('warning_high'),
              config.get('deadband', 0), config.get('enabled', True)))
        conn.commit()
        return cursor.lastrowid


def delete_slot_config(rtu_station: str, slot: int) -> bool:
    """Delete a slot configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM slot_configs WHERE rtu_station = ? AND slot = ?', (rtu_station, slot))
        conn.commit()
        return cursor.rowcount > 0


# ============== Historian Tag Operations ==============

def get_historian_tags() -> List[Dict[str, Any]]:
    """Get all historian tags"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags ORDER BY tag_name')
        return [dict(row) for row in cursor.fetchall()]


def get_historian_tag(tag_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific historian tag by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags WHERE id = ?', (tag_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_historian_tag_by_name(tag_name: str) -> Optional[Dict[str, Any]]:
    """Get a historian tag by name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historian_tags WHERE tag_name = ?', (tag_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_historian_tag(tag: Dict[str, Any]) -> int:
    """Create or update a historian tag"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO historian_tags (rtu_station, slot, tag_name, unit, sample_rate_ms, deadband, compression)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rtu_station, slot) DO UPDATE SET
                tag_name = excluded.tag_name,
                unit = excluded.unit,
                sample_rate_ms = excluded.sample_rate_ms,
                deadband = excluded.deadband,
                compression = excluded.compression
        ''', (tag['rtu_station'], tag['slot'], tag['tag_name'], tag.get('unit'),
              tag.get('sample_rate_ms', 1000), tag.get('deadband', 0.1),
              tag.get('compression', 'swinging_door')))
        conn.commit()
        log_audit('system', 'upsert', 'historian_tag', tag['tag_name'],
                  f"Upserted historian tag {tag['tag_name']}")
        return cursor.lastrowid


def delete_historian_tag(tag_id: int) -> bool:
    """Delete a historian tag"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM historian_tags WHERE id = ?', (tag_id,))
        conn.commit()
        log_audit('system', 'delete', 'historian_tag', str(tag_id), f"Deleted historian tag {tag_id}")
        return cursor.rowcount > 0


# ============== Log Forwarding Config Operations ==============

def get_log_forwarding_config() -> Dict[str, Any]:
    """Get log forwarding configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM log_forwarding_config WHERE id = 1')
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_log_forwarding_config(config: Dict[str, Any]) -> bool:
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

def get_ad_config() -> Dict[str, Any]:
    """Get Active Directory configuration"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM ad_config WHERE id = 1')
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Don't expose bind password
            if 'bind_password' in result and result['bind_password']:
                result['bind_password'] = '********'
            return result
        return {}


def update_ad_config(config: Dict[str, Any]) -> bool:
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
                admin_group = ?, bind_user = ?, bind_password = ?, updated_at = CURRENT_TIMESTAMP
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

def get_backups() -> List[Dict[str, Any]]:
    """Get all backup records"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM backups ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]


def get_backup(backup_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific backup record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM backups WHERE backup_id = ?', (backup_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_backup_record(backup_id: str, filename: str, description: str = None,
                         size_bytes: int = 0, includes_historian: bool = False) -> int:
    """Create a backup metadata record"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO backups (backup_id, filename, description, size_bytes, includes_historian)
            VALUES (?, ?, ?, ?, ?)
        ''', (backup_id, filename, description, size_bytes, 1 if includes_historian else 0))
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
            log_audit('system', 'delete', 'backup', backup_id, f"Deleted backup record {backup_id}")
            return True
        return False


# ============== Shared Import Logic ==============

def import_configuration(config: Dict[str, Any], user: str = "system") -> Dict[str, int]:
    """
    Import configuration from a dictionary.
    This is the single source of truth for all import operations.

    Args:
        config: Configuration dictionary containing entities to import
        user: Username for audit logging

    Returns:
        Dictionary with counts of imported entities
    """
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
                logger.warning(f"Failed to import RTU {rtu_data.get('station_name')}: {e}")

    # Import slot configs
    if "slot_configs" in config:
        for slot_data in config["slot_configs"]:
            try:
                upsert_slot_config(slot_data)
                imported["slot_configs"] += 1
            except Exception as e:
                logger.warning(f"Failed to import slot config: {e}")

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
                logger.warning(f"Failed to import alarm rule: {e}")

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
                logger.warning(f"Failed to import PID loop: {e}")

    # Import historian tags
    if "historian_tags" in config:
        for tag_data in config["historian_tags"]:
            try:
                upsert_historian_tag(tag_data)
                imported["historian_tags"] += 1
            except Exception as e:
                logger.warning(f"Failed to import historian tag: {e}")

    # Import modbus downstream devices
    if "modbus_devices" in config:
        for device_data in config["modbus_devices"]:
            try:
                create_modbus_downstream_device(device_data)
                imported["modbus_devices"] += 1
            except Exception as e:
                logger.warning(f"Failed to import modbus device: {e}")

    # Import modbus register mappings
    if "modbus_mappings" in config:
        for mapping_data in config["modbus_mappings"]:
            try:
                create_modbus_register_mapping(mapping_data)
                imported["modbus_mappings"] += 1
            except Exception as e:
                logger.warning(f"Failed to import modbus mapping: {e}")

    # Import modbus server config (singleton)
    if "modbus_server" in config:
        try:
            update_modbus_server_config(config["modbus_server"])
        except Exception as e:
            logger.warning(f"Failed to import modbus server config: {e}")

    # Import log forwarding config (singleton)
    if "log_forwarding" in config:
        try:
            update_log_forwarding_config(config["log_forwarding"])
        except Exception as e:
            logger.warning(f"Failed to import log forwarding config: {e}")

    # Import AD config (singleton)
    if "ad_config" in config:
        try:
            update_ad_config(config["ad_config"])
        except Exception as e:
            logger.warning(f"Failed to import AD config: {e}")

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
                logger.warning(f"Failed to import user {user_data.get('username')}: {e}")

    log_audit(user, 'import', 'configuration', None, f"Imported: {imported}")
    return imported


def export_configuration() -> Dict[str, Any]:
    """
    Export all configuration to a dictionary.
    This is the single source of truth for all export operations.

    Returns:
        Dictionary containing all configuration entities
    """
    from datetime import datetime

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


# Flag to track initialization state
_initialized = False


def initialize() -> bool:
    """
    Explicitly initialize the database.
    Call this from application startup, not at import time.
    Returns True if successful, False otherwise.
    """
    global _initialized
    if _initialized:
        return True

    try:
        # Ensure database directory exists
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        init_database()
        ensure_default_admin()
        _initialized = True
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        return False


def is_initialized() -> bool:
    """Check if database has been initialized"""
    return _initialized


# Auto-initialize for backward compatibility (can be disabled via env var)
if os.environ.get('WTC_DB_AUTO_INIT', '1') == '1':
    initialize()
