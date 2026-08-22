"""WebSocket connection manager for streaming analysis progress.

Tracks active WebSocket connections and provides helpers to broadcast to all
clients or to send a personal JSON message to a single client.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import WebSocket


class ConnectionManager:
    """Manage a set of live WebSocket connections."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        if websocket not in self.active:
            self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def send_personal_json(self, message: dict, websocket: WebSocket) -> None:
        """Send a JSON message to a single connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)

    async def broadcast_json(self, message: dict) -> None:
        """Send a JSON message to every active connection."""
        # Snapshot so a disconnect during iteration is safe.
        for websocket in list(self.active):
            await self.send_personal_json(message, websocket)

    async def broadcast_text(self, message: str, skip: WebSocket | None = None) -> None:
        """Send a raw text message to every connection except ``skip``."""
        for websocket in list(self.active):
            if websocket is skip:
                continue
            try:
                await websocket.send_text(message)
            except Exception:
                self.disconnect(websocket)


def make_event(type_: str, **fields) -> dict:
    """Build a typed WebSocket event payload."""
    payload: dict = {"type": type_}
    for key, value in fields.items():
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            value = list(value)
        payload[key] = value
    return payload


# Shared manager instance for the analyze WebSocket stream.
manager = ConnectionManager()
