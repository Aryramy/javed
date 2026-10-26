import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

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
    openrouter_system_prompt: str | None = Field(
        default=None,
        description="Optional system prompt override for LLM conversations",
    )
    app_name: str = Field(
        default="Javed Control Center",
        description="Application title for OpenRouter analytics",
    )
    app_url: str = Field(
        default="http://localhost:5173",
        description="Application origin for OpenRouter analytics",
    )

    # Deep Agents & LangGraph Runtime Settings
    agent_checkpoint_db_path: str = Field(
        default="data/checkpoints.db",
        description="Path to SQLite database for LangGraph checkpoints",
    )
    agent_approvals_db_path: str = Field(
        default="data/approvals.db",
        description="Path to SQLite database for durable pending approvals and execution ledger",
    )
    agent_stream_timeout_seconds: float = Field(
        default=120.0,
        description="Timeout for agent stream runs in seconds",
    )
    owner_token: str | None = Field(
        default=None,
        description="Local owner token for privileged administration. None if unset.",
    )

    @model_validator(mode="after")
    def validate_owner_token_security(self) -> "Settings":
        """Reject empty, blank or known weak placeholder owner tokens; enforce in production."""
        if self.owner_token is not None:
            stripped = self.owner_token.strip()
            if not stripped:
                raise ValueError("owner_token cannot be empty or whitespace.")
            if stripped.lower() in FORBIDDEN_OWNER_TOKENS:
                raise ValueError(
                    f"owner_token cannot be a known weak placeholder ('{stripped}'). "
                    "Configure a unique secure secret via JAVED_OWNER_TOKEN."
                )
            if len(stripped) < 8:
                raise ValueError("owner_token must be at least 8 characters long.")
        if self.env == "production" and not self.owner_token:
            raise ValueError(
                "Production environment requires JAVED_OWNER_TOKEN to be explicitly configured."
            )
        return self


# Known weak or placeholder credentials that must never be accepted as owner credentials
FORBIDDEN_OWNER_TOKENS = {
    "javed-local-owner-token",
    "admin",
    "password",
    "token",
    "secret",
    "owner",
    "12345678",
    "changeme",
    "owner-token",
    "local-owner-token",
    "placeholder",
    "test",
}


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

    raw_owner_token = os.getenv("JAVED_OWNER_TOKEN")
    owner_token: str | None = None
    if raw_owner_token is not None:
        stripped_token = raw_owner_token.strip()
        if not stripped_token:
            raise ValueError("JAVED_OWNER_TOKEN environment variable cannot be empty.")
        if stripped_token.lower() in FORBIDDEN_OWNER_TOKENS:
            raise ValueError(
                f"JAVED_OWNER_TOKEN cannot be a known weak placeholder ('{stripped_token}'). "
                "Configure a unique secure secret via JAVED_OWNER_TOKEN."
            )
        if len(stripped_token) < 8:
            raise ValueError("JAVED_OWNER_TOKEN must be at least 8 characters long.")
        owner_token = stripped_token

    env = os.getenv("JAVED_ENV", "development").strip().lower()

    kwargs = {
        "env": env,
        "host": os.getenv("JAVED_HOST", "127.0.0.1"),
        "port": int(os.getenv("JAVED_PORT", "8000")),
        "log_level": os.getenv("JAVED_LOG_LEVEL", "INFO"),
        "openrouter_api_key": os.getenv("OPENROUTER_API_KEY"),
        "openrouter_base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "openrouter_default_model": os.getenv("OPENROUTER_DEFAULT_MODEL", "openrouter/auto"),
        "openrouter_daily_budget_usd": daily_budget,
        "openrouter_timeout_seconds": float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60.0")),
        "openrouter_auto_router_cost_tier": os.getenv("OPENROUTER_AUTO_ROUTER_COST_TIER", "low"),
        "openrouter_system_prompt": os.getenv("OPENROUTER_SYSTEM_PROMPT"),
        "agent_checkpoint_db_path": os.getenv(
            "JAVED_AGENT_CHECKPOINT_DB_PATH", "data/checkpoints.db"
        ),
        "agent_approvals_db_path": os.getenv("JAVED_AGENT_APPROVALS_DB_PATH", "data/approvals.db"),
        "agent_stream_timeout_seconds": float(
            os.getenv("JAVED_AGENT_STREAM_TIMEOUT_SECONDS", "120.0")
        ),
        "owner_token": owner_token,
    }
    if allowed_origins:
        kwargs["allowed_origins"] = allowed_origins

    return Settings(**kwargs)
