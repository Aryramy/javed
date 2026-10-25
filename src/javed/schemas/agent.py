"""Pydantic schemas for Deep Agents & LangGraph agent runtime."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from javed.schemas.chat import ChatMessage, CostTier

AgentTodoStatus = Literal["pending", "in_progress", "completed"]


class AgentTodoItem(BaseModel):
    """Structured plan task item managed by TodoListMiddleware write_todos."""

    id: str = Field(default="", description="Unique task identifier or index")
    content: str = Field(description="Descriptive task title or action statement")
    status: AgentTodoStatus = Field(
        default="pending",
        description="Task lifecycle status: pending, in_progress, or completed",
    )


class AgentStreamRequest(BaseModel):
    """Inbound request to run the agent in a stateful conversation thread."""

    thread_id: str = Field(
        min_length=1,
        max_length=255,
        description="Thread identifier for persistent LangGraph checkpoints",
    )
    message: str = Field(
        min_length=1,
        description="User prompt or task instruction",
    )
    model: str | None = Field(
        default=None,
        description="Optional model ID (defaults to Settings.openrouter_default_model)",
    )
    cost_tier: CostTier | None = Field(
        default=None,
        description="Cost tier for openrouter/auto (low, medium, high, xhigh, max)",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional OpenRouter session ID for prompt caching and stickiness",
    )


class AgentStreamEvent(BaseModel):
    """Typed Server-Sent Event envelope emitted during agent execution."""

    event: str = Field(
        description=(
            "Agent event type: run_started, planning, plan_updated, "
            "model_streaming, checkpoint_saved, run_completed, run_cancelled, run_failed"
        ),
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event payload attributes",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event generation timestamp (UTC)",
    )


class AgentThreadStateResponse(BaseModel):
    """State snapshot for a restored thread."""

    thread_id: str = Field(description="Thread identifier")
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="All messages recorded in the thread state",
    )
    todos: list[AgentTodoItem] = Field(
        default_factory=list,
        description="Current active or completed todos in thread state",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="Latest checkpoint ID if saved",
    )
    exists: bool = Field(
        default=False,
        description="Whether this thread has committed checkpoints",
    )


class AgentRuntimeStatusResponse(BaseModel):
    """Diagnostic status for Developer Mode and health probes."""

    status: str = Field(default="ready", description="Runtime status: ready, degraded, error")
    checkpointer: str = Field(
        default="sqlite",
        description="Active checkpointer implementation (e.g. sqlite)",
    )
    checkpoint_db_path: str = Field(
        description="Path to SQLite checkpoints database file",
    )
    security_profile: str = Field(
        default="zero-trust-planning-only",
        description="Applied security profile",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Tools currently visible to the model (strictly bounded)",
    )
    excluded_tools: list[str] = Field(
        default_factory=list,
        description="Tools explicitly blocked by the security profile",
    )
