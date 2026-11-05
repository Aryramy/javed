"""ledger.py — Action ledger, deduplication, and read tracking for JAVED.

Tracks fine-grained task actions, normalized tool calls, file read scopes,
failure fingerprints, and detects duplicate actions/reads to prevent loop thrashing.
Zero sensitive credentials, prompts, or full files are ever stored.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ActionStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REUSED = "reused"


class FailureClassification(StrEnum):
    NONE = "none"
    PATCH_DEFECT = "patch_defect"
    EXISTING_FAILURE = "existing_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    FLAKY_TEST = "flaky_test"
    OUTDATED_TEST_CONTRACT = "outdated_test_contract"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ActionRecord:
    """Immutable audit record of a single agent action.

    NEVER stores chain-of-thought, prompts, secrets, or raw file contents.
    """

    action_id: str
    task_id: str
    action_type: str
    target: str
    normalized_arguments_hash: str
    git_head: str
    relevant_file_hashes: dict[str, str]
    start_time: str
    end_time: str
    duration_ms: int
    status: ActionStatus
    result_fingerprint: str
    evidence_summary: str
    budget_delta: dict[str, Any]
    retryable: bool
    failure_classification: FailureClassification = FailureClassification.NONE

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["failure_classification"] = self.failure_classification.value
        return data


@dataclass(frozen=True)
class FileReadRecord:
    """Record of an individual file-read operation."""

    file_path: str
    content_hash: str
    line_range: str  # e.g. "L10-L40" or "ALL"
    reason: str
    task_iteration: int
    read_at: str


@dataclass
class ActionLedger:
    """In-memory and serializable ledger of task execution actions and read records."""

    task_id: str
    actions: list[ActionRecord] = field(default_factory=list)
    file_reads: list[FileReadRecord] = field(default_factory=list)
    duplicate_actions_prevented: int = 0
    duplicate_reads_prevented: int = 0

    def compute_action_hash(self, action_type: str, target: str, arguments: dict[str, Any]) -> str:
        """Deterministic normalization and hashing of action arguments."""
        # Sanitize sensitive keys before hashing
        sensitive_keys = {"api_key", "authorization", "password", "token", "secret"}
        sanitized_args = {}
        for k, v in sorted(arguments.items()):
            if any(s in k.lower() for s in sensitive_keys):
                sanitized_args[k] = "[REDACTED]"
            else:
                sanitized_args[k] = v
        raw = json.dumps(
            {"type": action_type, "target": target, "args": sanitized_args},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record_action(self, action: ActionRecord) -> None:
        """Append action record to audit log."""
        self.actions.append(action)

    def find_equivalent_action(
        self,
        action_type: str,
        target: str,
        arg_hash: str,
        current_git_head: str,
        current_file_hashes: dict[str, str],
    ) -> ActionRecord | None:
        """Find previous equivalent action if Git HEAD and relevant file hashes match."""
        for a in reversed(self.actions):
            if (
                a.action_type == action_type
                and a.target == target
                and a.normalized_arguments_hash == arg_hash
            ):
                # Verify environmental and repository identity
                if a.git_head == current_git_head:
                    # Check relevant file hashes
                    if a.relevant_file_hashes == current_file_hashes:
                        return a
        return None

    def record_file_read(
        self,
        file_path: str,
        content_hash: str,
        line_range: str,
        reason: str,
        iteration: int,
    ) -> None:
        """Record an approved file read operation."""
        rec = FileReadRecord(
            file_path=file_path,
            content_hash=content_hash,
            line_range=line_range,
            reason=reason,
            task_iteration=iteration,
            read_at=datetime.now(UTC).isoformat(),
        )
        self.file_reads.append(rec)

    def check_duplicate_read(
        self,
        file_path: str,
        current_content_hash: str,
        line_range: str,
    ) -> bool:
        """Check if identical unchanged content and line range was already read."""
        for r in self.file_reads:
            if r.file_path == file_path:
                # If content hash unchanged and range covered or identical
                if r.content_hash == current_content_hash:
                    if r.line_range == line_range or r.line_range == "ALL":
                        return True
        return False

    def get_unique_files_read_count(self) -> int:
        """Count unique files read across task execution."""
        return len({r.file_path for r in self.file_reads})

    def get_repeated_reads_count(self, file_path: str) -> int:
        """Count read repetitions for a given file."""
        return sum(1 for r in self.file_reads if r.file_path == file_path)

    def to_dict(self) -> dict[str, Any]:
        """Serialize ledger for checkpointing without raw file content or prompts."""
        return {
            "task_id": self.task_id,
            "actions_count": len(self.actions),
            "duplicate_actions_prevented": self.duplicate_actions_prevented,
            "duplicate_reads_prevented": self.duplicate_reads_prevented,
            "actions": [a.to_dict() for a in self.actions],
            "file_reads": [asdict(fr) for fr in self.file_reads],
        }
