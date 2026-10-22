import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env if present
load_dotenv()


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

    # OpenRouter LLM Settings
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API Key",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API Base URL",
    )
    openrouter_default_model: str = Field(
        default="openrouter/auto",
        description="Default LLM model identifier",
    )
    openrouter_daily_budget_usd: float | None = Field(
        default=None,
        description="Optional application-side daily LLM spend limit in USD (None if uncapped)",
    )
    openrouter_timeout_seconds: float = Field(
        default=60.0,
        description="Timeout for upstream LLM inference requests in seconds",
    )
    openrouter_auto_router_cost_tier: str = Field(
        default="low",
        description="Default cost tier for openrouter/auto (low, medium, high, xhigh, max)",
    )
    app_name: str = Field(
        default="Javed Control Center",
        description="Application title for OpenRouter analytics",
    )
    app_url: str = Field(
        default="http://localhost:5173",
        description="Application origin for OpenRouter analytics",
    )


def get_settings() -> Settings:
    """Load settings from environment variables with safe defaults."""
    allowed_origins_env = os.getenv("JAVED_ALLOWED_ORIGINS")
    allowed_origins = (
        [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        if allowed_origins_env
        else None
    )

    daily_budget_env = os.getenv("OPENROUTER_DAILY_BUDGET_USD")
    daily_budget = float(daily_budget_env) if daily_budget_env else None

    kwargs = {
        "env": os.getenv("JAVED_ENV", "development"),
        "host": os.getenv("JAVED_HOST", "127.0.0.1"),
        "port": int(os.getenv("JAVED_PORT", "8000")),
        "log_level": os.getenv("JAVED_LOG_LEVEL", "INFO"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
        "openrouter_base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "openrouter_default_model": os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/auto"),
        "openrouter_daily_budget_usd": daily_budget,
        "openrouter_timeout_seconds": float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60.0")),
        "openrouter_auto_router_cost_tier": os.getenv("OPENROUTER_AUTO_ROUTER_COST_TIER", "low"),
    }
    if allowed_origins:
        kwargs["allowed_origins"] = allowed_origins

    return Settings(**kwargs)

