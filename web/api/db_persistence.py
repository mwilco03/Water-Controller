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


# Initialize database on module import
init_database()
