"""Pydantic schemas and typed data models for Durable Human-in-the-Loop Approvals
(BRICK-005 Phase 5).
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ApprovalStatus = Literal["pending", "approved", "rejected", "cancelled", "expired"]
DispatchStatus = Literal["not_dispatched", "in_flight", "completed", "failed", "uncertain"]
ApprovalDecisionType = Literal["approve", "reject"]


def compute_argument_digest(arguments: dict[str, Any] | None) -> str:
    """Generate a deterministic SHA-256 digest of validated tool arguments using canonical JSON."""
    payload = arguments if arguments is not None else {}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ApprovalRecord(BaseModel):
    """Authoritative durable record tracking a pending, approved, or rejected tool call."""

    approval_id: str = Field(..., description="Unique approval identifier (e.g., 'appr_...')")
    interrupt_id: str = Field(..., description="LangGraph interrupt ID from HITL request")
    run_id: str = Field(..., description="Agent execution run identifier")
    thread_id: str = Field(..., description="Conversation thread identifier")
    server_id: str = Field(..., description="MCP server originating the tool call")
    tool_id: str = Field(..., description="Namespaced tool ID: {server_id}__{tool_name}")
    tool_call_id: str = Field(..., description="Unique tool-call ID from AIMessage")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Exact validated arguments")
    argument_digest: str = Field(..., description="Deterministic SHA-256 digest of arguments")
    tool_fingerprint: str = Field(
        ..., description="Deterministic SHA-256 tool metadata fingerprint"
    )
    policy_version: int = Field(..., description="Host policy version when approval was raised")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(default=None, description="Optional expiration timestamp")
    status: ApprovalStatus = Field("pending", description="Current lifecycle state")
    decision_at: datetime | None = Field(default=None, description="Timestamp of human decision")
    decision_by: str | None = Field(
        default=None, description="Identity of decider (e.g. human_user)"
    )
    rejection_reason: str | None = Field(
        default=None, description="Optional human rejection explanation"
    )
    dispatch_status: DispatchStatus = Field(
        "not_dispatched", description="Transport dispatch lifecycle state"
    )
    dispatched_at: datetime | None = Field(
        default=None, description="Timestamp of transport dispatch"
    )
    completed_at: datetime | None = Field(default=None, description="Timestamp of tool completion")
    result_summary: str | None = Field(default=None, description="Brief sanitized result summary")
    error_message: str | None = Field(default=None, description="Execution error message if failed")


class ApprovalDecisionRequest(BaseModel):
    """Request payload submitted by human reviewer to approve or reject a pending tool call."""

    decision: ApprovalDecisionType = Field(..., description="'approve' or 'reject'")
    thread_id: str = Field(..., description="Thread ID to verify decision context")
    reason: str | None = Field(
        default=None, description="Optional explanation, especially on rejection"
    )


class ApprovalResponse(BaseModel):
    """Response payload returning the updated approval record."""

    approval: ApprovalRecord
    message: str


class ApprovalListResponse(BaseModel):
    """Response payload listing pending or historical approval records."""

    approvals: list[ApprovalRecord]
    total: int
