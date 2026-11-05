"""Pydantic schemas for atomic provider and thread binding contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProviderSelectionRequest(BaseModel):
    """Request payload to bind or switch provider for a thread."""

    provider_id: str = Field(
        ...,
        description="Target provider identifier ('auto', 'openrouter', 'cheaper_inference').",
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )
    cost_tier: Literal["low", "medium", "high", "highest", "max"] | None = Field(
        default=None,
        description="Optional routing cost tier when provider_id is 'auto'.",
    )
    interaction_mode: Literal["chat", "agent"] = Field(
        default="chat",
        description="Current interaction mode ('chat' or 'agent').",
    )
    current_thread_id: str | None = Field(
        default=None,
        description="Current thread identifier, if transitioning an existing thread.",
    )
    create_new_thread: bool = Field(
        default=True,
        description="Whether to generate a fresh, isolated provider-bound thread (recommended).",
    )


class ProviderBindingResponse(BaseModel):
    """Authoritative contract confirming an atomic provider, model, thread, and configuration."""

    thread_id: str = Field(
        ...,
        description="Unique thread identifier bound to this provider configuration.",
    )
    provider_id: str = Field(
        ...,
        description="Resolved provider identifier ('auto', 'openrouter', 'cheaper_inference').",
    )
    provider_mode: Literal["explicit", "auto"] = Field(
        ...,
        description="Routing mode ('explicit' for fixed provider or 'auto' for policy routing).",
    )
    effective_model_id: str = Field(
        ...,
        description=(
            "Authoritative backend-controlled model ID "
            "(e.g. 'deepseek-v4.1-flash-1017' or 'openrouter/auto')."
        ),
    )
    configuration_version: str = Field(
        ...,
        description="Monotonically increasing or unique configuration version token.",
    )
    display_name: str = Field(..., description="Human-readable provider label.")
    capabilities: dict[str, bool] = Field(
        default_factory=dict,
        description="Resolved capability flags for this provider.",
    )
