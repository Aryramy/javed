"""gate.py — Pre-Edit Brief approval lifecycle, gate evaluation, and write authorization for JAVED.

Enforces fail-closed write gating against validated Pre-Edit Briefs, active approvals,
repository commit consistency, target line ranges, and watchdog execution states.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from javed.agent.efficiency.briefs import (
    PreEditBrief,
    RootCauseConfidence,
    TargetLineRange,
    TaskType,
)
from javed.agent.efficiency.watchdog import WatchdogEngine, WatchdogState


class ApprovalStatus(StrEnum):
    """Lifecycle status of a brief approval."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    CONSUMED = "CONSUMED"
    CANCELLED = "CANCELLED"


class WriteOperation(StrEnum):
    """Supported file modification operations."""

    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    RENAME = "RENAME"


class WriteAuthorizationDecision(StrEnum):
    """Exhaustive fail-closed outcomes for write authorization checks."""

    ALLOWED = "ALLOWED"
    DENIED_NO_BRIEF = "DENIED_NO_BRIEF"
    DENIED_INVALID_BRIEF = "DENIED_INVALID_BRIEF"
    DENIED_NO_APPROVAL = "DENIED_NO_APPROVAL"
    DENIED_EXPIRED_APPROVAL = "DENIED_EXPIRED_APPROVAL"
    DENIED_STALE_REPOSITORY = "DENIED_STALE_REPOSITORY"
    DENIED_STALE_FILE = "DENIED_STALE_FILE"
    DENIED_UNDECLARED_FILE = "DENIED_UNDECLARED_FILE"
    DENIED_UNDECLARED_SYMBOL = "DENIED_UNDECLARED_SYMBOL"
    DENIED_OUT_OF_RANGE = "DENIED_OUT_OF_RANGE"
    DENIED_SENSITIVE_PATH = "DENIED_SENSITIVE_PATH"
    DENIED_BUDGET_STATE = "DENIED_BUDGET_STATE"
    SCOPE_EXPANSION_REQUIRED = "SCOPE_EXPANSION_REQUIRED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"


@dataclass(frozen=True)
class BriefApprovalRecord:
    """Signed authorization record granting write permission under a validated brief."""

    approval_id: str
    task_id: str
    brief_hash: str
    repository_head: str
    approved_files: list[str]
    approved_symbols: list[str]
    approved_line_ranges: list[TargetLineRange]
    approved_task_class: str
    approved_at: str
    expires_at: str
    approved_by: str = "ProjectOwner"
    status: ApprovalStatus = ApprovalStatus.APPROVED
    single_use: bool = False
    consumed_at: str | None = None

    def is_expired(self, current_iso_time: str | None = None) -> bool:
        now_str = current_iso_time or datetime.now(UTC).isoformat()
        return now_str > self.expires_at


@dataclass(frozen=True)
class WriteAuthorizationResult:
    """Detailed audit verdict returned by the write gate."""

    decision: WriteAuthorizationDecision
    allowed: bool
    reason: str
    affected_rule: str
    corrective_action: str
    task_id: str
    file_path: str
    operation: WriteOperation
    brief_hash: str | None = None
    approval_id: str | None = None
    watchdog_state: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        data["operation"] = self.operation.value
        return data


class PreEditGate:
    """Evaluates and enforces Pre-Edit Brief validation and write authorization."""

    @staticmethod
    def approve_brief(
        brief: PreEditBrief,
        approver: str = "ProjectOwner",
        expires_in_seconds: int = 3600,
        single_use: bool = False,
        owner_override_low_confidence: bool = False,
    ) -> tuple[BriefApprovalRecord | None, list[str]]:
        """Validate and grant formal approval record for a brief."""
        valid, errors = brief.validate_structure()
        if not valid:
            return None, errors

        # Root-cause confidence rule
        if brief.task_type in {TaskType.DEFECT, TaskType.SECURITY_FIX}:
            if brief.root_cause_confidence in {
                RootCauseConfidence.LOW,
                RootCauseConfidence.MEDIUM,
            }:
                if not owner_override_low_confidence:
                    return (
                        None,
                        [
                            f"Root cause confidence is {brief.root_cause_confidence.value}. "
                            "Requires HIGH or VERIFIED, or explicit owner override."
                        ],
                    )

        now = datetime.now(UTC)
        expires = datetime.fromtimestamp(now.timestamp() + expires_in_seconds, tz=UTC)

        approval = BriefApprovalRecord(
            approval_id=f"APPR-{brief.task_id[:12]}-{int(now.timestamp())}",
            task_id=brief.task_id,
            brief_hash=brief.compute_brief_hash(),
            repository_head=brief.repository_head,
            approved_files=list(brief.files_to_modify),
            approved_symbols=list(brief.affected_symbols),
            approved_line_ranges=list(brief.target_line_ranges),
            approved_task_class=brief.task_type.value,
            approved_at=now.isoformat(),
            expires_at=expires.isoformat(),
            approved_by=approver,
            status=ApprovalStatus.APPROVED,
            single_use=single_use,
        )
        return approval, []

    @staticmethod
    def authorize_write(
        watchdog: WatchdogEngine,
        brief: PreEditBrief | None,
        approval: BriefApprovalRecord | None,
        relative_path: str,
        operation: WriteOperation,
        target_lines: list[int] | None = None,
        current_file_hash: str | None = None,
        expected_file_hash: str | None = None,
    ) -> WriteAuthorizationResult:
        """Evaluate write authorization fail-closed across all policy rules."""
        norm_path = relative_path.replace("\\", "/").strip()
        now_iso = datetime.now(UTC).isoformat()

        # 1. Traversal and sensitive path defense
        if ".." in norm_path or norm_path.startswith(("/", "\\")):
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_SENSITIVE_PATH,
                allowed=False,
                reason=f"Path traversal rejected: '{relative_path}'",
                affected_rule="RULE_PATH_TRAVERSAL",
                corrective_action="Use safe path relative to repository root.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        if any(seg in norm_path for seg in [".env", ".git", "node_modules", ".venv"]):
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_SENSITIVE_PATH,
                allowed=False,
                reason=f"Modification of protected path rejected: '{relative_path}'",
                affected_rule="RULE_PROTECTED_PATH",
                corrective_action="Remove protected directory from write scope.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 2. Watchdog State Check
        denied_states = {
            WatchdogState.BUDGET_EXCEEDED,
            WatchdogState.STALLED,
            WatchdogState.TIMEOUT,
            WatchdogState.OWNER_INPUT_REQUIRED,
            WatchdogState.CANCELLED,
            WatchdogState.COMPLETED,
            WatchdogState.FAILED,
        }
        if watchdog.state in denied_states:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_BUDGET_STATE,
                allowed=False,
                reason=f"Watchdog is in terminal or blocked state: {watchdog.state.value}",
                affected_rule="RULE_WATCHDOG_DISCIPLINE",
                corrective_action="Resolve watchdog state or obtain explicit owner override.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 3. Brief Presence & Validation
        if brief is None:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_NO_BRIEF,
                allowed=False,
                reason="No Pre-Edit Brief has been authored for this task.",
                affected_rule="RULE_MANDATORY_PRE_EDIT_BRIEF",
                corrective_action=(
                    "Author and submit Pre-Edit Brief before proposing code modifications."
                ),
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        if brief.task_type == TaskType.INVESTIGATION:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_INVALID_BRIEF,
                allowed=False,
                reason="INVESTIGATION tasks are read-only and cannot authorize code edits.",
                affected_rule="RULE_INVESTIGATION_TASK_IMMUTABILITY",
                corrective_action=(
                    "Reclassify task to DEFECT, FEATURE, or REFACTOR with approved brief."
                ),
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        valid_struct, errors = brief.validate_structure()
        if not valid_struct:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_INVALID_BRIEF,
                allowed=False,
                reason=f"Brief failed structural validation: {'; '.join(errors[:2])}",
                affected_rule="RULE_BRIEF_QUALITY",
                corrective_action="Correct brief errors and resubmit.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 4. Approval Presence & Validity
        if approval is None or approval.status != ApprovalStatus.APPROVED:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_NO_APPROVAL,
                allowed=False,
                reason="Pre-Edit Brief has not received formal approval.",
                affected_rule="RULE_BRIEF_APPROVAL",
                corrective_action="Submit brief for Project Owner or gate approval.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        if approval.task_id != brief.task_id or approval.task_id != watchdog.task_id:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_NO_APPROVAL,
                allowed=False,
                reason="Approval task_id does not match current active task.",
                affected_rule="RULE_APPROVAL_TASK_BOUND",
                corrective_action="Approval cannot be reused across tasks.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        if approval.is_expired(now_iso):
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_EXPIRED_APPROVAL,
                allowed=False,
                reason=f"Approval expired at {approval.expires_at}.",
                affected_rule="RULE_APPROVAL_EXPIRY",
                corrective_action="Obtain renewed approval for the active task.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        if approval.single_use and approval.consumed_at is not None:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_NO_APPROVAL,
                allowed=False,
                reason="Single-use approval has already been consumed.",
                affected_rule="RULE_SINGLE_USE_APPROVAL",
                corrective_action="Obtain fresh approval for next modification.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 5. Repository Stale Check
        if approval.repository_head != watchdog.git_head:
            app_h = approval.repository_head[:7]
            cur_h = watchdog.git_head[:7]
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_STALE_REPOSITORY,
                allowed=False,
                reason=f"Git HEAD shifted from approved {app_h} to {cur_h}.",
                affected_rule="RULE_REPOSITORY_CONSISTENCY",
                corrective_action="Rebase or re-verify brief against current Git HEAD.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 6. File Stale Check
        if current_file_hash and expected_file_hash and current_file_hash != expected_file_hash:
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.DENIED_STALE_FILE,
                allowed=False,
                reason=f"File hash changed on disk for '{norm_path}'.",
                affected_rule="RULE_FILE_CONSISTENCY",
                corrective_action="Reread file and update brief evidence with new hash.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 7. Scope Check: File listed in approved_files
        if norm_path not in approval.approved_files:
            watchdog.state = WatchdogState.SCOPE_EXPANSION_REQUIRED
            return WriteAuthorizationResult(
                decision=WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED,
                allowed=False,
                reason=f"File '{norm_path}' was not declared in approved files_to_modify.",
                affected_rule="RULE_SCOPE_DISCIPLINE",
                corrective_action="Update Pre-Edit Brief scope and obtain reapproval.",
                task_id=watchdog.task_id,
                file_path=norm_path,
                operation=operation,
                watchdog_state=watchdog.state.value,
            )

        # 8. Target Line-Range Check
        if target_lines and operation == WriteOperation.MODIFY:
            # Find matching declared ranges for this file
            matching_ranges = [
                r for r in approval.approved_line_ranges if r.relative_path == norm_path
            ]
            if not matching_ranges:
                return WriteAuthorizationResult(
                    decision=WriteAuthorizationDecision.DENIED_OUT_OF_RANGE,
                    allowed=False,
                    reason=f"No target line ranges declared for '{norm_path}'.",
                    affected_rule="RULE_LINE_RANGE_AUTHORIZATION",
                    corrective_action="Declare target line ranges in brief.",
                    task_id=watchdog.task_id,
                    file_path=norm_path,
                    operation=operation,
                    watchdog_state=watchdog.state.value,
                )

            # Check if all target lines fall within at least one range (20-line allowance)
            for line_no in target_lines:
                if not any(r.contains_line(line_no, allowance=20) for r in matching_ranges):
                    return WriteAuthorizationResult(
                        decision=WriteAuthorizationDecision.DENIED_OUT_OF_RANGE,
                        allowed=False,
                        reason=(
                            f"Line {line_no} falls outside authorized range for '{norm_path}'."
                        ),
                        affected_rule="RULE_LINE_RANGE_AUTHORIZATION",
                        corrective_action="Expand declared target line range in brief.",
                        task_id=watchdog.task_id,
                        file_path=norm_path,
                        operation=operation,
                        watchdog_state=watchdog.state.value,
                    )

        # All checks passed
        return WriteAuthorizationResult(
            decision=WriteAuthorizationDecision.ALLOWED,
            allowed=True,
            reason="All Pre-Edit Brief and approval requirements satisfied.",
            affected_rule="RULE_PRE_EDIT_GATE_PASSED",
            corrective_action="Proceed with authorized write operation.",
            task_id=watchdog.task_id,
            file_path=norm_path,
            operation=operation,
            brief_hash=approval.brief_hash,
            approval_id=approval.approval_id,
            watchdog_state=watchdog.state.value,
        )
