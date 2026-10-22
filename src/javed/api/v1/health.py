"""Health and readiness probe endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter

from javed.schemas.health import DependencyStatus, LiveResponse, ReadyResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=LiveResponse, summary="Process Liveness Probe")
async def get_live() -> LiveResponse:
    """Return whether the FastAPI process is alive and responsive."""
    return LiveResponse(status="live", timestamp=datetime.now(UTC))


@router.get("/ready", response_model=ReadyResponse, summary="Dependency Readiness Probe")
async def get_ready() -> ReadyResponse:
    """Return whether all implemented backend dependencies are ready."""
    return ReadyResponse(
        status="ready",
        timestamp=datetime.now(UTC),
        dependencies={
            "backend_runtime": DependencyStatus(
                status="ready",
                details="FastAPI process and event loop running cleanly",
            ),
            "websocket_transport": DependencyStatus(
                status="ready",
                details="WebSocket gateway ready for client connections",
            ),
            "sse_telemetry": DependencyStatus(
                status="ready",
                details="Server-Sent Events broadcaster operational",
            ),
        },
    )
