"""WebSocket connection manager and event routing."""

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from javed.config import Settings
from javed.schemas.events import EventEnvelope

logger = logging.getLogger("javed.transport.websocket")


class WebSocketManager:
    """Manages active WebSocket sessions with heartbeat and connection lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.active_connections: dict[str, WebSocket] = {}
        self.connection_metadata: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str | None = None) -> str:
        """Accept an incoming WebSocket connection and register client."""
        await websocket.accept()
        cid = client_id or str(uuid.uuid4())

        async with self._lock:
            self.active_connections[cid] = websocket
            self.connection_metadata[cid] = {
                "connected_at": datetime.now(UTC).isoformat(),
                "last_heartbeat": datetime.now(UTC).isoformat(),
                "client_ip": websocket.client.host if websocket.client else "unknown",
            }

        logger.info(
            "WebSocket connected: %s (active: %d)",
            cid,
            len(self.active_connections),
        )

        # Send welcome/handshake event
        welcome = EventEnvelope(
            type="connection_established",
            correlation_id=None,
            payload={
                "client_id": cid,
                "server_time": datetime.now(UTC).isoformat(),
                "heartbeat_interval_seconds": self.settings.ws_heartbeat_interval_seconds,
            },
        )
        await self.send_personal_envelope(cid, welcome)
        return cid

    async def disconnect(self, client_id: str) -> None:
        """Unregister a disconnected client safely."""
        async with self._lock:
            self.active_connections.pop(client_id, None)
            self.connection_metadata.pop(client_id, None)
        logger.info(
            "WebSocket disconnected: %s (active: %d)",
            client_id,
            len(self.active_connections),
        )

    async def send_personal_envelope(self, client_id: str, envelope: EventEnvelope) -> None:
        """Send a typed EventEnvelope to a specific client."""
        ws = self.active_connections.get(client_id)
        if ws is not None:
            try:
                await ws.send_text(envelope.model_dump_json())
            except Exception as e:
                logger.warning("Failed to send to client %s: %s", client_id, e)

    async def broadcast_envelope(self, envelope: EventEnvelope) -> None:
        """Broadcast an EventEnvelope to all connected clients."""
        if not self.active_connections:
            return

        payload_json = envelope.model_dump_json()
        tasks = []
        for cid, ws in list(self.active_connections.items()):
            tasks.append(self._safe_send_text(cid, ws, payload_json))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send_text(self, client_id: str, ws: WebSocket, text: str) -> None:
        try:
            await ws.send_text(text)
        except Exception as e:
            logger.warning("Error broadcasting to %s: %s", client_id, e)

    async def close_all(self, code: int = 1001, reason: str = "Server shutdown") -> None:
        """Gracefully close all open WebSocket connections."""
        async with self._lock:
            clients = list(self.active_connections.items())
            self.active_connections.clear()
            self.connection_metadata.clear()

        for cid, ws in clients:
            try:
                await ws.close(code=code, reason=reason)
            except Exception as e:
                logger.debug("Error closing connection %s: %s", cid, e)
        logger.info("All WebSocket connections closed")

    def get_active_count(self) -> int:
        """Return the number of active connections."""
        return len(self.active_connections)

    def is_origin_allowed(self, origin: str | None) -> bool:
        """Verify whether an Origin header is permitted."""
        if not origin:
            # Allow non-browser direct clients or tests if configured
            return True
        return origin.rstrip("/") in [o.rstrip("/") for o in self.settings.allowed_origins]

    async def handle_message(self, client_id: str, raw_text: str) -> None:
        """Process an incoming raw WebSocket message frame."""
        # 1. Enforce max message size
        max_bytes = self.settings.ws_max_message_bytes
        if len(raw_text.encode("utf-8")) > max_bytes:
            error_env = EventEnvelope(
                type="error",
                payload={
                    "code": "MESSAGE_TOO_LARGE",
                    "message": f"Message exceeds maximum size of {max_bytes} bytes",
                },
            )
            await self.send_personal_envelope(client_id, error_env)
            return

        # 2. Parse JSON
        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError("Message must be a JSON object")
        except Exception as e:
            error_env = EventEnvelope(
                type="error",
                payload={"code": "INVALID_JSON", "message": f"Malformed JSON: {e}"},
            )
            await self.send_personal_envelope(client_id, error_env)
            return

        msg_type = data.get("type")
        correlation_id = data.get("correlation_id")
        payload = data.get("payload", {})

        # Update last heartbeat time
        if client_id in self.connection_metadata:
            self.connection_metadata[client_id]["last_heartbeat"] = datetime.now(UTC).isoformat()

        # 3. Route recognized message types
        if msg_type == "ping":
            pong_env = EventEnvelope(
                type="pong",
                correlation_id=correlation_id,
                payload={
                    "client_time": payload.get("client_time"),
                    "server_time": datetime.now(UTC).isoformat(),
                },
            )
            await self.send_personal_envelope(client_id, pong_env)

        elif msg_type == "heartbeat":
            ack_env = EventEnvelope(
                type="heartbeat_ack",
                correlation_id=correlation_id,
                payload={
                    "client_time": payload.get("client_time"),
                    "server_time": datetime.now(UTC).isoformat(),
                },
            )
            await self.send_personal_envelope(client_id, ack_env)

        elif msg_type == "status_request":
            from javed.version import __version__

            status_env = EventEnvelope(
                type="status_response",
                correlation_id=correlation_id,
                payload={
                    "backend_version": __version__,
                    "active_connections": self.get_active_count(),
                    "server_time": datetime.now(UTC).isoformat(),
                },
            )
            await self.send_personal_envelope(client_id, status_env)

        elif msg_type == "echo":
            echo_env = EventEnvelope(
                type="echo_response",
                correlation_id=correlation_id,
                payload=payload,
            )
            await self.send_personal_envelope(client_id, echo_env)

        else:
            error_env = EventEnvelope(
                type="error",
                correlation_id=correlation_id,
                payload={
                    "code": "UNKNOWN_MESSAGE_TYPE",
                    "message": f"Message type '{msg_type}' is not supported",
                },
            )
            await self.send_personal_envelope(client_id, error_env)
