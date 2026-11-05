"""state.py — Typed task state and workflow state definitions for JAVED.

Strictly adheres to security and storage boundaries:
- Stores structured metadata, decisions, fingerprints, and audit identifiers.
- NEVER stores chain-of-thought, thinking tokens, API keys, full source files,
  uploaded documents, or provider payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from javed.agent.efficiency.briefs import PreEditBrief
from javed.agent.efficiency.budgets import TaskClass
from javed.agent.efficiency.gate import ApprovalStatus, BriefApprovalRecord
from javed.agent.efficiency.watchdog import TaskCheckpoint, WatchdogState


class WorkflowState(StrEnum):
    """Operational and exceptional states in the bounded coding workflow."""

    # Operational states
    INTAKE = "INTAKE"
    REPOSITORY_ORIENTATION = "REPOSITORY_ORIENTATION"
    ROOT_CAUSE_OR_DESIGN = "ROOT_CAUSE_OR_DESIGN"
    PLANNING = "PLANNING"
    PLAN_GATE = "PLAN_GATE"
    CODING = "CODING"
    REVIEW = "REVIEW"
    TARGETED_TESTING = "TARGETED_TESTING"
    REGRESSION_TESTING = "REGRESSION_TESTING"
    FINAL_REVIEW = "FINAL_REVIEW"
    COMPLETED = "COMPLETED"

    # Exceptional states
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    STALLED = "STALLED"
    TIMEOUT = "TIMEOUT"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    SCOPE_EXPANSION_REQUIRED = "SCOPE_EXPANSION_REQUIRED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class CodingTaskState:
    """Typed shared state governing the LangGraph cyclic coding workflow.

    NEVER stores chain-of-thought, prompts, secrets, full source codes, or provider payloads.
    """

    # Task identity and classification
    task_id: str
    task_type: (
        str  # DEFECT, FEATURE, DOCUMENTATION, REFACTOR, SECURITY_FIX, MIGRATION, INVESTIGATION
    )
    objective: str
    repository_head: str
    current_state: WorkflowState = WorkflowState.INTAKE
    task_class: TaskClass = TaskClass.SINGLE_FILE_DEFECT

    # Repository context and orientation (bounded metadata)
    repository_context: dict[str, Any] = field(default_factory=dict)
    graph_freshness: str = "UNKNOWN"

    # Pre-Edit Brief and approval binding
    pre_edit_brief: PreEditBrief | None = None
    brief_hash: str | None = None
    approval_record: BriefApprovalRecord | None = None
    approval_id: str | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_files: list[str] = field(default_factory=list)
    approved_symbols: list[str] = field(default_factory=list)
    approved_line_ranges: list[dict[str, Any]] = field(default_factory=list)

    # Implementation plan and code artifacts
    implementation_plan: list[dict[str, Any]] = field(default_factory=list)
    current_diff_reference: str = ""
    patch_summary: dict[str, Any] = field(default_factory=dict)

    # Review findings and reviewer audit trail
    reviewer_findings: list[dict[str, Any]] = field(default_factory=list)
    review_status: str = "PENDING"
    review_notes: list[str] = field(default_factory=list)

    # Test plan and verification execution results
    test_plan: list[str] = field(default_factory=list)
    test_results: list[dict[str, Any]] = field(default_factory=list)
    failure_fingerprints: list[str] = field(default_factory=list)

    # Watchdog state and execution counters
    watchdog_state: WatchdogState = WatchdogState.ACTIVE
    budget_counters: dict[str, Any] = field(default_factory=dict)
    action_ledger_reference: str = ""
    checkpoint_reference: TaskCheckpoint | None = None

    # Work tracking and final completion decision
    remaining_work: list[str] = field(default_factory=list)
    final_decision: str = "PENDING"
    final_notes: list[str] = field(default_factory=list)

    # Loop and anti-thrashing circuit counters
    node_visit_counts: dict[str, int] = field(default_factory=dict)
    consecutive_no_progress_count: int = 0
    replan_count: int = 0
    cancellation_requested: bool = False
    stop_reason: str = ""

    def __post_init__(self) -> None:
        # Sanity check: never allow sensitive tokens in objective
        lower_obj = self.objective.lower()
        for token in ("api_key", "authorization", "bearer ", "password", "secret_token"):
            if token in lower_obj:
                raise ValueError(f"Sensitive credential detected in task objective: {token}")

    def increment_visit(self, node_name: str) -> int:
        count = self.node_visit_counts.get(node_name, 0) + 1
        self.node_visit_counts[node_name] = count
        return count

    def get_visit_count(self, node_name: str) -> int:
        return self.node_visit_counts.get(node_name, 0)

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary ensuring zero secret or full-source leakage."""
        data = asdict(self)
        data["current_state"] = self.current_state.value
        data["task_class"] = self.task_class.value
        data["approval_status"] = self.approval_status.value
        data["watchdog_state"] = self.watchdog_state.value
        if self.pre_edit_brief:
            data["pre_edit_brief"] = {
                "task_id": self.pre_edit_brief.task_id,
                "task_type": self.pre_edit_brief.task_type.value,
                "brief_hash": self.brief_hash,
                "files_to_modify": self.pre_edit_brief.files_to_modify,
            }
        if self.approval_record:
            data["approval_record"] = {
                "approval_id": self.approval_record.approval_id,
                "approved_by": self.approval_record.approved_by,
                "expires_at": self.approval_record.expires_at,
            }
        if self.checkpoint_reference:
            data["checkpoint_reference"] = self.checkpoint_reference.to_dict()
        return data
