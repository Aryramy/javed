"""Application configuration and settings for Project Javed."""

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime configuration settings."""

    env: str = Field(
        default="development",
        description="Environment: development, test, or production",
    )
    host: str = Field(default="127.0.0.1", description="Host address to bind to")
    port: int = Field(default=8000, description="Port number to bind to")
    log_level: str = Field(default="INFO", description="Logging level")

    # Allowed Origins for CORS and WebSocket connections
    allowed_origins: list[str] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        description="Allowed HTTP and WebSocket origins",
    )

    # WebSocket limits and timeouts
    ws_max_message_bytes: int = Field(
        default=65536,
        description="Max allowed message size in bytes (64KB)",
    )
    ws_heartbeat_interval_seconds: float = Field(
        default=15.0,
        description="Recommended heartbeat interval",
    )
    ws_heartbeat_timeout_seconds: float = Field(
        default=30.0,
        description="Heartbeat timeout threshold",
    )

    # REST limits
    max_request_body_bytes: int = Field(
        default=1048576,
        description="Max request body in bytes (1MB)",
    )


def get_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""
    allowed_origins_env = os.getenv("JAVED_ALLOWED_ORIGINS")
    allowed_origins = (
        [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        if allowed_origins_env
        else None
    )

    kwargs = {
        "env": os.getenv("JAVED_ENV", "development"),
        "host": os.getenv("JAVED_HOST", "127.0.0.1"),
        "port": int(os.getenv("JAVED_PORT", "8000")),
        "log_level": os.getenv("JAVED_LOG_LEVEL", "INFO"),
    }
    if allowed_origins:
        kwargs["allowed_origins"] = allowed_origins

    return Settings(**kwargs)
