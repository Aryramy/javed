"""WebSocket gateway for real-time browser preview frame streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.status import WS_1008_POLICY_VIOLATION

from javed.browser.streamer import BrowserFrameStreamer
from javed.config import Settings
from javed.schemas.events import EventEnvelope

logger = logging.getLogger("javed.api.v1.browser_ws")
router = APIRouter(tags=["Browser WebSocket"])


class BrowserWebSocketManager:
    """Manages active WebSocket subscribers to the live browser viewport stream."""

    def __init__(self, settings: Settings, streamer: BrowserFrameStreamer) -> None:
        self.settings = settings
        self.streamer = streamer
        self.active_connections: dict[str, WebSocket] = {}
        self._subscribers: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def is_origin_allowed(self, origin: str | None) -> bool:
        """Verify whether an incoming WebSocket Origin is permitted."""
        if not origin:
            return True
        allowed = [o.rstrip("/") for o in self.settings.allowed_origins]
        return origin.rstrip("/") in allowed

    async def connect(self, websocket: WebSocket, client_id: str | None = None) -> str:
        """Accept WebSocket connection, register client, and bind frame subscription."""
        await websocket.accept()
        cid = client_id or str(uuid.uuid4())

        async with self._lock:
            self.active_connections[cid] = websocket

        # Create frame subscriber callback for this client
        async def _client_subscriber(envelope: EventEnvelope) -> None:
            await self._safe_send_envelope(cid, envelope)

        self._subscribers[cid] = _client_subscriber
        self.streamer.add_subscriber(_client_subscriber)

        logger.info(
            "Browser WebSocket client connected: %s (active subscribers: %d)",
            cid,
            len(self.active_connections),
        )

        # Send welcome handshake event
        welcome = EventEnvelope(
            type="connection_established",
            correlation_id=None,
            timestamp=datetime.now(UTC),
            payload={
                "client_id": cid,
                "server_time": datetime.now(UTC).isoformat(),
                "stream": "browser_viewport",
                "fps_target": round(1.0 / self.streamer.interval_seconds, 1),
                "has_active_page": self.streamer.has_page,
            },
        )
        await self._safe_send_envelope(cid, welcome)

        # If a page is already active, send an immediate snapshot
        if self.streamer.has_page:
            initial_frame = await self.streamer.capture_frame()
            if initial_frame:
                await self._safe_send_envelope(cid, initial_frame)

        return cid

    async def disconnect(self, client_id: str) -> None:
        """Unregister client and detach frame subscriber."""
        async with self._lock:
            self.active_connections.pop(client_id, None)
            cb = self._subscribers.pop(client_id, None)

        if cb is not None:
            self.streamer.remove_subscriber(cb)

        logger.info(
            "Browser WebSocket client disconnected: %s (remaining: %d)",
            client_id,
            len(self.active_connections),
        )

    async def _safe_send_envelope(self, client_id: str, envelope: EventEnvelope) -> None:
        ws = self.active_connections.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_text(envelope.model_dump_json())
        except Exception as exc:
            logger.debug("Failed to send frame to client %s: %s", client_id, exc)

    async def handle_message(self, client_id: str, text: str) -> None:
        """Process incoming client control messages (ping, status, pause, resume)."""
        try:
            data = json.loads(text)
        except Exception:
            return

        msg_type = data.get("type", "").lower()
        correlation_id = data.get("correlation_id")

        if msg_type == "ping":
            pong = EventEnvelope(
                type="pong",
                correlation_id=correlation_id,
                payload={"server_time": datetime.now(UTC).isoformat()},
            )
            await self._safe_send_envelope(client_id, pong)
        elif msg_type == "status":
            status_env = EventEnvelope(
                type="browser_status",
                correlation_id=correlation_id,
                payload={
                    "is_running": self.streamer.is_running,
                    "has_page": self.streamer.has_page,
                    "frame_count": self.streamer.frame_count,
                    "subscriber_count": self.streamer.subscriber_count,
                },
            )
            await self._safe_send_envelope(client_id, status_env)
        elif msg_type in {"pause", "unsubscribe"}:
            cb = self._subscribers.get(client_id)
            if cb:
                self.streamer.remove_subscriber(cb)
        elif msg_type in {"resume", "subscribe"}:
            cb = self._subscribers.get(client_id)
            if cb:
                self.streamer.add_subscriber(cb)

    async def close_all(self, code: int = 1001, reason: str = "Server shutdown") -> None:
        """Cleanly close all active WebSocket connections."""
        async with self._lock:
            clients = list(self.active_connections.items())
            self.active_connections.clear()
            self._subscribers.clear()

        for cid, ws in clients:
            try:
                await ws.close(code=code, reason=reason)
            except Exception as exc:
                logger.debug("Error closing connection %s: %s", cid, exc)

        logger.info("All Browser WebSocket connections closed cleanly")


@router.websocket("/ws/browser")
async def browser_websocket_endpoint(
    websocket: WebSocket,
    client_id: str | None = Query(default=None),
) -> None:
    """Dedicated WebSocket endpoint for live browser preview frame streaming."""
    app_state = websocket.app.state

    # Lazily initialize manager on app.state if not pre-configured
    if not hasattr(app_state, "browser_ws_manager") or app_state.browser_ws_manager is None:
        streamer = getattr(app_state, "browser_streamer", None)
        if streamer is None:
            streamer = BrowserFrameStreamer()
            app_state.browser_streamer = streamer
        settings = getattr(app_state, "settings", Settings())
        app_state.browser_ws_manager = BrowserWebSocketManager(settings, streamer)

    manager: BrowserWebSocketManager = app_state.browser_ws_manager

    # 1. Validate Origin header
    origin = websocket.headers.get("origin")
    if not manager.is_origin_allowed(origin):
        logger.warning("Rejected Browser WebSocket connection from unauthorized origin: %s", origin)
        await websocket.close(code=WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # 2. Accept and register client
    cid = await manager.connect(websocket, client_id=client_id)

    # 3. Message loop
    try:
        while True:
            text_data = await websocket.receive_text()
            await manager.handle_message(cid, text_data)
    except WebSocketDisconnect as disc:
        logger.info("Browser WebSocket client %s disconnected: code %s", cid, disc.code)
    except Exception as exc:
        logger.warning("Error in Browser WebSocket loop for %s: %s", cid, exc)
    finally:
        await manager.disconnect(cid)
