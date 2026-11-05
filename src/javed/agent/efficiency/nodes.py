"""nodes.py — Modular LangGraph workflow node implementations for JAVED.

Encapsulates the discrete roles:
- IntakeNode
- RepositoryOrientationNode
- RootCauseOrDesignNode
- PlannerNode
- PlanGateNode
- CoderNode
- ReviewerNode
- TesterNode
- FinalReviewerNode
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from javed.agent.efficiency.briefs import (
    PreEditBrief,
    TaskType,
)
from javed.agent.efficiency.budgets import TaskClass
from javed.agent.efficiency.contracts import (
    FinalReviewerOutcome,
    FinalReviewerOutput,
    PlannerOutput,
    ReviewerOutcome,
    ReviewerOutput,
    TesterOutput,
)
from javed.agent.efficiency.gate import (
    ApprovalStatus,
    PreEditGate,
    WriteAuthorizationDecision,
    WriteOperation,
)
from javed.agent.efficiency.ledger import (
    ActionLedger,
    ActionRecord,
    ActionStatus,
    FailureClassification,
)
from javed.agent.efficiency.state import CodingTaskState, WorkflowState
from javed.agent.efficiency.watchdog import WatchdogEngine, WatchdogState


class IntakeNode:
    """Validates task ID, classifies task, initializes watchdog budget, records HEAD."""

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        state.increment_visit("intake")

        # 1. Validate task ID
        if not state.task_id.strip() or len(state.task_id) < 3:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = "Invalid or empty task_id"
            return state

        # 2. Validate / normalize task type
        try:
            t_type = TaskType(state.task_type)
        except ValueError:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = f"Unsupported task_type: {state.task_type}"
            return state

        # 3. Classify budget profile
        if t_type == TaskType.DOCUMENTATION:
            state.task_class = TaskClass.DOCUMENTATION
        elif t_type == TaskType.SECURITY_FIX:
            state.task_class = TaskClass.SECURITY_SENSITIVE
        elif t_type in {TaskType.MIGRATION, TaskType.FEATURE}:
            state.task_class = TaskClass.FRONTEND_BACKEND_CONTRACT
        elif t_type == TaskType.REFACTOR:
            state.task_class = TaskClass.ARCHITECTURE_CHANGE
        else:
            state.task_class = TaskClass.SINGLE_FILE_DEFECT

        # 4. Checkpoint
        state.current_state = WorkflowState.REPOSITORY_ORIENTATION
        state.budget_counters = asdict(watchdog.counters)
        state.checkpoint_reference = watchdog.create_checkpoint()

        if ledger:
            ledger.record_action(
                ActionRecord(
                    action_id=f"act-intake-{state.task_id}",
                    task_id=state.task_id,
                    action_type="intake_validation",
                    target=state.task_id,
                    normalized_arguments_hash=ledger.compute_action_hash(
                        "intake", state.task_id, {"type": state.task_type}
                    ),
                    git_head=state.repository_head,
                    relevant_file_hashes={},
                    start_time=datetime.now(UTC).isoformat(),
                    end_time=datetime.now(UTC).isoformat(),
                    duration_ms=2,
                    status=ActionStatus.SUCCESS,
                    result_fingerprint="fp-intake-ok",
                    evidence_summary=f"Task classified as {state.task_class.value}",
                    budget_delta={},
                    retryable=False,
                )
            )

        return state


class RepositoryOrientationNode:
    """Extracts task anchors and queries Graphify knowledge graph within bounded limits."""

    def __init__(self, query_fn: Callable[..., Any] | None = None) -> None:
        self.query_fn = query_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        state.increment_visit("repository_orientation")

        # Hard limits check
        if watchdog.state in {WatchdogState.BUDGET_EXCEEDED, WatchdogState.TIMEOUT}:
            state.current_state = WorkflowState.BUDGET_EXCEEDED
            return state

        # Produce bounded repository context
        repo_ctx: dict[str, Any] = {
            "owning_files": [],
            "symbols": [],
            "callers": [],
            "tests": [],
            "query_count": 0,
        }

        if self.query_fn:
            result = self.query_fn(state.objective)
            repo_ctx.update(result)
        else:
            # Safe default fallback for tests
            repo_ctx["owning_files"] = [f for f in state.approved_files][:12]
            repo_ctx["query_count"] = 1

        # Enforce bounds: max 12 files, max 30 symbols, max 12 tests
        repo_ctx["owning_files"] = repo_ctx["owning_files"][:12]
        if "symbols" in repo_ctx:
            repo_ctx["symbols"] = repo_ctx["symbols"][:30]
        if "tests" in repo_ctx:
            repo_ctx["tests"] = repo_ctx["tests"][:12]

        state.repository_context = repo_ctx
        state.graph_freshness = "FRESH"
        state.current_state = WorkflowState.ROOT_CAUSE_OR_DESIGN
        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class RootCauseOrDesignNode:
    """Produces the structured Pre-Edit Brief according to task type rules."""

    def __init__(self, brief_generator_fn: Callable[..., PreEditBrief] | None = None) -> None:
        self.brief_generator_fn = brief_generator_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        state.increment_visit("root_cause_or_design")

        # Generate or assign brief
        if self.brief_generator_fn:
            state.pre_edit_brief = self.brief_generator_fn(state)

        if state.pre_edit_brief is None:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = "No Pre-Edit Brief generated"
            return state

        # Validate brief structure fail-closed
        valid, errors = state.pre_edit_brief.validate_structure()
        if not valid:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = f"Brief structure invalid: {'; '.join(errors)}"
            return state

        state.brief_hash = state.pre_edit_brief.compute_brief_hash()
        state.approved_files = list(state.pre_edit_brief.files_to_modify)
        state.approved_symbols = list(state.pre_edit_brief.affected_symbols)

        # Investigation task check: cannot proceed to coding
        if state.pre_edit_brief.task_type == TaskType.INVESTIGATION:
            state.current_state = WorkflowState.FINAL_REVIEW
            state.remaining_work = []
            return state

        state.current_state = WorkflowState.PLANNING
        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class PlannerNode:
    """Read-only planner establishing exact implementation steps and target ranges."""

    def __init__(self, plan_fn: Callable[..., PlannerOutput] | None = None) -> None:
        self.plan_fn = plan_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        visits = state.increment_visit("planner")
        if visits > 2:
            state.current_state = WorkflowState.OWNER_INPUT_REQUIRED
            state.stop_reason = "Planner visit limit exceeded (max 2)"
            return state

        if self.plan_fn:
            out = self.plan_fn(state)
            state.implementation_plan = [{"step": s} for s in out.implementation_steps]
            state.test_plan = list(out.test_sequence)
        else:
            state.implementation_plan = [
                {"step": f"Implement changes for {f}"} for f in state.approved_files
            ]
            state.test_plan = ["pytest tests/test_target.py -v"]

        state.current_state = WorkflowState.PLAN_GATE
        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class PlanGateNode:
    """Evaluates brief approval, repository head, file hash, and budget alignment."""

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        state.increment_visit("plan_gate")

        if state.pre_edit_brief is None:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = "Missing Pre-Edit Brief at Plan Gate"
            return state

        # Evaluate approval via PreEditGate
        approval, errors = PreEditGate.approve_brief(state.pre_edit_brief)
        if approval is None:
            state.current_state = WorkflowState.REPLAN_REQUIRED
            state.replan_count += 1
            state.stop_reason = f"Gate rejected brief: {'; '.join(errors)}"
            return state

        # Verify Git HEAD consistency
        if approval.repository_head != state.repository_head:
            state.current_state = WorkflowState.FAILED
            state.stop_reason = "Stale Git HEAD at Plan Gate"
            return state

        state.approval_record = approval
        state.approval_id = approval.approval_id
        state.approval_status = ApprovalStatus.APPROVED
        state.current_state = WorkflowState.CODING
        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class CoderNode:
    """Produces the authorized code modification under strict gate supervision."""

    def __init__(self, code_fn: Callable[..., Any] | None = None) -> None:
        self.code_fn = code_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        visits = state.increment_visit("coder")
        if visits > 3:
            state.current_state = WorkflowState.REPLAN_REQUIRED
            state.stop_reason = "Coder visit limit exceeded (max 3)"
            return state

        # Verify write authorization for each target file before writing
        for target_file in state.approved_files:
            auth_res = PreEditGate.authorize_write(
                watchdog=watchdog,
                brief=state.pre_edit_brief,
                approval=state.approval_record,
                relative_path=target_file,
                operation=WriteOperation.MODIFY,
            )
            if not auth_res.allowed:
                if auth_res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED:
                    state.current_state = WorkflowState.SCOPE_EXPANSION_REQUIRED
                else:
                    state.current_state = WorkflowState.FAILED
                state.stop_reason = auth_res.reason
                return state

        # Execute coding function or mock patch
        if self.code_fn:
            patch_res = self.code_fn(state)
            state.patch_summary = patch_res
            state.current_diff_reference = patch_res.get("diff_ref", "diff_mock")
        else:
            state.patch_summary = {
                "files": state.approved_files,
                "lines_added": 5,
                "lines_removed": 2,
            }
            state.current_diff_reference = f"diff_{state.task_id}_v{visits}"

        # Record patch in watchdog
        watchdog.counters.patch_count += 1
        for f in state.approved_files:
            watchdog.counters.files_modified.add(f)

        state.current_state = WorkflowState.REVIEW
        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class ReviewerNode:
    """Independent reviewer evaluating patch against declared objective and boundaries."""

    def __init__(self, review_fn: Callable[..., ReviewerOutput] | None = None) -> None:
        self.review_fn = review_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        visits = state.increment_visit("reviewer")
        if visits > 2:
            state.current_state = WorkflowState.REPLAN_REQUIRED
            state.stop_reason = "Reviewer visit limit exceeded (max 2)"
            return state

        if self.review_fn:
            out = self.review_fn(state)
        else:
            out = ReviewerOutput(
                outcome=ReviewerOutcome.APPROVED,
                findings=[],
                notes=["Patch adheres strictly to declared boundaries."],
                complexity_score=1,
                unrelated_changes_detected=False,
                security_boundary_intact=True,
                public_contracts_intact=True,
            )

        state.review_status = out.outcome.value
        state.reviewer_findings = out.findings
        state.review_notes = out.notes

        if out.outcome in {ReviewerOutcome.APPROVED, ReviewerOutcome.APPROVED_WITH_NOTES}:
            state.current_state = WorkflowState.TARGETED_TESTING
        elif out.outcome == ReviewerOutcome.CHANGES_REQUIRED:
            if state.get_visit_count("coder") >= 3:
                state.current_state = WorkflowState.REPLAN_REQUIRED
            else:
                state.current_state = WorkflowState.CODING
        elif out.outcome == ReviewerOutcome.REPLAN_REQUIRED:
            state.current_state = WorkflowState.PLANNING
        else:
            state.current_state = WorkflowState.FAILED

        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class TesterNode:
    """Executes the approved test plan and classifies failures."""

    __test__ = False

    def __init__(self, test_runner_fn: Callable[..., TesterOutput] | None = None) -> None:
        self.test_runner_fn = test_runner_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        visits = state.increment_visit("tester")
        if visits > 3:
            state.current_state = WorkflowState.REPLAN_REQUIRED
            state.stop_reason = "Tester visit limit exceeded (max 3)"
            return state

        if self.test_runner_fn:
            out = self.test_runner_fn(state)
        else:
            out = TesterOutput(
                tests_executed=state.test_plan,
                passed_count=len(state.test_plan),
                failed_count=0,
                exit_code=0,
                safe_summary="All tests passed successfully",
                failure_fingerprints=[],
                failure_classification=FailureClassification.NONE,
                retryable=False,
            )

        # Record test results
        result_dict = asdict(out)
        result_dict["failure_classification"] = out.failure_classification.value
        state.test_results.append(result_dict)

        if out.failure_fingerprints:
            for fp in out.failure_fingerprints:
                state.failure_fingerprints.append(fp)

        # Update watchdog test count
        watchdog.counters.targeted_test_runs += 1

        if out.exit_code == 0:
            state.current_state = WorkflowState.FINAL_REVIEW
        else:
            # Identical failure check
            fps = state.failure_fingerprints
            if len(fps) >= 2 and fps[-1] == fps[-2] and fps[-1] != "":
                state.current_state = WorkflowState.REPLAN_REQUIRED
                state.stop_reason = f"Identical failure loop detected: {fps[-1]}"
            elif out.failure_classification == FailureClassification.ENVIRONMENT_FAILURE:
                state.current_state = WorkflowState.OWNER_INPUT_REQUIRED
                state.stop_reason = "Environment failure requires owner intervention"
            else:
                state.current_state = WorkflowState.CODING

        state.checkpoint_reference = watchdog.create_checkpoint()
        return state


class FinalReviewerNode:
    """Final gatekeeper verifying repository status, budget hygiene, and documentation."""

    def __init__(self, final_review_fn: Callable[..., FinalReviewerOutput] | None = None) -> None:
        self.final_review_fn = final_review_fn

    def __call__(
        self, state: CodingTaskState, watchdog: WatchdogEngine, ledger: ActionLedger | None = None
    ) -> CodingTaskState:
        state.increment_visit("final_reviewer")

        if self.final_review_fn:
            out = self.final_review_fn(state)
        else:
            out = FinalReviewerOutput(
                outcome=FinalReviewerOutcome.FINAL_APPROVED,
                clean_working_tree_verified=True,
                unresolved_findings_count=0,
                documentation_consistent=True,
                resource_hygiene_verified=True,
                summary="All quality gates, tests, and budget limits verified.",
            )

        state.final_decision = out.outcome.value
        if out.outcome in {
            FinalReviewerOutcome.FINAL_APPROVED,
            FinalReviewerOutcome.FINAL_APPROVED_WITH_NOTES,
        }:
            state.current_state = WorkflowState.COMPLETED
            watchdog.state = WatchdogState.COMPLETED
        else:
            state.current_state = WorkflowState.FAILED

        state.checkpoint_reference = watchdog.create_checkpoint()
        return state
