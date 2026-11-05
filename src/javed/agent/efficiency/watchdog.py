"""watchdog.py — Execution watchdog, budget tracking, and circuit breaker for JAVED.

Tracks real-time execution metrics against task-class budget profiles, enforces
80% Warning and 100% Hard Stop circuits, detects no-progress loops, handles owner overrides,
and exports clean serializable task checkpoints.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from javed.agent.efficiency.budgets import (
    GLOBAL_MAX_DURATION_SECONDS,
    TaskBudgetProfile,
    TaskClass,
    get_budget_profile,
)
from javed.agent.efficiency.ledger import (
    ActionLedger,
    ActionRecord,
    ActionStatus,
    FailureClassification,
)


class WatchdogState(StrEnum):
    """Discrete, deterministic state transitions for the watchdog engine."""

    ACTIVE = "ACTIVE"
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    STALLED = "STALLED"
    TIMEOUT = "TIMEOUT"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    SCOPE_EXPANSION_REQUIRED = "SCOPE_EXPANSION_REQUIRED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class OwnerBudgetOverride:
    """Explicit, auditable Project Owner budget extension."""

    task_id: str
    budget_name: str
    old_value: Any
    new_value: Any
    reason: str
    approved_at: str
    expires_at: str
    additional_scope: list[str] = field(default_factory=list)

    def is_expired(self, current_iso_time: str | None = None) -> bool:
        now_str = current_iso_time or datetime.now(UTC).isoformat()
        return now_str > self.expires_at


@dataclass
class ExecutionCounters:
    """Live counters tracking consumption against approved budget."""

    analysis_iterations: int = 0
    replans: int = 0
    files_modified: set[str] = field(default_factory=set)
    patch_count: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    targeted_test_runs: int = 0
    identical_test_retries: int = 0
    full_regression_runs: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    consecutive_no_progress_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class BudgetWarningEvent:
    """Warning event emitted when any critical resource crosses 80% allowance."""

    metric: str
    current_value: float
    max_value: float
    percentage_consumed: float
    remaining_allowance: float
    timestamp: str


@dataclass
class TaskCheckpoint:
    """Structured, resumable task checkpoint.

    NEVER stores chain-of-thought, passwords, API tokens, or full source contents.
    """

    task_id: str
    task_class: str
    git_head: str
    state: WatchdogState
    start_time: str
    duration_seconds: float
    counters: dict[str, Any]
    approved_files: list[str]
    failure_fingerprints: list[str]
    test_summary: dict[str, Any]
    remaining_work: list[str]
    overrides: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


class WatchdogEngine:
    """Enforceable execution-budget and watchdog engine for JAVED coding tasks."""

    def __init__(
        self,
        task_id: str,
        task_class: TaskClass | str,
        git_head: str,
        approved_files: list[str] | None = None,
        profile_override: TaskBudgetProfile | None = None,
        clock_fn: Any = None,
    ):
        self.task_id = task_id
        self.task_class = (
            task_class if isinstance(task_class, TaskClass) else TaskClass(task_class.lower())
        )
        self.profile = profile_override or get_budget_profile(self.task_class)
        self.git_head = git_head
        self.approved_files: set[str] = set(approved_files or [])
        self.clock = clock_fn or time.time

        self.state = WatchdogState.ACTIVE
        self.start_time = self.clock()
        self.start_time_iso = datetime.now(UTC).isoformat()

        self.counters = ExecutionCounters()
        self.ledger = ActionLedger(task_id=task_id)
        self.overrides: list[OwnerBudgetOverride] = []
        self.warnings: list[BudgetWarningEvent] = []
        self.failure_fingerprints: list[str] = []
        self.last_progress_event: str = "Initialized task"

    # ------------------------------------------------------------------
    # Time & Deadline Enforcement
    # ------------------------------------------------------------------

    def get_elapsed_seconds(self) -> float:
        return self.clock() - self.start_time

    def get_effective_limit(self, budget_name: str, base_limit: Any) -> Any:
        """Apply active owner override for a budget if present and unexpired."""
        for ov in reversed(self.overrides):
            if ov.budget_name == budget_name and not ov.is_expired():
                return ov.new_value
        return base_limit

    def check_time_limit(self) -> None:
        """Check elapsed wall-clock time against budget."""
        elapsed = self.get_elapsed_seconds()
        max_duration = self.get_effective_limit(
            "max_duration_seconds", self.profile.max_duration_seconds
        )

        if elapsed >= max_duration:
            self.state = WatchdogState.TIMEOUT
            return

        if elapsed >= 0.8 * max_duration:
            self._emit_warning(
                metric="duration_seconds",
                current=elapsed,
                maximum=max_duration,
            )

    # ------------------------------------------------------------------
    # Warning & Hard-Stop Circuit Breakers
    # ------------------------------------------------------------------

    def _emit_warning(self, metric: str, current: float, maximum: float) -> None:
        """Record budget warning and update state if still ACTIVE."""
        # Avoid duplicate warnings for same metric
        if any(w.metric == metric for w in self.warnings):
            return

        pct = (current / maximum) * 100.0
        rem = max(0.0, maximum - current)
        event = BudgetWarningEvent(
            metric=metric,
            current_value=current,
            max_value=maximum,
            percentage_consumed=pct,
            remaining_allowance=rem,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self.warnings.append(event)
        if self.state == WatchdogState.ACTIVE:
            self.state = WatchdogState.BUDGET_WARNING

    def _check_critical_budgets(self) -> None:
        """Verify 80% warning and 100% hard-stop thresholds across all dimensions."""
        self.check_time_limit()
        if self.state in {WatchdogState.TIMEOUT, WatchdogState.BUDGET_EXCEEDED}:
            return

        checks = [
            (
                "tool_calls",
                self.counters.tool_calls,
                self.get_effective_limit("max_tool_calls", self.profile.max_tool_calls),
            ),
            (
                "model_calls",
                self.counters.model_calls,
                self.get_effective_limit("max_model_calls", self.profile.max_model_calls),
            ),
            (
                "tokens",
                self.counters.total_tokens,
                self.get_effective_limit("max_tokens", self.profile.max_tokens),
            ),
            (
                "cost_usd",
                self.counters.cost_usd,
                self.get_effective_limit("max_cost_usd", self.profile.max_cost_usd),
            ),
            (
                "unique_files_read",
                self.ledger.get_unique_files_read_count(),
                self.get_effective_limit(
                    "max_unique_files_read", self.profile.max_unique_files_read
                ),
            ),
            (
                "files_modified",
                len(self.counters.files_modified),
                self.get_effective_limit("max_files_modified", self.profile.max_files_modified),
            ),
            (
                "patch_count",
                self.counters.patch_count,
                self.get_effective_limit("max_patch_count", self.profile.max_patch_count),
            ),
            (
                "targeted_test_runs",
                self.counters.targeted_test_runs,
                self.get_effective_limit(
                    "max_targeted_test_runs", self.profile.max_targeted_test_runs
                ),
            ),
        ]

        for metric, current, maximum in checks:
            if current >= maximum:
                self.state = WatchdogState.BUDGET_EXCEEDED
                return
            elif current >= 0.8 * maximum:
                self._emit_warning(metric, float(current), float(maximum))

    # ------------------------------------------------------------------
    # Analysis & Replanning Limits
    # ------------------------------------------------------------------

    def record_analysis_iteration(self, has_progress: bool = True) -> None:
        """Track analysis cycles and check iteration limits."""
        self.counters.analysis_iterations += 1
        max_iter = self.get_effective_limit(
            "max_analysis_iterations", self.profile.max_analysis_iterations
        )

        if not has_progress:
            self.counters.consecutive_no_progress_count += 1
        else:
            self.counters.consecutive_no_progress_count = 0

        if self.counters.consecutive_no_progress_count >= 2:
            self.state = WatchdogState.STALLED
            return

        if self.counters.analysis_iterations > max_iter:
            self.state = WatchdogState.REPLAN_REQUIRED
            return

        self._check_critical_budgets()

    def record_replan(self) -> bool:
        """Attempt to transition from STALLED or REPLAN_REQUIRED to ACTIVE."""
        max_replans = self.get_effective_limit("max_replans", self.profile.max_replans)
        if self.counters.replans >= max_replans:
            self.state = WatchdogState.OWNER_INPUT_REQUIRED
            return False

        self.counters.replans += 1
        self.counters.consecutive_no_progress_count = 0
        self.state = WatchdogState.ACTIVE
        return True

    # ------------------------------------------------------------------
    # File Reading & Dedup Control
    # ------------------------------------------------------------------

    def authorize_file_read(
        self,
        file_path: str,
        content_hash: str,
        line_range: str = "ALL",
        reason: str = "Inspection",
    ) -> tuple[bool, str]:
        """Authorize file read or reject if limits/traversal/duplicate rules violated."""
        self._check_critical_budgets()
        if self.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.TIMEOUT}:
            return False, f"Cannot read file: watchdog state is {self.state.value}"

        # Path safety check
        norm_path = file_path.replace("\\", "/").strip()
        if ".." in norm_path or norm_path.startswith(("/", "\\")):
            return False, f"Path traversal rejected: {file_path}"
        if any(
            seg in norm_path for seg in [".env", ".git", "node_modules", ".venv", "data/sources"]
        ):
            return False, f"Access to excluded/sensitive path rejected: {file_path}"

        # Check duplicate unchanged read
        if self.ledger.check_duplicate_read(norm_path, content_hash, line_range):
            self.ledger.duplicate_reads_prevented += 1
            return False, "DUPLICATE_READ_PREVENTED: Unchanged file and line range already read"

        # Check repeated read limit for this specific file
        rep_count = self.ledger.get_repeated_reads_count(norm_path)
        max_rep = self.get_effective_limit(
            "max_repeated_reads_per_file", self.profile.max_repeated_reads_per_file
        )
        if rep_count >= max_rep:
            return False, f"Repeated read ceiling ({max_rep}) reached for '{file_path}'"

        # Check unique files limit if this is a new file
        if norm_path not in {r.file_path for r in self.ledger.file_reads}:
            unique_count = self.ledger.get_unique_files_read_count()
            max_unique = self.get_effective_limit(
                "max_unique_files_read", self.profile.max_unique_files_read
            )
            if unique_count >= max_unique:
                self.state = WatchdogState.BUDGET_EXCEEDED
                return False, f"Unique files read ceiling ({max_unique}) reached"

        # Record approved read
        self.ledger.record_file_read(
            file_path=norm_path,
            content_hash=content_hash,
            line_range=line_range,
            reason=reason,
            iteration=self.counters.analysis_iterations,
        )
        return True, "AUTHORIZED"

    # ------------------------------------------------------------------
    # Tool Call & Deduplication Control
    # ------------------------------------------------------------------

    def authorize_tool_call(
        self,
        tool_name: str,
        target: str,
        arguments: dict[str, Any],
        current_file_hashes: dict[str, str] | None = None,
    ) -> tuple[bool, str, ActionRecord | None]:
        """Authorize tool call or detect duplicate action to reuse previous result."""
        self._check_critical_budgets()
        if self.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.TIMEOUT}:
            return False, f"Tool call blocked: watchdog state is {self.state.value}", None

        max_tools = self.get_effective_limit("max_tool_calls", self.profile.max_tool_calls)
        if self.counters.tool_calls >= max_tools:
            self.state = WatchdogState.BUDGET_EXCEEDED
            return False, "Tool call limit reached", None

        # Compute arguments hash
        arg_hash = self.ledger.compute_action_hash(tool_name, target, arguments)
        f_hashes = current_file_hashes or {}

        # Check for equivalent action
        prev = self.ledger.find_equivalent_action(
            action_type=tool_name,
            target=target,
            arg_hash=arg_hash,
            current_git_head=self.git_head,
            current_file_hashes=f_hashes,
        )

        if prev:
            if prev.status == ActionStatus.SUCCESS:
                self.ledger.duplicate_actions_prevented += 1
                return False, "DUPLICATE_ACTION_REUSED: Prior successful result available", prev
            elif prev.status == ActionStatus.FAILED and not prev.retryable:
                self.state = WatchdogState.REPLAN_REQUIRED
                return (
                    False,
                    "FAILED_EQUIVALENT_ACTION: Identical failure without state change",
                    prev,
                )

        self.counters.tool_calls += 1
        self._check_critical_budgets()
        return True, "AUTHORIZED", None

    def record_action_result(
        self,
        action_id: str,
        tool_name: str,
        target: str,
        arguments: dict[str, Any],
        status: ActionStatus,
        result_fingerprint: str,
        evidence_summary: str,
        duration_ms: int = 0,
        relevant_file_hashes: dict[str, str] | None = None,
        retryable: bool = False,
        failure_classification: FailureClassification = FailureClassification.NONE,
    ) -> ActionRecord:
        """Record completed action in ledger without sensitive tokens."""
        now_iso = datetime.now(UTC).isoformat()
        rec = ActionRecord(
            action_id=action_id,
            task_id=self.task_id,
            action_type=tool_name,
            target=target,
            normalized_arguments_hash=self.ledger.compute_action_hash(tool_name, target, arguments),
            git_head=self.git_head,
            relevant_file_hashes=relevant_file_hashes or {},
            start_time=now_iso,
            end_time=now_iso,
            duration_ms=duration_ms,
            status=status,
            result_fingerprint=result_fingerprint,
            evidence_summary=evidence_summary[:200],  # bounded evidence summary
            budget_delta={},
            retryable=retryable,
            failure_classification=failure_classification,
        )
        self.ledger.record_action(rec)
        return rec

    # ------------------------------------------------------------------
    # Scope & Modification Control
    # ------------------------------------------------------------------

    def authorize_file_modification(self, file_path: str) -> tuple[bool, str]:
        """Verify modification is authorized within approved scope and limits."""
        self._check_critical_budgets()
        if self.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.TIMEOUT}:
            return False, f"Modification blocked: watchdog state is {self.state.value}"

        norm_path = file_path.replace("\\", "/").strip()

        # Reject path traversal or protected paths
        if ".." in norm_path or any(
            seg in norm_path for seg in [".env", ".git", "node_modules", ".venv"]
        ):
            return False, f"Modification of protected/traversal path rejected: {file_path}"

        # Scope enforcement
        if self.approved_files and norm_path not in self.approved_files:
            self.state = WatchdogState.SCOPE_EXPANSION_REQUIRED
            return (
                False,
                f"SCOPE_EXPANSION_REQUIRED: File '{file_path}' is not in approved scope",
            )

        max_files = self.get_effective_limit("max_files_modified", self.profile.max_files_modified)
        if norm_path not in self.counters.files_modified:
            if len(self.counters.files_modified) >= max_files:
                self.state = WatchdogState.BUDGET_EXCEEDED
                return False, f"Max modified files limit ({max_files}) reached"
            self.counters.files_modified.add(norm_path)

        return True, "AUTHORIZED"

    def record_patch_applied(self, lines_added: int = 0, lines_removed: int = 0) -> bool:
        """Track patch execution and enforce patch count limits."""
        max_patches = self.get_effective_limit("max_patch_count", self.profile.max_patch_count)
        self.counters.patch_count += 1
        self.counters.lines_added += lines_added
        self.counters.lines_removed += lines_removed

        if self.counters.patch_count > max_patches:
            self.state = WatchdogState.BUDGET_EXCEEDED
            return False

        self._check_critical_budgets()
        return True

    # ------------------------------------------------------------------
    # Test Execution & Failure Fingerprinting
    # ------------------------------------------------------------------

    def authorize_test_execution(self, is_full_regression: bool = False) -> tuple[bool, str]:
        """Check test execution allowance."""
        self._check_critical_budgets()
        if self.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.TIMEOUT}:
            return False, f"Test blocked: watchdog state is {self.state.value}"

        if is_full_regression:
            max_reg = self.get_effective_limit(
                "max_full_regression_runs", self.profile.max_full_regression_runs
            )
            if self.counters.full_regression_runs >= max_reg:
                return False, f"Full regression limit ({max_reg}) reached"
            self.counters.full_regression_runs += 1
        else:
            max_tests = self.get_effective_limit(
                "max_targeted_test_runs", self.profile.max_targeted_test_runs
            )
            if self.counters.targeted_test_runs >= max_tests:
                self.state = WatchdogState.BUDGET_EXCEEDED
                return False, f"Targeted test limit ({max_tests}) reached"
            self.counters.targeted_test_runs += 1

        self._check_critical_budgets()
        return True, "AUTHORIZED"

    def record_test_result(
        self,
        exit_code: int,
        failure_fingerprint: str | None = None,
        classification: FailureClassification = FailureClassification.NONE,
    ) -> None:
        """Record test outcome and detect repeated failure fingerprints."""
        if exit_code == 0:
            self.counters.identical_test_retries = 0
            self.last_progress_event = "Targeted tests passed"
            return

        if failure_fingerprint:
            # Check if identical failure was repeated consecutively
            if self.failure_fingerprints and self.failure_fingerprints[-1] == failure_fingerprint:
                self.counters.identical_test_retries += 1
                max_retries = self.get_effective_limit(
                    "max_identical_test_retries", self.profile.max_identical_test_retries
                )
                if self.counters.identical_test_retries > max_retries:
                    self.state = WatchdogState.REPLAN_REQUIRED
                    return

            self.failure_fingerprints.append(failure_fingerprint)

    # ------------------------------------------------------------------
    # Model Calls, Token & Cost Metering
    # ------------------------------------------------------------------

    def record_model_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float = 0.0,
    ) -> None:
        """Meter model usage once and enforce ceilings."""
        self.counters.model_calls += 1
        self.counters.prompt_tokens += prompt_tokens
        self.counters.completion_tokens += completion_tokens
        self.counters.cost_usd += cost_usd

        self._check_critical_budgets()

    # ------------------------------------------------------------------
    # Project Owner Overrides
    # ------------------------------------------------------------------

    def apply_owner_override(self, override: OwnerBudgetOverride) -> None:
        """Apply explicit owner override for a named budget."""
        if override.task_id != self.task_id:
            raise ValueError(
                f"Override task_id '{override.task_id}' does not match active '{self.task_id}'"
            )

        # Ensure duration does not exceed absolute global maximum without explicit notation
        if override.budget_name == "max_duration_seconds":
            if (
                override.new_value > GLOBAL_MAX_DURATION_SECONDS
                and "force" not in override.reason.lower()
            ):
                raise ValueError(
                    f"Override exceeds {GLOBAL_MAX_DURATION_SECONDS}s ceiling without 'force'"
                )

        self.overrides.append(override)
        if override.additional_scope:
            self.approved_files.update(override.additional_scope)

        # Clear budget exceeded state if relevant budget was expanded
        if self.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.SCOPE_EXPANSION_REQUIRED}:
            self.state = WatchdogState.ACTIVE

    # ------------------------------------------------------------------
    # Checkpointing & Serialization
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        remaining_work: list[str] | None = None,
        test_summary: dict[str, Any] | None = None,
    ) -> TaskCheckpoint:
        """Serialize current execution state into clean, secure checkpoint."""
        return TaskCheckpoint(
            task_id=self.task_id,
            task_class=self.task_class.value,
            git_head=self.git_head,
            state=self.state,
            start_time=self.start_time_iso,
            duration_seconds=self.get_elapsed_seconds(),
            counters={
                "analysis_iterations": self.counters.analysis_iterations,
                "replans": self.counters.replans,
                "files_modified": sorted(self.counters.files_modified),
                "patch_count": self.counters.patch_count,
                "lines_added": self.counters.lines_added,
                "lines_removed": self.counters.lines_removed,
                "targeted_test_runs": self.counters.targeted_test_runs,
                "tool_calls": self.counters.tool_calls,
                "model_calls": self.counters.model_calls,
                "prompt_tokens": self.counters.prompt_tokens,
                "completion_tokens": self.counters.completion_tokens,
                "total_tokens": self.counters.total_tokens,
                "cost_usd": self.counters.cost_usd,
            },
            approved_files=sorted(self.approved_files),
            failure_fingerprints=list(self.failure_fingerprints),
            test_summary=test_summary or {},
            remaining_work=remaining_work or [],
            overrides=[asdict(o) for o in self.overrides],
            warnings=[asdict(w) for w in self.warnings],
        )

    def save_checkpoint_file(self, checkpoint_path: Path) -> Path:
        """Write checkpoint to JSON file safely."""
        cp = self.create_checkpoint()
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")
        return checkpoint_path
