"""Typed event envelope schemas for real-time WebSocket and SSE transports."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Standardized event envelope for client-server real-time communication."""

    type: str = Field(description="Event discriminator type")
    version: str = Field(default="1.0", description="Event contract version")
    correlation_id: str | None = Field(default=None, description="Optional request correlation ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the event",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Event payload data")
