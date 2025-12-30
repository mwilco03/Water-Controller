"""
Water Treatment Controller - WebSocket Handlers
Copyright (C) 2024
SPDX-License-Identifier: GPL-3.0-or-later

Real-time data streaming via WebSocket.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections with channel-based subscriptions."""

    def __init__(self):
        self._connections: dict[WebSocket, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = {
                "channels": set(),
                "rtus": set(),  # Empty means all RTUs
                "connected_at": datetime.now(UTC),
                "last_activity": datetime.now(UTC),
            }
        logger.info(f"WebSocket connected. Total connections: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self._connections:
                del self._connections[websocket]
        logger.info(f"WebSocket disconnected. Total connections: {len(self._connections)}")

    async def subscribe(
        self,
        websocket: WebSocket,
        channels: list[str],
        rtus: list[str] | None = None
    ) -> None:
        """Subscribe a connection to specific channels."""
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket]["channels"] = set(channels)
                if rtus:
                    self._connections[websocket]["rtus"] = set(rtus)
                else:
                    self._connections[websocket]["rtus"] = set()  # All RTUs

    async def broadcast(
        self,
        channel: str,
        data: dict[str, Any],
        rtu: str | None = None
    ) -> None:
        """Broadcast message to all subscribed connections."""
        message = {
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if rtu:
            message["rtu"] = rtu

        dead_connections = []

        async with self._lock:
            connections = list(self._connections.items())

        for websocket, info in connections:
            # Check if subscribed to this channel
            if channel not in info["channels"]:
                continue

            # Check RTU filter
            rtu_filter = info["rtus"]
            if rtu and rtu_filter and rtu not in rtu_filter:
                continue

            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for ws in dead_connections:
                    self._connections.pop(ws, None)
            logger.info(f"Removed {len(dead_connections)} dead WebSocket connections")

    @property
    def connection_count(self) -> int:
        """Get current connection count."""
        return len(self._connections)


# Global connection manager
manager = ConnectionManager()


class SubscriptionMessage(BaseModel):
    """Subscription request from client."""

    action: str  # "subscribe" or "unsubscribe"
    channels: list[str]  # sensors, controls, alarms, rtu_state
    rtus: list[str] | None = None  # Optional filter by RTU names


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket endpoint for real-time data streaming.

    Protocol:
    1. Client connects
    2. Client sends subscription message:
       {
         "action": "subscribe",
         "channels": ["sensors", "controls", "alarms", "rtu_state"],
         "rtus": ["pump-station-1"]  // optional filter
       }
    3. Server sends updates matching subscription:
       {
         "channel": "sensors",
         "rtu": "pump-station-1",
         "data": [...]
       }
    4. Heartbeat ping/pong every 30 seconds
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                # Heartbeat
                await websocket.send_json({"type": "pong"})
                continue

            action = data.get("action")

            if action == "subscribe":
                channels = data.get("channels", [])
                rtus = data.get("rtus")
                await manager.subscribe(websocket, channels, rtus)
                await websocket.send_json({
                    "type": "subscribed",
                    "channels": channels,
                    "rtus": rtus or "all",
                })

            elif action == "unsubscribe":
                await manager.subscribe(websocket, [], None)
                await websocket.send_json({
                    "type": "unsubscribed",
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


# Helper functions for broadcasting events


async def broadcast_sensor_update(rtu: str, sensors: list[dict[str, Any]]) -> None:
    """Broadcast sensor value updates."""
    await manager.broadcast("sensors", sensors, rtu)


async def broadcast_control_update(rtu: str, controls: list[dict[str, Any]]) -> None:
    """Broadcast control state updates."""
    await manager.broadcast("controls", controls, rtu)


async def broadcast_alarm(action: str, alarm: dict[str, Any]) -> None:
    """Broadcast alarm event."""
    await manager.broadcast("alarms", {
        "action": action,  # activated, acknowledged, cleared
        "alarm": alarm,
    })


async def broadcast_rtu_state_change(
    rtu: str,
    previous_state: str,
    new_state: str
) -> None:
    """Broadcast RTU state change."""
    await manager.broadcast("rtu_state", {
        "previous_state": previous_state,
        "new_state": new_state,
    }, rtu)
