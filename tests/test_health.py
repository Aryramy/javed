"""Tests for health check endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from javed.main import app


@pytest.mark.asyncio
async def test_health_live() -> None:
    """Test the /api/v1/health/live endpoint returns live status."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "live"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_ready() -> None:
    """Test the /api/v1/health/ready endpoint returns dependencies."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "dependencies" in data
        assert "backend_runtime" in data["dependencies"]
        assert data["dependencies"]["backend_runtime"]["status"] == "ready"
