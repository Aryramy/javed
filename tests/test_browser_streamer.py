"""Unit and integration tests for the browser viewport frame streamer and WebSocket gateway.

Verifies:
1. Frame capture, base64 JPEG encoding, and EventEnvelope payload structure.
2. Auto-pause behavior when 0 subscribers are connected (zero-idle waste).
3. Throttled frame broadcasting to subscriber callbacks.
4. FastAPI WebSocket endpoint (/api/v1/ws/browser and /ws/browser) handshake and message routing.
5. Unauthorized origin rejection with code 1008.
6. Clean teardown and disconnection handling with zero lingering tasks.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from javed.browser.engine import BrowserEngineManager
from javed.browser.streamer import BrowserFrameStreamer
from javed.main import app
from javed.schemas.events import EventEnvelope


@pytest.mark.asyncio
async def test_streamer_direct_frame_capture() -> None:
    """Verify single frame capture produces valid JPEG Base64 EventEnvelope."""
    engine = BrowserEngineManager(headless=True)
    streamer = BrowserFrameStreamer(interval_seconds=0.2, quality=50)

    try:
        await engine.initialize()
        ctx = await engine.create_ephemeral_context()
        page = await ctx.new_page()
        await page.set_content(
            "<html><head><title>Streamer Title</title></head>"
            "<body><h1>Viewport Test</h1></body></html>"
        )

        streamer.attach_page(page)
        assert streamer.has_page is True

        envelope = await streamer.capture_frame()
        assert envelope is not None
        assert envelope.type == "viewport_frame"
        assert envelope.payload["title"] == "Streamer Title"
        assert envelope.payload["format"] == "jpeg"
        assert envelope.payload["frame_number"] == 1
        assert envelope.payload["image"].startswith("data:image/jpeg;base64,")
        assert envelope.payload["size_bytes"] > 0
        assert envelope.payload["viewport"] == {"width": 1280, "height": 720}
    finally:
        await streamer.stop()
        await engine.close()

    assert streamer.has_page is False
    assert streamer.is_running is False


@pytest.mark.asyncio
async def test_streamer_auto_pause_and_subscriber_lifecycle() -> None:
    """Verify capture loop automatically pauses when no subscribers are active."""
    engine = BrowserEngineManager(headless=True)
    streamer = BrowserFrameStreamer(interval_seconds=0.1, quality=40)

    try:
        await engine.initialize()
        ctx = await engine.create_ephemeral_context()
        page = await ctx.new_page()
        await page.set_content("<html><body><h1>Idle Pause Test</h1></body></html>")

        # 1. Page attached, but 0 subscribers -> must remain paused
        streamer.attach_page(page)
        assert streamer.has_page is True
        assert streamer.subscriber_count == 0
        assert streamer.is_running is False

        # 2. Add subscriber -> capture loop must automatically start
        received: list[EventEnvelope] = []

        async def _sub(env: EventEnvelope) -> None:
            received.append(env)

        streamer.add_subscriber(_sub)
        assert streamer.subscriber_count == 1
        assert streamer.is_running is True

        # Wait briefly for a frame to be captured and dispatched
        await asyncio.sleep(0.25)
        assert len(received) >= 1
        assert received[0].type == "viewport_frame"

        # 3. Remove subscriber -> capture loop must automatically pause
        streamer.remove_subscriber(_sub)
        assert streamer.subscriber_count == 0
        assert streamer.is_running is False
    finally:
        await streamer.stop()
        await engine.close()

    assert streamer.is_running is False


def test_browser_websocket_endpoint_handshake_and_controls() -> None:
    """Verify WebSocket connection, handshake, ping/pong, and status query."""
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws/browser") as ws:
            # 1. Consume connection_established handshake
            handshake = ws.receive_json()
            assert handshake["type"] == "connection_established"
            assert handshake["payload"]["stream"] == "browser_viewport"
            assert "client_id" in handshake["payload"]
            assert "fps_target" in handshake["payload"]

            # 2. Test ping / pong control
            ping_msg = {
                "type": "ping",
                "correlation_id": "test-stream-ping-101",
            }
            ws.send_json(ping_msg)
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert pong["correlation_id"] == "test-stream-ping-101"

            # 3. Test status query
            status_msg = {"type": "status", "correlation_id": "status-req-1"}
            ws.send_json(status_msg)
            status_res = ws.receive_json()
            assert status_res["type"] == "browser_status"
            assert "is_running" in status_res["payload"]
            assert "subscriber_count" in status_res["payload"]


def test_browser_websocket_root_alias_endpoint() -> None:
    """Verify the root-level /ws/browser alias connects and handshakes identically."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/browser") as ws:
            handshake = ws.receive_json()
            assert handshake["type"] == "connection_established"
            assert handshake["payload"]["stream"] == "browser_viewport"


def test_browser_websocket_origin_enforcement() -> None:
    """Verify unauthorized WebSocket origin header is rejected with policy violation (1008)."""
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/v1/ws/browser",
                headers={"Origin": "https://untrusted-external-site.malicious.com"},
            ):
                pass
        assert exc_info.value.code == 1008
