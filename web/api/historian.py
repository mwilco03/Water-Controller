"""
Water Treatment Controller - TimescaleDB Historian Storage
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

This module provides time-series data storage using TimescaleDB.
Falls back to SQLite if TimescaleDB is not available.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Configuration from environment
TIMESCALE_HOST = os.environ.get('WTC_TIMESCALE_HOST', 'localhost')
TIMESCALE_PORT = int(os.environ.get('WTC_TIMESCALE_PORT', '5432'))
TIMESCALE_DB = os.environ.get('WTC_TIMESCALE_DB', 'wtc_historian')
TIMESCALE_USER = os.environ.get('WTC_TIMESCALE_USER', 'wtc')
TIMESCALE_PASSWORD = os.environ.get('WTC_TIMESCALE_PASSWORD', 'wtc_password')

# Fallback SQLite path
SQLITE_HISTORIAN_PATH = os.environ.get('WTC_HISTORIAN_DB', '/var/lib/water-controller/historian.db')

# Check if psycopg2 is available for PostgreSQL/TimescaleDB
try:
    import psycopg2
    import psycopg2.extras
    TIMESCALE_AVAILABLE = True
except ImportError:
    TIMESCALE_AVAILABLE = False
    logger.warning("psycopg2 not available, using SQLite fallback for historian")

import sqlite3


class CompressionType(str, Enum):
    NONE = "none"
    DEADBAND = "deadband"
    SWINGING_DOOR = "swinging_door"
    BOXCAR = "boxcar"


class HistorianBackend:
    """Abstract base for historian backends"""

    def init_schema(self):
        raise NotImplementedError

    def record_sample(self, tag_id: int, timestamp: datetime, value: float, quality: int):
        raise NotImplementedError

    def record_samples_batch(self, samples: list[tuple[int, datetime, float, int]]):
        raise NotImplementedError

    def query_raw(self, tag_id: int, start_time: datetime, end_time: datetime,
                  limit: int = 10000) -> list[dict[str, Any]]:
        raise NotImplementedError

    def query_aggregate(self, tag_id: int, start_time: datetime, end_time: datetime,
                        interval_seconds: int = 60) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_latest(self, tag_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def purge_old_data(self, retention_days: int) -> int:
        raise NotImplementedError


class TimescaleBackend(HistorianBackend):
    """TimescaleDB backend for production use"""

    def __init__(self):
        self.conn_params = {
            'host': TIMESCALE_HOST,
            'port': TIMESCALE_PORT,
            'dbname': TIMESCALE_DB,
            'user': TIMESCALE_USER,
            'password': TIMESCALE_PASSWORD
        }
        self._init_connection_pool()

    def _init_connection_pool(self):
        """Initialize connection pool"""
        try:
            from psycopg2 import pool
            self.pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                **self.conn_params
            )
            logger.info(f"TimescaleDB connection pool initialized: {TIMESCALE_HOST}:{TIMESCALE_PORT}")
        except Exception as e:
            logger.error(f"Failed to initialize TimescaleDB connection pool: {e}")
            self.pool = None

    @contextmanager
    def get_conn(self):
        """Get connection from pool"""
        conn = self.pool.getconn() if self.pool else None
        if not conn:
            raise RuntimeError("No database connection available")
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def init_schema(self):
        """Initialize TimescaleDB schema with hypertables"""
        with self.get_conn() as conn, conn.cursor() as cur:
            # Create extension if not exists
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

            # Historian samples table
            cur.execute("""
                    CREATE TABLE IF NOT EXISTS historian_samples (
                        time TIMESTAMPTZ NOT NULL,
                        tag_id INTEGER NOT NULL,
                        value DOUBLE PRECISION NOT NULL,
                        quality SMALLINT DEFAULT 192
                    );
                """)

            # Convert to hypertable if not already
            cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables
                        WHERE hypertable_name = 'historian_samples'
                    );
                """)
            is_hypertable = cur.fetchone()[0]

            if not is_hypertable:
                cur.execute("""
                        SELECT create_hypertable('historian_samples', 'time',
                                                  chunk_time_interval => INTERVAL '1 day',
                                                  if_not_exists => TRUE);
                    """)
                logger.info("Created historian_samples hypertable")

            # Create index on tag_id and time
            cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_historian_samples_tag_time
                    ON historian_samples (tag_id, time DESC);
                """)

            # Create continuous aggregates for common intervals
            # 1-minute aggregates
            cur.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS historian_1min
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 minute', time) AS bucket,
                        tag_id,
                        AVG(value) AS avg_value,
                        MIN(value) AS min_value,
                        MAX(value) AS max_value,
                        COUNT(*) AS sample_count,
                        LAST(value, time) AS last_value
                    FROM historian_samples
                    GROUP BY bucket, tag_id
                    WITH NO DATA;
                """)

            # 1-hour aggregates
            cur.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS historian_1hour
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 hour', time) AS bucket,
                        tag_id,
                        AVG(value) AS avg_value,
                        MIN(value) AS min_value,
                        MAX(value) AS max_value,
                        COUNT(*) AS sample_count,
                        LAST(value, time) AS last_value
                    FROM historian_samples
                    GROUP BY bucket, tag_id
                    WITH NO DATA;
                """)

            # 1-day aggregates
            cur.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS historian_1day
                    WITH (timescaledb.continuous) AS
                    SELECT
                        time_bucket('1 day', time) AS bucket,
                        tag_id,
                        AVG(value) AS avg_value,
                        MIN(value) AS min_value,
                        MAX(value) AS max_value,
                        COUNT(*) AS sample_count,
                        LAST(value, time) AS last_value
                    FROM historian_samples
                    GROUP BY bucket, tag_id
                    WITH NO DATA;
                """)

            # Add refresh policies for continuous aggregates
            try:
                cur.execute("""
                        SELECT add_continuous_aggregate_policy('historian_1min',
                            start_offset => INTERVAL '1 hour',
                            end_offset => INTERVAL '1 minute',
                            schedule_interval => INTERVAL '1 minute',
                            if_not_exists => TRUE);
                    """)
                cur.execute("""
                        SELECT add_continuous_aggregate_policy('historian_1hour',
                            start_offset => INTERVAL '1 day',
                            end_offset => INTERVAL '1 hour',
                            schedule_interval => INTERVAL '1 hour',
                            if_not_exists => TRUE);
                    """)
                cur.execute("""
                        SELECT add_continuous_aggregate_policy('historian_1day',
                            start_offset => INTERVAL '7 days',
                            end_offset => INTERVAL '1 day',
                            schedule_interval => INTERVAL '1 day',
                            if_not_exists => TRUE);
                    """)
            except Exception as e:
                logger.warning(f"Failed to add continuous aggregate policies: {e}")

            # Add compression policy (compress chunks older than 7 days)
            try:
                cur.execute("""
                        ALTER TABLE historian_samples SET (
                            timescaledb.compress,
                            timescaledb.compress_segmentby = 'tag_id'
                        );
                    """)
                cur.execute("""
                        SELECT add_compression_policy('historian_samples',
                            INTERVAL '7 days', if_not_exists => TRUE);
                    """)
            except Exception as e:
                logger.warning(f"Failed to add compression policy: {e}")

            # Add retention policy (drop chunks older than 365 days by default)
            try:
                cur.execute("""
                        SELECT add_retention_policy('historian_samples',
                            INTERVAL '365 days', if_not_exists => TRUE);
                    """)
            except Exception as e:
                logger.warning(f"Failed to add retention policy: {e}")

            conn.commit()
            logger.info("TimescaleDB historian schema initialized")

    def record_sample(self, tag_id: int, timestamp: datetime, value: float, quality: int = 192):
        """Record a single sample"""
        with self.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO historian_samples (time, tag_id, value, quality) VALUES (%s, %s, %s, %s)",
                (timestamp, tag_id, value, quality)
            )
            conn.commit()

    def record_samples_batch(self, samples: list[tuple[int, datetime, float, int]]):
        """Record multiple samples efficiently"""
        if not samples:
            return

        with self.get_conn() as conn, conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO historian_samples (tag_id, time, value, quality) VALUES %s",
                samples,
                template="(%s, %s, %s, %s)"
            )
            conn.commit()

    def query_raw(self, tag_id: int, start_time: datetime, end_time: datetime,
                  limit: int = 10000) -> list[dict[str, Any]]:
        """Query raw samples"""
        with self.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                    SELECT time, value, quality
                    FROM historian_samples
                    WHERE tag_id = %s AND time >= %s AND time <= %s
                    ORDER BY time ASC
                    LIMIT %s
                """, (tag_id, start_time, end_time, limit))
            return [dict(row) for row in cur.fetchall()]

    def query_aggregate(self, tag_id: int, start_time: datetime, end_time: datetime,
                        interval_seconds: int = 60) -> list[dict[str, Any]]:
        """Query aggregated data"""
        # Choose appropriate materialized view based on interval
        (end_time - start_time).total_seconds()

        if interval_seconds >= 86400:  # 1 day or more
            view = "historian_1day"
        elif interval_seconds >= 3600:  # 1 hour or more
            view = "historian_1hour"
        elif interval_seconds >= 60:  # 1 minute or more
            view = "historian_1min"
        else:
            # Use raw data with time_bucket for sub-minute intervals
            with self.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                        SELECT
                            time_bucket('{interval_seconds} seconds', time) AS bucket,
                            AVG(value) AS avg_value,
                            MIN(value) AS min_value,
                            MAX(value) AS max_value,
                            COUNT(*) AS sample_count
                        FROM historian_samples
                        WHERE tag_id = %s AND time >= %s AND time <= %s
                        GROUP BY bucket
                        ORDER BY bucket ASC
                    """, (tag_id, start_time, end_time))
                return [dict(row) for row in cur.fetchall()]

        with self.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                    SELECT bucket, avg_value, min_value, max_value, sample_count
                    FROM {view}
                    WHERE tag_id = %s AND bucket >= %s AND bucket <= %s
                    ORDER BY bucket ASC
                """, (tag_id, start_time, end_time))
            return [dict(row) for row in cur.fetchall()]

    def get_latest(self, tag_id: int) -> dict[str, Any] | None:
        """Get latest value for a tag"""
        with self.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                    SELECT time, value, quality
                    FROM historian_samples
                    WHERE tag_id = %s
                    ORDER BY time DESC
                    LIMIT 1
                """, (tag_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def purge_old_data(self, retention_days: int) -> int:
        """Manually purge old data (in addition to retention policy)"""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        with self.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM historian_samples WHERE time < %s",
                (cutoff,)
            )
            deleted = cur.rowcount
            conn.commit()
            return deleted

    def get_statistics(self, tag_id: int | None = None) -> dict[str, Any]:
        """Get historian statistics"""
        with self.get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if tag_id:
                cur.execute("""
                        SELECT
                            COUNT(*) as total_samples,
                            MIN(time) as oldest_sample,
                            MAX(time) as newest_sample,
                            pg_size_pretty(pg_total_relation_size('historian_samples')) as storage_size
                        FROM historian_samples
                        WHERE tag_id = %s
                    """, (tag_id,))
            else:
                cur.execute("""
                        SELECT
                            COUNT(*) as total_samples,
                            COUNT(DISTINCT tag_id) as total_tags,
                            MIN(time) as oldest_sample,
                            MAX(time) as newest_sample,
                            pg_size_pretty(pg_total_relation_size('historian_samples')) as storage_size
                        FROM historian_samples
                    """)
            row = cur.fetchone()
            return dict(row) if row else {}


class SQLiteBackend(HistorianBackend):
    """SQLite fallback backend for development/testing"""

    def __init__(self):
        self.db_path = SQLITE_HISTORIAN_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self):
        """Initialize SQLite schema"""
        with self.get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historian_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TIMESTAMP NOT NULL,
                    tag_id INTEGER NOT NULL,
                    value REAL NOT NULL,
                    quality INTEGER DEFAULT 192
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_samples_tag_time
                ON historian_samples (tag_id, time DESC)
            """)

            conn.commit()
            logger.info("SQLite historian schema initialized")

    def record_sample(self, tag_id: int, timestamp: datetime, value: float, quality: int = 192):
        """Record a single sample"""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO historian_samples (time, tag_id, value, quality) VALUES (?, ?, ?, ?)",
                (timestamp.isoformat(), tag_id, value, quality)
            )
            conn.commit()

    def record_samples_batch(self, samples: list[tuple[int, datetime, float, int]]):
        """Record multiple samples"""
        if not samples:
            return

        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO historian_samples (tag_id, time, value, quality) VALUES (?, ?, ?, ?)",
                [(s[0], s[1].isoformat(), s[2], s[3]) for s in samples]
            )
            conn.commit()

    def query_raw(self, tag_id: int, start_time: datetime, end_time: datetime,
                  limit: int = 10000) -> list[dict[str, Any]]:
        """Query raw samples"""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT time, value, quality
                FROM historian_samples
                WHERE tag_id = ? AND time >= ? AND time <= ?
                ORDER BY time ASC
                LIMIT ?
            """, (tag_id, start_time.isoformat(), end_time.isoformat(), limit))
            return [dict(row) for row in cursor.fetchall()]

    def query_aggregate(self, tag_id: int, start_time: datetime, end_time: datetime,
                        interval_seconds: int = 60) -> list[dict[str, Any]]:
        """Query aggregated data using window functions"""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            # SQLite doesn't have time_bucket, use strftime for grouping
            cursor.execute("""
                SELECT
                    strftime('%Y-%m-%d %H:%M:00', time) as bucket,
                    AVG(value) as avg_value,
                    MIN(value) as min_value,
                    MAX(value) as max_value,
                    COUNT(*) as sample_count
                FROM historian_samples
                WHERE tag_id = ? AND time >= ? AND time <= ?
                GROUP BY bucket
                ORDER BY bucket ASC
            """, (tag_id, start_time.isoformat(), end_time.isoformat()))
            return [dict(row) for row in cursor.fetchall()]

    def get_latest(self, tag_id: int) -> dict[str, Any] | None:
        """Get latest value for a tag"""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT time, value, quality
                FROM historian_samples
                WHERE tag_id = ?
                ORDER BY time DESC
                LIMIT 1
            """, (tag_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def purge_old_data(self, retention_days: int) -> int:
        """Purge old data"""
        cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM historian_samples WHERE time < ?", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def get_statistics(self, tag_id: int | None = None) -> dict[str, Any]:
        """Get historian statistics"""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            if tag_id:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_samples,
                        MIN(time) as oldest_sample,
                        MAX(time) as newest_sample
                    FROM historian_samples
                    WHERE tag_id = ?
                """, (tag_id,))
            else:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_samples,
                        COUNT(DISTINCT tag_id) as total_tags,
                        MIN(time) as oldest_sample,
                        MAX(time) as newest_sample
                    FROM historian_samples
                """)
            row = cursor.fetchone()
            stats = dict(row) if row else {}
            # Add file size
            if os.path.exists(self.db_path):
                stats['storage_size'] = f"{os.path.getsize(self.db_path) / 1024 / 1024:.2f} MB"
            return stats


# Global historian instance
_historian: HistorianBackend | None = None


def get_historian() -> HistorianBackend:
    """Get the historian backend instance"""
    global _historian
    if _historian is None:
        if TIMESCALE_AVAILABLE:
            try:
                _historian = TimescaleBackend()
                _historian.init_schema()
            except Exception as e:
                logger.error(f"Failed to initialize TimescaleDB: {e}, falling back to SQLite")
                _historian = SQLiteBackend()
                _historian.init_schema()
        else:
            _historian = SQLiteBackend()
            _historian.init_schema()
    return _historian


# Convenience functions that use the global historian

def record_sample(tag_id: int, timestamp: datetime, value: float, quality: int = 192):
    """Record a sample to the historian"""
    get_historian().record_sample(tag_id, timestamp, value, quality)


def record_samples_batch(samples: list[tuple[int, datetime, float, int]]):
    """Record multiple samples efficiently"""
    get_historian().record_samples_batch(samples)


def query_raw(tag_id: int, start_time: datetime, end_time: datetime,
              limit: int = 10000) -> list[dict[str, Any]]:
    """Query raw samples"""
    return get_historian().query_raw(tag_id, start_time, end_time, limit)


def query_aggregate(tag_id: int, start_time: datetime, end_time: datetime,
                    interval_seconds: int = 60) -> list[dict[str, Any]]:
    """Query aggregated data"""
    return get_historian().query_aggregate(tag_id, start_time, end_time, interval_seconds)


def get_latest(tag_id: int) -> dict[str, Any] | None:
    """Get latest value for a tag"""
    return get_historian().get_latest(tag_id)


def get_statistics(tag_id: int | None = None) -> dict[str, Any]:
    """Get historian statistics"""
    return get_historian().get_statistics(tag_id)


def purge_old_data(retention_days: int = 365) -> int:
    """Purge data older than retention period"""
    return get_historian().purge_old_data(retention_days)
