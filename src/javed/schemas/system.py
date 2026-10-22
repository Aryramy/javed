"""System status and latency measurement schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SystemStatusResponse(BaseModel):
    """System status metadata response model."""

    app_name: str = Field(default="Javed — New JARVIS", description="Application name")
    backend_version: str = Field(description="Backend semantic version")
    api_version: str = Field(default="v1", description="API contract version")
    environment: str = Field(description="Operating environment")
    server_time: datetime = Field(description="Current UTC timestamp on the server")
    uptime_seconds: float = Field(description="Uptime in seconds since process startup")
    active_ws_connections: int = Field(
        default=0,
        description="Count of currently active WebSocket clients",
    )
    capabilities: dict[str, bool] = Field(description="Explicit map of implemented capabilities")


class PingResponse(BaseModel):
    """Round-trip latency test response model."""

    message: Literal["pong"] = Field(default="pong", description="Ping acknowledgment")
    timestamp: datetime = Field(description="UTC timestamp when ping was received")
    echo: str | None = Field(default=None, description="Optional echoed payload")
