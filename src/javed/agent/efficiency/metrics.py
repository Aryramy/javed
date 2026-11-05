"""metrics.py — Minimal task execution metrics and performance summary for JAVED.

Strict boundaries:
- Stores strictly aggregated execution numbers, audit identifiers, and verdicts.
- NEVER stores prompts, chain-of-thought, source contents, diffs, secrets,
  uploaded documents, or raw model payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from javed.agent.efficiency.budgets import TaskClass
from javed.agent.efficiency.state import CodingTaskState
from javed.agent.efficiency.watchdog import WatchdogEngine


@dataclass(frozen=True)
class TaskMetricsReport:
    """Minimal, auditable execution metrics proving agent efficiency."""

    task_id: str
    task_class: str
    elapsed_seconds: float
    files_read_count: int
    repeated_reads_prevented: int
    files_modified_count: int
    lines_added: int
    lines_removed: int
    graphify_queries: int
    tool_calls: int
    patch_count: int
    targeted_test_runs: int
    full_regression_runs: int
    test_failures_count: int
    reviewer_cycles: int
    model_calls: int
    total_tokens: int
    total_cost_usd: float
    watchdog_state: str
    final_result: str
    stop_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary ensuring zero secret or source exposure."""
        return asdict(self)

    @classmethod
    def collect(
        cls,
        state: CodingTaskState,
        watchdog: WatchdogEngine,
    ) -> TaskMetricsReport:
        """Extract bounded task metrics from state and watchdog engine."""
        counters = watchdog.counters
        ledger = watchdog.ledger

        # Reviewer cycles: number of times reviewer node was invoked
        rev_cycles = state.get_visit_count("reviewer")

        # Test failures count: sum of failed test runs in recorded test results
        test_fails = sum(1 for res in state.test_results if res.get("exit_code", 0) != 0)

        return cls(
            task_id=state.task_id,
            task_class=state.task_class.value
            if isinstance(state.task_class, TaskClass)
            else str(state.task_class),
            elapsed_seconds=round(watchdog.get_elapsed_seconds(), 2),
            files_read_count=ledger.get_unique_files_read_count(),
            repeated_reads_prevented=ledger.duplicate_reads_prevented,
            files_modified_count=len(counters.files_modified),
            lines_added=counters.lines_added,
            lines_removed=counters.lines_removed,
            graphify_queries=state.repository_context.get("query_count", 0),
            tool_calls=counters.tool_calls,
            patch_count=counters.patch_count,
            targeted_test_runs=counters.targeted_test_runs,
            full_regression_runs=counters.full_regression_runs,
            test_failures_count=test_fails,
            reviewer_cycles=rev_cycles,
            model_calls=counters.model_calls,
            total_tokens=counters.total_tokens,
            total_cost_usd=round(counters.cost_usd, 4),
            watchdog_state=watchdog.state.value,
            final_result=state.final_decision
            if state.final_decision != "PENDING"
            else state.current_state.value,
            stop_reason=state.stop_reason,
        )
