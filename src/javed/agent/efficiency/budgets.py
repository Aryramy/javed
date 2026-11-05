"""budgets.py — Task-class budget profiles, constraints, and validation for JAVED.

Defines the six canonical task classes, their default budget profiles, metric definitions,
and validation logic ensuring budgets are positive, bounded, and immutable without explicit
owner authorization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class TaskClass(StrEnum):
    """Canonical task classes governing execution limits."""

    DOCUMENTATION = "documentation"
    SINGLE_FILE_DEFECT = "single_file_defect"
    MULTI_FILE_DEFECT = "multi_file_defect"
    FRONTEND_BACKEND_CONTRACT = "frontend_backend_contract"
    SECURITY_SENSITIVE = "security_sensitive"
    ARCHITECTURE_CHANGE = "architecture_change"


# Absolute upper ceiling for any task class without explicit owner override (60 minutes)
GLOBAL_MAX_DURATION_SECONDS: int = 3600


@dataclass(frozen=True)
class TaskBudgetProfile:
    """Immutable budget profile for a specific task class."""

    task_class: TaskClass
    max_duration_seconds: int
    max_analysis_iterations: int
    max_replans: int
    max_unique_files_read: int
    max_repeated_reads_per_file: int
    max_files_modified: int
    max_patch_count: int
    max_targeted_test_runs: int
    max_identical_test_retries: int
    max_full_regression_runs: int
    max_tool_calls: int
    max_model_calls: int
    max_tokens: int
    max_cost_usd: float

    def __post_init__(self) -> None:
        """Validate that all limits are positive, within hard ceilings, and logically consistent."""
        if self.max_duration_seconds <= 0:
            raise ValueError(
                f"max_duration_seconds must be positive, got {self.max_duration_seconds}"
            )
        if self.max_duration_seconds > GLOBAL_MAX_DURATION_SECONDS:
            raise ValueError(
                f"max_duration_seconds ({self.max_duration_seconds}) exceeds global ceiling "
                f"of {GLOBAL_MAX_DURATION_SECONDS}s without explicit owner override."
            )
        if self.max_analysis_iterations <= 0:
            raise ValueError("max_analysis_iterations must be positive")
        if self.max_replans < 0:
            raise ValueError("max_replans cannot be negative")
        if self.max_unique_files_read <= 0:
            raise ValueError("max_unique_files_read must be positive")
        if self.max_repeated_reads_per_file < 0:
            raise ValueError("max_repeated_reads_per_file cannot be negative")
        if self.max_files_modified <= 0:
            raise ValueError("max_files_modified must be positive")
        if self.max_patch_count <= 0:
            raise ValueError("max_patch_count must be positive")
        if self.max_targeted_test_runs < 0:
            raise ValueError("max_targeted_test_runs cannot be negative")
        if self.max_identical_test_retries < 0:
            raise ValueError("max_identical_test_retries cannot be negative")
        if self.max_full_regression_runs < 0:
            raise ValueError("max_full_regression_runs cannot be negative")
        if self.max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")
        if self.max_model_calls <= 0:
            raise ValueError("max_model_calls must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.max_cost_usd <= 0.0:
            raise ValueError("max_cost_usd must be positive")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["task_class"] = self.task_class.value
        return data


# Canonical Default Profiles
DEFAULT_BUDGET_PROFILES: dict[TaskClass, TaskBudgetProfile] = {
    TaskClass.DOCUMENTATION: TaskBudgetProfile(
        task_class=TaskClass.DOCUMENTATION,
        max_duration_seconds=900,
        max_analysis_iterations=2,
        max_replans=1,
        max_unique_files_read=8,
        max_repeated_reads_per_file=1,
        max_files_modified=8,
        max_patch_count=2,
        max_targeted_test_runs=1,
        max_identical_test_retries=1,
        max_full_regression_runs=0,
        max_tool_calls=30,
        max_model_calls=4,
        max_tokens=60000,
        max_cost_usd=0.50,
    ),
    TaskClass.SINGLE_FILE_DEFECT: TaskBudgetProfile(
        task_class=TaskClass.SINGLE_FILE_DEFECT,
        max_duration_seconds=1200,
        max_analysis_iterations=3,
        max_replans=1,
        max_unique_files_read=10,
        max_repeated_reads_per_file=2,
        max_files_modified=3,
        max_patch_count=2,
        max_targeted_test_runs=3,
        max_identical_test_retries=1,
        max_full_regression_runs=1,
        max_tool_calls=40,
        max_model_calls=6,
        max_tokens=80000,
        max_cost_usd=0.50,
    ),
    TaskClass.MULTI_FILE_DEFECT: TaskBudgetProfile(
        task_class=TaskClass.MULTI_FILE_DEFECT,
        max_duration_seconds=2100,
        max_analysis_iterations=3,
        max_replans=2,
        max_unique_files_read=20,
        max_repeated_reads_per_file=2,
        max_files_modified=10,
        max_patch_count=3,
        max_targeted_test_runs=3,
        max_identical_test_retries=1,
        max_full_regression_runs=1,
        max_tool_calls=70,
        max_model_calls=8,
        max_tokens=140000,
        max_cost_usd=1.25,
    ),
    TaskClass.FRONTEND_BACKEND_CONTRACT: TaskBudgetProfile(
        task_class=TaskClass.FRONTEND_BACKEND_CONTRACT,
        max_duration_seconds=2700,
        max_analysis_iterations=3,
        max_replans=2,
        max_unique_files_read=24,
        max_repeated_reads_per_file=2,
        max_files_modified=14,
        max_patch_count=4,
        max_targeted_test_runs=3,
        max_identical_test_retries=1,
        max_full_regression_runs=1,
        max_tool_calls=80,
        max_model_calls=8,
        max_tokens=160000,
        max_cost_usd=1.50,
    ),
    TaskClass.SECURITY_SENSITIVE: TaskBudgetProfile(
        task_class=TaskClass.SECURITY_SENSITIVE,
        max_duration_seconds=2700,
        max_analysis_iterations=3,
        max_replans=2,
        max_unique_files_read=25,
        max_repeated_reads_per_file=2,
        max_files_modified=12,
        max_patch_count=4,
        max_targeted_test_runs=3,
        max_identical_test_retries=1,
        max_full_regression_runs=1,
        max_tool_calls=80,
        max_model_calls=8,
        max_tokens=160000,
        max_cost_usd=1.50,
    ),
    TaskClass.ARCHITECTURE_CHANGE: TaskBudgetProfile(
        task_class=TaskClass.ARCHITECTURE_CHANGE,
        max_duration_seconds=3600,
        max_analysis_iterations=3,
        max_replans=2,
        max_unique_files_read=40,
        max_repeated_reads_per_file=2,
        max_files_modified=20,
        max_patch_count=5,
        max_targeted_test_runs=3,
        max_identical_test_retries=1,
        max_full_regression_runs=1,
        max_tool_calls=120,
        max_model_calls=10,
        max_tokens=250000,
        max_cost_usd=3.00,
    ),
}


def get_budget_profile(task_class: TaskClass | str) -> TaskBudgetProfile:
    """Retrieve default TaskBudgetProfile for a task class, rejecting unknown classes."""
    if isinstance(task_class, str):
        try:
            task_class = TaskClass(task_class.lower().strip())
        except ValueError as err:
            valid_classes = ", ".join(tc.value for tc in TaskClass)
            raise ValueError(
                f"Unknown task class: '{task_class}'. Valid classes: {valid_classes}"
            ) from err
    return DEFAULT_BUDGET_PROFILES[task_class]
