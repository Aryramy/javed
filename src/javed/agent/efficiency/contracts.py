"""contracts.py — Formal role contracts and node result envelopes for JAVED.

Enforces role boundaries, input/output typing, and strict constraints:
- Planner: Read-only, max 2 visits, no auto-approval.
- Coder: Must call write gate, max 3 visits, max 2 revisions.
- Reviewer: Isolated context, independent model, max 2 visits.
- Tester: Strictly executes approved test plan, no designing, identical failure circuit.
- Final Reviewer: Final gatekeeper, clean working tree, verified completion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from javed.agent.efficiency.ledger import FailureClassification


class PlanGateOutcome(StrEnum):
    """Possible decisions evaluated by the Plan Gate node."""

    PLAN_APPROVED = "PLAN_APPROVED"
    PLAN_REJECTED = "PLAN_REJECTED"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    SCOPE_EXPANSION_REQUIRED = "SCOPE_EXPANSION_REQUIRED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class ReviewerOutcome(StrEnum):
    """Possible outcomes evaluated by the independent Reviewer node."""

    APPROVED = "APPROVED"
    APPROVED_WITH_NOTES = "APPROVED_WITH_NOTES"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    REJECTED = "REJECTED"


class FinalReviewerOutcome(StrEnum):
    """Possible outcomes evaluated by the Final Reviewer node."""

    FINAL_APPROVED = "FINAL_APPROVED"
    FINAL_APPROVED_WITH_NOTES = "FINAL_APPROVED_WITH_NOTES"
    FINAL_REJECTED = "FINAL_REJECTED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"


@dataclass(frozen=True)
class NodeResult:
    """Standardized audit envelope returned by all workflow nodes."""

    node_name: str
    success: bool
    next_state: str
    progress_made: bool
    summary: str
    evidence_collected: list[str] = field(default_factory=list)
    failure_reason: str = ""
    failure_classification: FailureClassification = FailureClassification.NONE
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        # Credential stripping
        lower_summary = self.summary.lower()
        for token in ("api_key", "authorization", "bearer ", "password", "secret_token"):
            if token in lower_summary:
                raise ValueError(f"Sensitive credential detected in node result summary: {token}")


@dataclass(frozen=True)
class PlannerOutput:
    """Formal contract returned by the Planner node."""

    implementation_steps: list[str]
    target_files: list[str]
    target_symbols: list[str]
    target_line_ranges: list[dict[str, Any]]
    test_sequence: list[str]
    rollback_sequence: list[str]
    risk_controls: list[str]
    completion_criteria: list[str]


@dataclass(frozen=True)
class CoderOutput:
    """Formal contract returned by the Coder node."""

    modified_files: list[str]
    patch_fingerprint: str
    lines_added: int
    lines_removed: int
    summary: str
    target_ranges_honored: bool = True
    new_tests_added: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewerOutput:
    """Formal contract returned by the Reviewer node."""

    outcome: ReviewerOutcome
    findings: list[dict[str, Any]]
    notes: list[str]
    complexity_score: int  # 1 (clean) to 5 (over-engineered)
    unrelated_changes_detected: bool
    security_boundary_intact: bool
    public_contracts_intact: bool


@dataclass(frozen=True)
class TesterOutput:
    """Formal contract returned by the Tester node."""

    __test__ = False

    tests_executed: list[str]
    passed_count: int
    failed_count: int
    exit_code: int
    safe_summary: str
    failure_fingerprints: list[str]
    failure_classification: FailureClassification
    retryable: bool


@dataclass(frozen=True)
class FinalReviewerOutput:
    """Formal contract returned by the Final Reviewer node."""

    outcome: FinalReviewerOutcome
    clean_working_tree_verified: bool
    unresolved_findings_count: int
    documentation_consistent: bool
    resource_hygiene_verified: bool
    summary: str
