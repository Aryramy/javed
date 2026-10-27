"""Pydantic schemas for Deep Agents & LangGraph agent runtime."""

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from javed.schemas.chat import ChatMessage, CostTier

AgentTodoStatus = Literal["pending", "in_progress", "completed"]

THREAD_ID_REGEX = r"^[a-zA-Z0-9_\-]+$"
_THREAD_ID_PATTERN = re.compile(THREAD_ID_REGEX)


def validate_thread_id(thread_id: str) -> str:
    """Validate thread identifier to prevent path traversal, injection, or malformed input.

    Rejects:
        - None or non-string input
        - Empty or whitespace-only strings
        - Strings containing path separators ('/', '\\') or traversal patterns ('..')
        - Strings with null bytes or control characters
        - Strings exceeding 128 characters
        - Strings with characters outside [a-zA-Z0-9_-]

    Returns:
        Validated, stripped thread identifier string.

    Raises:
        ValueError: If thread_id fails any security validation constraint.
    """
    if not isinstance(thread_id, str):
        raise ValueError("thread_id must be a string")

    stripped = thread_id.strip()
    if not stripped:
        raise ValueError("thread_id cannot be empty or whitespace only")

    if len(stripped) > 128:
        raise ValueError(
            f"thread_id exceeds maximum length of 128 characters (got {len(stripped)})"
        )

    # Explicit path traversal and separator rejection
    if ".." in stripped or "/" in stripped or "\\" in stripped:
        raise ValueError(f"thread_id contains illegal path traversal characters: '{thread_id}'")

    if "\x00" in stripped:
        raise ValueError("thread_id contains null byte character")

    if not _THREAD_ID_PATTERN.match(stripped):
        raise ValueError(
            f"Invalid thread_id format '{thread_id}'. Only alphanumeric characters, "
            f"hyphens, and underscores are permitted (pattern: {THREAD_ID_REGEX})."
        )

    return stripped


def extract_message_text(content: Any) -> str:
    """Extract plain text from string or multipart message content blocks.

    Handles:
        - Plain string content: returns as-is
        - List of strings: joins strings
        - List of dicts (OpenAI/Anthropic blocks): extracts 'text' or 'content' keys
        - None: returns empty string
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(str(block["text"]))
                elif "content" in block:
                    parts.append(str(block["content"]))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content)


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
        max_length=128,
        pattern=THREAD_ID_REGEX,
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

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id_field(cls, v: str) -> str:
        return validate_thread_id(v)


ToolLifecycleState = Literal[
    "REQUESTED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "UNCERTAIN",
]


class ToolActivityRecord(BaseModel):
    """User Mode live representation of an MCP tool invocation."""

    tool_call_id: str = Field(description="Unique tool call or invocation ID")
    tool_id: str = Field(description="Canonical namespaced tool ID (e.g. time__get_current_time)")
    server_id: str = Field(default="unknown", description="MCP server identity")
    tool_name: str | None = Field(default=None, description="Human friendly display name")
    description: str | None = Field(default=None, description="Tool purpose or summary")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Input arguments")
    status: ToolLifecycleState = Field(
        default="COMPLETED",
        description="Current lifecycle state",
    )
    result_summary: str | None = Field(default=None, description="Sanitized result output")
    error_message: str | None = Field(default=None, description="Sanitized error text")
    started_at: datetime | None = Field(default=None, description="Start timestamp UTC")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp UTC")
    elapsed_ms: int | None = Field(default=None, description="Elapsed duration in milliseconds")
    approval_id: str | None = Field(default=None, description="Associated approval ID if gated")


class AgentStreamEvent(BaseModel):
    """Typed Server-Sent Event envelope emitted during agent execution."""

    event: str = Field(
        description=(
            "Agent event type: run_started, planning, plan_updated, "
            "model_streaming, checkpoint_saved, tool_requested, tool_started, "
            "tool_completed, tool_failed, approval_required, approval_approved, "
            "approval_rejected, approval_cancelled, agent_resumed, "
            "run_completed, run_cancelled, run_failed"
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
    active_model: str | None = Field(
        default=None,
        description="Active model identifier associated with this thread run",
    )
    tool_calls: list[ToolActivityRecord] = Field(
        default_factory=list,
        description="Tool activity records reconstructed for this thread",
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
