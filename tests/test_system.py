"""Tests for system metadata, latency ping, and root endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from javed.main import app
from javed.version import __version__


@pytest.mark.asyncio
async def test_root_index() -> None:
    """Test the root '/' endpoint returns status and version."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Javed — New JARVIS"
        assert data["version"] == __version__
        assert data["status"] == "online"


@pytest.mark.asyncio
async def test_system_status() -> None:
    """Test the /api/v1/system/status endpoint returns safe metadata."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/status")
        assert response.status_code == 200
        data = response.json()
        assert data["backend_version"] == __version__
        assert data["api_version"] == "v1"
        assert "server_time" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0.0
        assert "capabilities" in data
        assert data["capabilities"]["rest_api"] is True
        assert data["capabilities"]["websocket"] is True
        assert data["capabilities"]["ai_chat"] is False  # Stage boundary respected


@pytest.mark.asyncio
async def test_ping() -> None:
    """Test the /api/v1/ping endpoint for latency testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/ping?echo=test123")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "pong"
        assert data["echo"] == "test123"
        assert "timestamp" in data
