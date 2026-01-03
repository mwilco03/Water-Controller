"""
Water Treatment Controller - Graceful Degradation Cache Service
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Provides cached last-known-good values when upstream systems are unavailable.
Enables graceful degradation instead of complete failure.

Design principles:
- Operators see stale data (with warning) instead of errors
- Cache is updated on every successful read
- Stale thresholds are configurable per data type
- Critical values have shorter stale thresholds

Usage:
    from app.services.cache_service import get_cache, CacheEntry

    # Store value on successful read
    cache = get_cache()
    cache.set("rtu:water-rtu-01:sensor:1", value=25.5, quality="good")

    # Retrieve with fallback to cached value
    entry = cache.get("rtu:water-rtu-01:sensor:1")
    if entry:
        print(f"Value: {entry.value}, Stale: {entry.is_stale}, Age: {entry.age_seconds}s")
"""

import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from threading import Lock
from typing import Any

from ..core.logging import get_logger

logger = get_logger(__name__)


class DataQuality(Enum):
    """Quality indicators for cached data."""
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"
    STALE = "stale"
    NOT_CONNECTED = "not_connected"


@dataclass
class CacheEntry:
    """Cached data entry with quality and timing metadata."""
    key: str
    value: Any
    quality: DataQuality
    timestamp: float  # monotonic time
    wall_clock: datetime  # for display
    source: str = ""  # e.g., "profinet", "modbus", "api"
    metadata: dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Age of the cached value in seconds."""
        return time.monotonic() - self.timestamp

    @property
    def age_ms(self) -> float:
        """Age in milliseconds."""
        return self.age_seconds * 1000

    def is_stale(self, threshold_seconds: float = 30.0) -> bool:
        """Check if value exceeds stale threshold."""
        return self.age_seconds > threshold_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "key": self.key,
            "value": self.value,
            "quality": self.quality.value,
            "age_seconds": round(self.age_seconds, 1),
            "timestamp": self.wall_clock.isoformat(),
            "source": self.source,
            "is_stale": self.is_stale(),
            "metadata": self.metadata,
        }


class CacheConfig:
    """Cache configuration with environment overrides."""

    def __init__(self):
        # Maximum entries before eviction
        self.max_entries = int(os.environ.get("WTC_CACHE_MAX_ENTRIES", "10000"))

        # Default stale threshold (seconds)
        self.default_stale_threshold = float(
            os.environ.get("WTC_CACHE_STALE_THRESHOLD", "30.0")
        )

        # Per-type stale thresholds (critical values have shorter thresholds)
        self.stale_thresholds = {
            "sensor": 30.0,          # 30 seconds for sensor values
            "actuator": 10.0,        # 10 seconds for actuator states
            "alarm": 5.0,            # 5 seconds for alarm states
            "rtu_state": 15.0,       # 15 seconds for RTU connection state
            "setpoint": 60.0,        # 60 seconds for setpoints (less volatile)
            "config": 300.0,         # 5 minutes for configuration data
        }

        # TTL for cache entries (when to evict completely)
        self.entry_ttl = float(os.environ.get("WTC_CACHE_TTL", "3600.0"))  # 1 hour

    def get_stale_threshold(self, data_type: str) -> float:
        """Get stale threshold for data type."""
        return self.stale_thresholds.get(data_type, self.default_stale_threshold)


class GracefulDegradationCache:
    """
    Thread-safe cache for graceful degradation.

    Features:
    - LRU eviction when max entries reached
    - Per-key quality and staleness tracking
    - Automatic TTL-based expiration
    - Statistics for monitoring
    """

    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig()
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # For LRU
        self._lock = Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._stale_hits = 0
        self._evictions = 0

    def set(
        self,
        key: str,
        value: Any,
        quality: str | DataQuality = DataQuality.GOOD,
        source: str = "",
        metadata: dict | None = None
    ) -> None:
        """
        Store or update a cached value.

        Args:
            key: Cache key (e.g., "rtu:station-01:sensor:1")
            value: Value to cache
            quality: Data quality indicator
            source: Data source (e.g., "profinet", "modbus")
            metadata: Additional metadata
        """
        if isinstance(quality, str):
            try:
                quality = DataQuality(quality)
            except ValueError:
                quality = DataQuality.UNCERTAIN

        entry = CacheEntry(
            key=key,
            value=value,
            quality=quality,
            timestamp=time.monotonic(),
            wall_clock=datetime.now(UTC),
            source=source,
            metadata=metadata or {}
        )

        with self._lock:
            # Update access order
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            self._cache[key] = entry

            # Evict if over capacity
            self._evict_if_needed()

    def get(
        self,
        key: str,
        stale_threshold: float | None = None
    ) -> CacheEntry | None:
        """
        Get cached value with staleness check.

        Args:
            key: Cache key
            stale_threshold: Override default stale threshold

        Returns:
            CacheEntry if found (may be stale), None if not found
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            self._hits += 1

            # Update access order (LRU)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            # Check staleness
            threshold = stale_threshold or self.config.default_stale_threshold
            if entry.is_stale(threshold):
                self._stale_hits += 1
                # Update quality to STALE if it was GOOD/UNCERTAIN
                if entry.quality in (DataQuality.GOOD, DataQuality.UNCERTAIN):
                    entry.quality = DataQuality.STALE

            return entry

    def get_or_default(
        self,
        key: str,
        default: Any = None,
        stale_threshold: float | None = None
    ) -> tuple[Any, CacheEntry | None]:
        """
        Get cached value or return default.

        Returns:
            (value, entry) - entry is None if using default
        """
        entry = self.get(key, stale_threshold)
        if entry is not None:
            return entry.value, entry
        return default, None

    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with prefix."""
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if over capacity (must hold lock)."""
        while len(self._cache) > self.config.max_entries:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                if oldest_key in self._cache:
                    del self._cache[oldest_key]
                    self._evictions += 1

    def cleanup_expired(self) -> int:
        """Remove entries that have exceeded TTL."""
        now = time.monotonic()
        removed = 0

        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if (now - entry.timestamp) > self.config.entry_ttl
            ]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                removed += 1

        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired cache entries")

        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            stale_rate = (self._stale_hits / self._hits * 100) if self._hits > 0 else 0

            return {
                "entries": len(self._cache),
                "max_entries": self.config.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "stale_hits": self._stale_hits,
                "evictions": self._evictions,
                "hit_rate_percent": round(hit_rate, 1),
                "stale_rate_percent": round(stale_rate, 1),
            }

    def get_all_for_rtu(self, rtu_name: str) -> list[CacheEntry]:
        """Get all cached entries for an RTU."""
        prefix = f"rtu:{rtu_name}:"
        with self._lock:
            return [
                entry for key, entry in self._cache.items()
                if key.startswith(prefix)
            ]

    def get_stale_entries(self, threshold: float | None = None) -> list[CacheEntry]:
        """Get all stale entries (for diagnostics)."""
        threshold = threshold or self.config.default_stale_threshold
        with self._lock:
            return [
                entry for entry in self._cache.values()
                if entry.is_stale(threshold)
            ]


# Singleton instance
_cache: GracefulDegradationCache | None = None
_cache_lock = Lock()


def get_cache() -> GracefulDegradationCache:
    """Get or create the cache singleton."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = GracefulDegradationCache()
    return _cache


def reset_cache() -> None:
    """Reset the cache singleton (for testing)."""
    global _cache
    with _cache_lock:
        _cache = None


# ============== Helper Functions for Common Patterns ==============


def cache_sensor_value(
    rtu_name: str,
    slot: int,
    value: float,
    quality: str = "good",
    unit: str = ""
) -> None:
    """Cache a sensor value with standard key format."""
    cache = get_cache()
    key = f"rtu:{rtu_name}:sensor:{slot}"
    cache.set(key, value, quality=quality, source="profinet", metadata={"unit": unit})


def get_sensor_value(
    rtu_name: str,
    slot: int,
    default: float | None = None
) -> tuple[float | None, bool, float]:
    """
    Get cached sensor value with staleness info.

    Returns:
        (value, is_stale, age_seconds)
    """
    cache = get_cache()
    key = f"rtu:{rtu_name}:sensor:{slot}"
    entry = cache.get(key, stale_threshold=30.0)

    if entry is None:
        return default, True, 0.0

    return entry.value, entry.is_stale(30.0), entry.age_seconds


def cache_actuator_state(
    rtu_name: str,
    slot: int,
    command: int,
    pwm_duty: int = 0,
    forced: bool = False
) -> None:
    """Cache an actuator state."""
    cache = get_cache()
    key = f"rtu:{rtu_name}:actuator:{slot}"
    cache.set(
        key,
        {"command": command, "pwm_duty": pwm_duty, "forced": forced},
        quality="good",
        source="profinet"
    )


def get_actuator_state(
    rtu_name: str,
    slot: int
) -> tuple[dict | None, bool, float]:
    """
    Get cached actuator state.

    Returns:
        (state_dict, is_stale, age_seconds)
    """
    cache = get_cache()
    key = f"rtu:{rtu_name}:actuator:{slot}"
    entry = cache.get(key, stale_threshold=10.0)

    if entry is None:
        return None, True, 0.0

    return entry.value, entry.is_stale(10.0), entry.age_seconds


def cache_rtu_state(rtu_name: str, state: str, healthy: bool = True) -> None:
    """Cache RTU connection state."""
    cache = get_cache()
    key = f"rtu:{rtu_name}:state"
    cache.set(
        key,
        {"state": state, "healthy": healthy},
        quality="good" if healthy else "uncertain",
        source="profinet"
    )


def get_rtu_state(rtu_name: str) -> tuple[dict | None, bool, float]:
    """Get cached RTU state."""
    cache = get_cache()
    key = f"rtu:{rtu_name}:state"
    entry = cache.get(key, stale_threshold=15.0)

    if entry is None:
        return None, True, 0.0

    return entry.value, entry.is_stale(15.0), entry.age_seconds
