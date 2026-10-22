"""Pydantic schemas for chat completions, streaming, and model catalog."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single message in a conversational thread."""

    role: Literal["system", "user", "assistant"] = Field(
        description="Message sender role: system, user, or assistant",
    )
    content: str = Field(
        description="Text content of the message",
    )
    reasoning: str | None = Field(
        default=None,
        description="Separate model reasoning/thought trace (not part of ordinary assistant response content)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message creation timestamp (UTC)",
    )


CostTier = Literal["low", "medium", "high", "xhigh", "max"]


class ChatRequest(BaseModel):
    """Inbound chat completion and streaming request."""

    messages: list[ChatMessage] = Field(
        min_length=1,
        description="Chronological history of conversation messages",
    )
    model: str | None = Field(
        default=None,
        description="Optional model ID; falls back to default if omitted",
    )
    cost_tier: CostTier | None = Field(
        default=None,
        description="Optional cost tier for openrouter/auto routing (low, medium, high, xhigh, max)",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional conversation/session identifier for Auto Router session stickiness",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Maximum tokens to generate",
    )
    stream: bool = Field(
        default=True,
        description="Whether to stream the response chunks",
    )


class StreamUsage(BaseModel):
    """Token consumption and cost telemetry."""

    prompt_tokens: int = Field(default=0, description="Input/prompt token count")
    completion_tokens: int = Field(default=0, description="Generated output token count")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    cost_usd: float = Field(default=0.0, description="Calculated or reported cost in USD")
    upstream_cost: float | None = Field(
        default=None,
        description="Exact cost reported directly by OpenRouter if available",
    )
    is_estimated: bool = Field(
        default=False,
        description="Whether the cost and token counts are estimated vs provider-reconciled",
    )
    cost_source: Literal["upstream", "rate_card", "character_estimate"] = Field(
        default="upstream",
        description="Source of cost calculation: upstream, rate_card, or estimate",
    )
    selected_model: str | None = Field(
        default=None,
        description="Concrete model selected by OpenRouter (e.g., when auto-routed)",
    )
    requested_model: str | None = Field(
        default=None,
        description="Original model or routing mode requested by client",
    )
    cost_tier: str | None = Field(
        default=None,
        description="Cost tier utilized if openrouter/auto was requested",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier associated with this usage record",
    )


class ChatStreamEvent(BaseModel):
    """Server-Sent Event envelope for chat streaming."""

    type: Literal["token", "reasoning", "usage", "error", "done"] = Field(
        description="Event type",
    )
    content: str | None = Field(
        default=None,
        description="Text token increment (present when type='token')",
    )
    reasoning: str | None = Field(
        default=None,
        description="Reasoning/thought token increment preserved separately from content (present when type='reasoning')",
    )
    usage: StreamUsage | None = Field(
        default=None,
        description="Usage statistics (present when type='usage')",
    )
    selected_model: str | None = Field(
        default=None,
        description="Concrete model selected by OpenRouter",
    )
    requested_model: str | None = Field(
        default=None,
        description="Original requested model or routing mode",
    )
    cost_tier: str | None = Field(
        default=None,
        description="Cost tier utilized if openrouter/auto was requested",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier associated with this stream event",
    )
    error: str | None = Field(
        default=None,
        description="Error description (present when type='error')",
    )


class ChatResponse(BaseModel):
    """Non-streaming chat completion response."""

    id: str = Field(description="Unique completion identifier")
    model: str = Field(description="Model used for inference")
    selected_model: str | None = Field(
        default=None,
        description="Concrete model selected by OpenRouter",
    )
    requested_model: str | None = Field(
        default=None,
        description="Original requested model or routing mode",
    )
    cost_tier: str | None = Field(
        default=None,
        description="Cost tier utilized if auto router was used",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier associated with this response",
    )
    reasoning: str | None = Field(
        default=None,
        description="Separate model reasoning trace if emitted",
    )
    message: ChatMessage = Field(description="Assistant response message")
    usage: StreamUsage = Field(description="Token usage and cost")
    finish_reason: str | None = Field(default=None, description="Completion finish reason")


class ModelInfo(BaseModel):
    """Information and pricing metadata for an LLM model."""

    id: str = Field(description="Model ID string for API calls")
    name: str = Field(description="Friendly human-readable display name")
    provider: str = Field(description="Model provider organization")
    context_length: int = Field(description="Max context window in tokens")
    pricing_prompt: float = Field(description="USD cost per 1M prompt tokens")
    pricing_completion: float = Field(description="USD cost per 1M completion tokens")
    description: str = Field(description="Brief summary of recommended use cases")
    is_default: bool = Field(default=False, description="Whether this is the system default model")
    is_favorite: bool = Field(default=False, description="Whether model is in favorites")
    is_router: bool = Field(
        default=False,
        description="Whether this entry is an Auto Router meta-model",
    )
    cost_tier: str | None = Field(default=None, description="Active or recommended cost tier")


class ModelCatalogResponse(BaseModel):
    """Catalog of available models and account quota status."""

    models: list[ModelInfo] = Field(description="List of available models")
    default_model: str = Field(description="System default model ID")
    authenticated: bool = Field(description="Whether a valid OpenRouter API key is loaded")
    quota_remaining_usd: float | None = Field(
        default=None,
        description="Remaining account balance/limit in USD from OpenRouter auth",
    )
    daily_budget_usd: float | None = Field(
        default=None,
        description="Optional application-side daily spending budget in USD (None if uncapped)",
    )
    total_models: int = Field(
        default=0,
        description="Total models available in the upstream OpenRouter catalog",
    )
    is_dynamic: bool = Field(
        default=True,
        description="Whether this catalog was populated dynamically from OpenRouter",
    )
