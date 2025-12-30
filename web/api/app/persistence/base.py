"""
Water Treatment Controller - Database Base Module
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Database connection, schema initialization, and shared utilities.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.environ.get('WTC_DB_PATH', '/var/lib/water-controller/wtc.db')


class _DatabaseState:
    """
    Encapsulated database initialization state.
    Avoids module-level mutable global per Section 1.6.
    """
    __slots__ = ('_initialized',)

    def __init__(self) -> None:
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def mark_initialized(self) -> None:
        self._initialized = True


_db_state = _DatabaseState()


@contextmanager
def get_db():
    """Context manager for database connections"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
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

        # Users table
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

        # RTU Sensors inventory table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rtu_sensors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rtu_station TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                sensor_type TEXT NOT NULL,
                name TEXT NOT NULL,
                unit TEXT,
                register_address INTEGER,
                data_type TEXT DEFAULT 'FLOAT32',
                scale_min REAL DEFAULT 0,
                scale_max REAL DEFAULT 100,
                last_value REAL,
                last_quality INTEGER DEFAULT 0,
                last_update TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rtu_station, sensor_id),
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name) ON DELETE CASCADE
            )
        ''')

        # RTU Controls inventory table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rtu_controls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rtu_station TEXT NOT NULL,
                control_id TEXT NOT NULL,
                control_type TEXT NOT NULL,
                name TEXT NOT NULL,
                command_type TEXT DEFAULT 'on_off',
                register_address INTEGER,
                feedback_register INTEGER,
                range_min REAL,
                range_max REAL,
                unit TEXT,
                last_state TEXT,
                last_update TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(rtu_station, control_id),
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name) ON DELETE CASCADE
            )
        ''')

        # DCP Discovery results cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dcp_discovery_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac_address TEXT UNIQUE NOT NULL,
                ip_address TEXT,
                device_name TEXT,
                vendor_name TEXT,
                device_type TEXT,
                profinet_device_id INTEGER,
                profinet_vendor_id INTEGER,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_as_rtu INTEGER DEFAULT 0
            )
        ''')

        # Command Log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username TEXT NOT NULL,
                rtu_station TEXT NOT NULL,
                control_id TEXT NOT NULL,
                command TEXT NOT NULL,
                command_value REAL,
                result TEXT,
                error_message TEXT,
                source_ip TEXT,
                session_token TEXT,
                FOREIGN KEY (rtu_station) REFERENCES rtu_devices(station_name) ON DELETE CASCADE
            )
        ''')

        # Shelved Alarms table (ISA-18.2)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shelved_alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rtu_station TEXT NOT NULL,
                slot INTEGER NOT NULL,
                shelved_by TEXT NOT NULL,
                shelved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                shelf_duration_minutes INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                reason TEXT,
                active INTEGER DEFAULT 1,
                UNIQUE(rtu_station, slot, active)
            )
        ''')

        # Create indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_shelved_alarms_active
            ON shelved_alarms(active, expires_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_command_log_timestamp
            ON command_log(timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_command_log_username
            ON command_log(username)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_command_log_rtu
            ON command_log(rtu_station)
        ''')

        # Initialize singleton configs
        cursor.execute('INSERT OR IGNORE INTO modbus_server_config (id) VALUES (1)')
        cursor.execute('INSERT OR IGNORE INTO log_forwarding_config (id) VALUES (1)')
        cursor.execute('INSERT OR IGNORE INTO ad_config (id) VALUES (1)')

        conn.commit()
        logger.info("Database schema initialized")


def initialize() -> bool:
    """
    Explicitly initialize the database.
    Call this from application startup, not at import time.
    """
    if _db_state.initialized:
        return True

    try:
        db_path = Path(DB_PATH)
        if db_path.parent != Path():
            db_path.parent.mkdir(parents=True, exist_ok=True)

        init_database()
        _db_state.mark_initialized()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        # [CONDITION] + [CONSEQUENCE] + [ACTION] per Section 1.9
        logger.critical(
            f"Database initialization failed: {e}. "
            "Application cannot persist data. "
            "Check database path permissions and disk space, then restart."
        )
        return False


def is_initialized() -> bool:
    """Check if database has been initialized"""
    return _db_state.initialized
