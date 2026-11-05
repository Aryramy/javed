"""__init__.py — JAVED Coding-Agent Efficiency & Execution Watchdog Module."""

from javed.agent.efficiency.briefs import (
    EvidenceItem,
    EvidenceType,
    PreEditBrief,
    RootCauseConfidence,
    TargetLineRange,
    TaskType,
)
from javed.agent.efficiency.budgets import (
    DEFAULT_BUDGET_PROFILES,
    GLOBAL_MAX_DURATION_SECONDS,
    TaskBudgetProfile,
    TaskClass,
    get_budget_profile,
)
from javed.agent.efficiency.gate import (
    ApprovalStatus,
    BriefApprovalRecord,
    PreEditGate,
    WriteAuthorizationDecision,
    WriteAuthorizationResult,
    WriteOperation,
)
from javed.agent.efficiency.ledger import (
    ActionLedger,
    ActionRecord,
    ActionStatus,
    FailureClassification,
    FileReadRecord,
)
from javed.agent.efficiency.subprocess_control import (
    SUBPROCESS_TIMEOUTS,
    SubprocessResult,
    get_timeout_for_category,
    run_bounded_subprocess,
    terminate_process_tree,
)
from javed.agent.efficiency.watchdog import (
    BudgetWarningEvent,
    ExecutionCounters,
    OwnerBudgetOverride,
    TaskCheckpoint,
    WatchdogEngine,
    WatchdogState,
)

__all__ = [
    "DEFAULT_BUDGET_PROFILES",
    "GLOBAL_MAX_DURATION_SECONDS",
    "ActionLedger",
    "ActionRecord",
    "ActionStatus",
    "ApprovalStatus",
    "BriefApprovalRecord",
    "BudgetWarningEvent",
    "EvidenceItem",
    "EvidenceType",
    "ExecutionCounters",
    "FailureClassification",
    "FileReadRecord",
    "OwnerBudgetOverride",
    "PreEditBrief",
    "PreEditGate",
    "RootCauseConfidence",
    "SUBPROCESS_TIMEOUTS",
    "SubprocessResult",
    "TargetLineRange",
    "TaskBudgetProfile",
    "TaskCheckpoint",
    "TaskClass",
    "TaskType",
    "WatchdogEngine",
    "WatchdogState",
    "WriteAuthorizationDecision",
    "WriteAuthorizationResult",
    "WriteOperation",
    "get_budget_profile",
    "get_timeout_for_category",
    "run_bounded_subprocess",
    "terminate_process_tree",
]
