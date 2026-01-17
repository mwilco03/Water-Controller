"""
Water Treatment Controller - Prometheus Metrics Endpoint
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Exposes system metrics in Prometheus format for monitoring.

Metrics exposed:
- wtc_api_requests_total: Total API requests by endpoint and status
- wtc_api_request_duration_seconds: Request latency histogram
- wtc_rtu_connection_state: RTU connection states
- wtc_sensor_value: Current sensor values
- wtc_alarm_active: Active alarm count by severity
- wtc_cache_hits_total: Cache hit/miss statistics
- wtc_modbus_requests_total: Modbus operation counts
- wtc_websocket_connections: Active WebSocket connections

Access at: GET /api/v1/metrics
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Response
from starlette.requests import Request

from ...core.logging import get_logger
from ...services.cache_service import get_cache

logger = get_logger(__name__)

router = APIRouter(tags=["metrics"])


@dataclass
class MetricsCollector:
    """Collects and formats Prometheus metrics."""

    # Counters
    requests_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    request_errors_total: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    modbus_operations: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Gauges
    websocket_connections: int = 0
    active_rtus: int = 0
    connected_rtus: int = 0

    # Histograms (simplified - just store recent values)
    request_durations: list[tuple[str, float]] = field(default_factory=list)
    _duration_max_samples: int = 1000

    def record_request(self, path: str, status_code: int, duration_ms: float) -> None:
        """Record an API request."""
        # Normalize path (remove IDs)
        normalized = self._normalize_path(path)
        key = f'{normalized}:{status_code // 100}xx'

        self.requests_total[key] += 1

        if status_code >= 400:
            self.request_errors_total[normalized] += 1

        # Store duration sample
        self.request_durations.append((normalized, duration_ms / 1000))
        if len(self.request_durations) > self._duration_max_samples:
            self.request_durations.pop(0)

    def record_modbus_operation(self, operation: str, success: bool) -> None:
        """Record a Modbus operation."""
        status = "success" if success else "error"
        self.modbus_operations[f"{operation}:{status}"] += 1

    def _normalize_path(self, path: str) -> str:
        """Normalize path by replacing dynamic segments."""
        parts = path.split('/')
        normalized = []
        for i, part in enumerate(parts):
            # Replace likely IDs with placeholder
            if part and (
                part.isdigit() or
                (len(part) > 8 and '-' in part) or  # UUIDs
                (i > 0 and parts[i-1] in ('rtus', 'alarms', 'users', 'pid'))
            ):
                normalized.append('{id}')
            else:
                normalized.append(part)
        return '/'.join(normalized)

    def get_duration_buckets(self, path: str = None) -> dict[str, int]:
        """Get request duration histogram buckets."""
        buckets = {
            "0.01": 0,   # 10ms
            "0.05": 0,   # 50ms
            "0.1": 0,    # 100ms
            "0.25": 0,   # 250ms
            "0.5": 0,    # 500ms
            "1.0": 0,    # 1s
            "2.5": 0,    # 2.5s
            "5.0": 0,    # 5s
            "10.0": 0,   # 10s
            "+Inf": 0,
        }

        for recorded_path, duration in self.request_durations:
            if path and recorded_path != path:
                continue

            for bucket_le in sorted([float(b) for b in buckets.keys() if b != "+Inf"]):
                if duration <= bucket_le:
                    buckets[str(bucket_le)] += 1
            buckets["+Inf"] += 1

        return buckets


# Global metrics collector
_metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the metrics collector singleton."""
    return _metrics


def format_prometheus_metrics() -> str:
    """Format all metrics in Prometheus exposition format."""
    lines = []

    # Helper to add metric with HELP and TYPE
    def add_metric(name: str, type_: str, help_: str, values: list[tuple[dict, float | int]]):
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {type_}")
        for labels, value in values:
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")

    # === API Request Metrics ===
    request_values = []
    for key, count in _metrics.requests_total.items():
        path, status = key.rsplit(':', 1)
        request_values.append(({"path": path, "status": status}, count))

    if request_values:
        add_metric(
            "wtc_api_requests_total",
            "counter",
            "Total API requests by path and status code class",
            request_values
        )

    # Request errors
    error_values = [({"path": path}, count) for path, count in _metrics.request_errors_total.items()]
    if error_values:
        add_metric(
            "wtc_api_request_errors_total",
            "counter",
            "Total API request errors by path",
            error_values
        )

    # === RTU Metrics ===
    try:
        from ...services.profinet_client import get_profinet_client
        profinet = get_profinet_client()

        if profinet.is_connected():
            rtus = profinet.get_rtus()
            add_metric(
                "wtc_rtus_total",
                "gauge",
                "Total number of configured RTUs",
                [({}, len(rtus))]
            )

            # Connection states
            state_counts = defaultdict(int)
            for rtu in rtus:
                state = rtu.get("connection_state", "UNKNOWN")
                state_counts[state] += 1

            state_values = [({"state": state}, count) for state, count in state_counts.items()]
            if state_values:
                add_metric(
                    "wtc_rtu_connection_state",
                    "gauge",
                    "Number of RTUs by connection state",
                    state_values
                )

            # Sensor values (sample - first 10 sensors per RTU)
            sensor_values = []
            for rtu in rtus[:5]:  # Limit to first 5 RTUs
                rtu_name = rtu.get("station_name", "unknown")
                sensors = rtu.get("sensors", [])[:10]
                for sensor in sensors:
                    if sensor.get("status") == "good":
                        sensor_values.append((
                            {"rtu": rtu_name, "slot": str(sensor.get("slot", 0))},
                            sensor.get("value", 0)
                        ))

            if sensor_values:
                add_metric(
                    "wtc_sensor_value",
                    "gauge",
                    "Current sensor values by RTU and slot",
                    sensor_values
                )
    except Exception as e:
        logger.debug(f"Could not collect RTU metrics: {e}")

    # === Alarm Metrics ===
    try:
        from ...services.profinet_client import get_profinet_client
        profinet = get_profinet_client()

        if profinet.is_connected():
            alarms = profinet.get_alarms()
            severity_counts = defaultdict(int)

            for alarm in alarms:
                if alarm.get("state") in ("ACTIVE_UNACK", "ACTIVE_ACK"):
                    severity = alarm.get("severity", "UNKNOWN")
                    severity_counts[severity] += 1

            alarm_values = [({"severity": sev}, count) for sev, count in severity_counts.items()]
            if alarm_values:
                add_metric(
                    "wtc_alarms_active",
                    "gauge",
                    "Number of active alarms by severity",
                    alarm_values
                )
            else:
                add_metric(
                    "wtc_alarms_active",
                    "gauge",
                    "Number of active alarms by severity",
                    [({}, 0)]
                )
    except Exception as e:
        logger.debug(f"Could not collect alarm metrics: {e}")

    # === Cache Metrics ===
    try:
        cache = get_cache()
        stats = cache.get_stats()

        add_metric(
            "wtc_cache_entries",
            "gauge",
            "Number of entries in the cache",
            [({}, stats["entries"])]
        )

        add_metric(
            "wtc_cache_hits_total",
            "counter",
            "Total cache hits",
            [({}, stats["hits"])]
        )

        add_metric(
            "wtc_cache_misses_total",
            "counter",
            "Total cache misses",
            [({}, stats["misses"])]
        )

        add_metric(
            "wtc_cache_stale_hits_total",
            "counter",
            "Total stale cache hits",
            [({}, stats["stale_hits"])]
        )

        add_metric(
            "wtc_cache_hit_rate",
            "gauge",
            "Cache hit rate percentage",
            [({}, stats["hit_rate_percent"])]
        )
    except Exception as e:
        logger.debug(f"Could not collect cache metrics: {e}")

    # === Modbus Metrics ===
    modbus_values = []
    for key, count in _metrics.modbus_operations.items():
        operation, status = key.rsplit(':', 1)
        modbus_values.append(({"operation": operation, "status": status}, count))

    if modbus_values:
        add_metric(
            "wtc_modbus_operations_total",
            "counter",
            "Total Modbus operations by type and status",
            modbus_values
        )

    # === WebSocket Metrics ===
    try:
        from ..websocket import manager
        add_metric(
            "wtc_websocket_connections",
            "gauge",
            "Number of active WebSocket connections",
            [({}, manager.connection_count)]
        )
    except Exception as e:
        logger.debug(f"Could not collect WebSocket metrics: {e}")

    # === System Info ===
    add_metric(
        "wtc_info",
        "gauge",
        "Water Treatment Controller version info",
        [({"version": "2.0.0"}, 1)]
    )

    # Add timestamp
    add_metric(
        "wtc_last_scrape_timestamp",
        "gauge",
        "Timestamp of last metrics scrape",
        [({}, time.time())]
    )

    return "\n".join(lines) + "\n"


@router.get("/metrics")
async def get_metrics(request: Request) -> Response:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    Can be scraped by Prometheus server.

    Example prometheus.yml configuration:
    ```yaml
    scrape_configs:
      - job_name: 'water-controller'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: /api/v1/metrics
        scrape_interval: 15s
    ```
    """
    # Check if metrics are enabled
    if os.environ.get("WTC_METRICS_ENABLED", "true").lower() != "true":
        return Response(
            content="Metrics disabled",
            status_code=503,
            media_type="text/plain"
        )

    try:
        content = format_prometheus_metrics()
        return Response(
            content=content,
            media_type="text/plain; version=0.0.4; charset=utf-8"
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return Response(
            content=f"# Error generating metrics: {e}\n",
            status_code=500,
            media_type="text/plain"
        )


@router.get("/metrics/json")
async def get_metrics_json() -> dict[str, Any]:
    """
    Get metrics in JSON format (for debugging/dashboards).

    Returns structured metrics data instead of Prometheus format.
    """
    result = {
        "timestamp": time.time(),
        "api": {
            "requests_total": dict(_metrics.requests_total),
            "errors_total": dict(_metrics.request_errors_total),
        },
        "modbus": {
            "operations": dict(_metrics.modbus_operations),
        },
    }

    # Add cache stats
    try:
        cache = get_cache()
        result["cache"] = cache.get_stats()
    except Exception as e:
        logger.debug(f"Could not collect cache metrics: {e}")
        result["cache"] = {"error": str(e)}

    # Add RTU stats
    try:
        from ...services.profinet_client import get_profinet_client
        profinet = get_profinet_client()
        if profinet.is_connected():
            status = profinet.get_status()
            result["profinet"] = {
                "connected": True,
                "controller_running": status.get("controller_running", False),
                "total_rtus": status.get("total_rtus", 0),
                "connected_rtus": status.get("connected_rtus", 0),
                "active_alarms": status.get("active_alarms", 0),
            }
        else:
            result["profinet"] = {"connected": False, "reason": "not connected"}
    except ImportError as e:
        logger.debug(f"PROFINET client not available: {e}")
        result["profinet"] = {"connected": False, "reason": "module not available"}
    except Exception as e:
        logger.warning(f"PROFINET status check failed: {e}")
        result["profinet"] = {"connected": False, "reason": f"error: {e}"}

    # Add WebSocket stats
    try:
        from ..websocket import manager
        result["websocket"] = {
            "connections": manager.connection_count,
        }
    except ImportError as e:
        logger.debug(f"WebSocket manager not available: {e}")
    except Exception as e:
        logger.debug(f"Could not collect WebSocket metrics: {e}")

    return result
