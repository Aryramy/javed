"""System status and latency measurement endpoints."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from javed.schemas.system import PingResponse, SystemStatusResponse
from javed.version import __version__

router = APIRouter(tags=["System"])


@router.get("/system/status", response_model=SystemStatusResponse, summary="Get Safe System Status")
async def get_system_status(request: Request) -> SystemStatusResponse:
    """Return safe metadata about the running backend, version, uptime, and capabilities."""
    app_state = request.app.state
    startup_time = getattr(app_state, "startup_time", time.time())
    uptime = max(0.0, time.time() - startup_time)

    ws_manager = getattr(app_state, "ws_manager", None)
    active_connections = ws_manager.get_active_count() if ws_manager else 0

    settings = getattr(app_state, "settings", None)
    env = settings.env if settings else "development"

    return SystemStatusResponse(
        app_name="Javed — New JARVIS",
        backend_version=__version__,
        api_version="v1",
        environment=env,
        server_time=datetime.now(UTC),
        uptime_seconds=round(uptime, 2),
        active_ws_connections=active_connections,
        capabilities={
            "rest_api": True,
            "websocket": True,
            "sse": True,
            "ai_chat": False,
            "tool_execution": False,
            "browser_automation": False,
            "document_extraction": False,
            "persistent_memory": False,
            "voice_multilingual": False,
        },
    )


@router.get("/ping", response_model=PingResponse, summary="Round-Trip Latency Ping")
async def ping(echo: str | None = None) -> PingResponse:
    """Acknowledge a latency ping with the current UTC timestamp."""
    return PingResponse(
        message="pong",
        timestamp=datetime.now(UTC),
        echo=echo,
    )
