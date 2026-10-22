"""Tests for Server-Sent Events (SSE) telemetry stream."""

import json

import pytest
from starlette.testclient import TestClient

from javed.main import app


def test_sse_endpoint_connect() -> None:
    """Test /api/v1/events initiates an SSE stream with an initial sse_connected event."""
    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/events") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            lines = []
            for line in response.iter_lines():
                if line:
                    lines.append(line)
                if line.startswith("data:"):
                    break

            assert any("event: sse_connected" in line for line in lines)
            data_line = next(line for line in lines if line.startswith("data:"))
            payload = json.loads(data_line[len("data:") :].strip())
            assert payload["type"] == "sse_connected"


@pytest.mark.asyncio
async def test_sse_manager_publish() -> None:
    """Test SSEManager publish delivers events to subscribers."""
    sse_manager = app.state.sse_manager
    queue = await sse_manager.subscribe()
    try:
        await sse_manager.publish("test_event", {"metric": "latency", "val": 42})
        msg = await queue.get()
        assert "event: test_event" in msg
        assert '"val":42' in msg or '"val": 42' in msg
    finally:
        await sse_manager.unsubscribe(queue)
