"""Health check response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LiveResponse(BaseModel):
    """Liveness probe response model."""

    status: Literal["live"] = Field(
        default="live",
        description="Liveness status of the backend process",
    )
    timestamp: datetime = Field(description="UTC timestamp of the probe")


class DependencyStatus(BaseModel):
    """Status details for a specific subsystem dependency."""

    status: Literal["ready", "degraded", "not_ready"] = Field(
        description="Subsystem readiness state",
    )
    details: str | None = Field(default=None, description="Human-readable status summary")


class ReadyResponse(BaseModel):
    """Readiness probe response model."""

    status: Literal["ready", "not_ready"] = Field(description="Overall service readiness")
    timestamp: datetime = Field(description="UTC timestamp of the probe")
    dependencies: dict[str, DependencyStatus] = Field(
        description="Readiness state of implemented dependencies",
    )
