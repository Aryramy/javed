"""routing.py — Deterministic conditional routing functions for JAVED workflow.

Evaluates transitions across:
- Plan Gate outcomes
- Reviewer outcomes
- Tester outcomes
- Final Reviewer outcomes
- Watchdog budget warnings, limits, timeouts, and stalls
- Loop-prevention and anti-thrashing circuit breakers
"""

from __future__ import annotations

from javed.agent.efficiency.contracts import (
    FinalReviewerOutcome,
    ReviewerOutcome,
)
from javed.agent.efficiency.ledger import FailureClassification
from javed.agent.efficiency.state import CodingTaskState, WorkflowState
from javed.agent.efficiency.watchdog import WatchdogState


def route_from_plan_gate(state: CodingTaskState) -> str:
    """Conditional router following Plan Gate evaluation."""
    # 1. Watchdog and cancellation checks take absolute precedence
    if state.cancellation_requested or state.watchdog_state == WatchdogState.CANCELLED:
        return WorkflowState.CANCELLED.value
    if state.watchdog_state == WatchdogState.BUDGET_EXCEEDED:
        return WorkflowState.BUDGET_EXCEEDED.value
    if state.watchdog_state == WatchdogState.TIMEOUT:
        return WorkflowState.TIMEOUT.value

    # 2. Gate Decision routing
    if state.current_state == WorkflowState.PLAN_GATE:
        # Check plan approval status
        if state.approval_status.value == "APPROVED" and state.approval_id:
            return WorkflowState.CODING.value
        if state.current_state == WorkflowState.SCOPE_EXPANSION_REQUIRED:
            return WorkflowState.SCOPE_EXPANSION_REQUIRED.value
        if state.replan_count >= 2:
            return WorkflowState.OWNER_INPUT_REQUIRED.value
        return WorkflowState.REPLAN_REQUIRED.value

    return state.current_state.value


def route_from_reviewer(state: CodingTaskState) -> str:
    """Conditional router following independent Reviewer evaluation."""
    if state.cancellation_requested or state.watchdog_state == WatchdogState.CANCELLED:
        return WorkflowState.CANCELLED.value
    if state.watchdog_state == WatchdogState.BUDGET_EXCEEDED:
        return WorkflowState.BUDGET_EXCEEDED.value

    # Outcome evaluation
    rev_status = state.review_status
    if rev_status in {ReviewerOutcome.APPROVED.value, ReviewerOutcome.APPROVED_WITH_NOTES.value}:
        return WorkflowState.TARGETED_TESTING.value

    # Changes required - check revision cycles (max 2)
    coder_visits = state.get_visit_count("coder")
    if rev_status == ReviewerOutcome.CHANGES_REQUIRED.value:
        if coder_visits >= 3:  # Initial + 2 revisions
            return WorkflowState.REPLAN_REQUIRED.value
        return WorkflowState.CODING.value

    if rev_status == ReviewerOutcome.REPLAN_REQUIRED.value:
        if state.replan_count >= 2:
            return WorkflowState.OWNER_INPUT_REQUIRED.value
        return WorkflowState.PLANNING.value

    if rev_status == ReviewerOutcome.REJECTED.value:
        return WorkflowState.FAILED.value

    return WorkflowState.FAILED.value


def route_from_tester(state: CodingTaskState) -> str:
    """Conditional router following Tester evaluation."""
    if state.cancellation_requested or state.watchdog_state == WatchdogState.CANCELLED:
        return WorkflowState.CANCELLED.value
    if state.watchdog_state == WatchdogState.BUDGET_EXCEEDED:
        return WorkflowState.BUDGET_EXCEEDED.value

    # Check identical failure fingerprint circuit
    fps = state.failure_fingerprints
    if len(fps) >= 2 and fps[-1] == fps[-2] and fps[-1] != "":
        # Identical failure twice in a row without progress -> Replan or Owner
        if state.replan_count >= 2:
            return WorkflowState.OWNER_INPUT_REQUIRED.value
        return WorkflowState.REPLAN_REQUIRED.value

    # Check latest test results
    if state.test_results:
        latest = state.test_results[-1]
        exit_code = latest.get("exit_code", 1)
        fail_class = latest.get("failure_classification", "")

        if exit_code == 0:
            # Targeted tests passed; proceed to regression testing if declared, else final review
            if (
                state.current_state == WorkflowState.TARGETED_TESTING
                and state.get_visit_count("regression_testing") == 0
                and "full_regression" in state.test_plan
            ):
                return WorkflowState.REGRESSION_TESTING.value
            return WorkflowState.FINAL_REVIEW.value

        # Tests failed
        if fail_class == FailureClassification.ENVIRONMENT_FAILURE.value:
            # Environment failure -> do NOT patch code, route to Owner or Replan
            return WorkflowState.OWNER_INPUT_REQUIRED.value

        if fail_class == FailureClassification.OUTDATED_TEST_CONTRACT.value:
            return WorkflowState.PLANNING.value

        # Patch defect: route back to Coder if revision cycles remain
        if state.get_visit_count("coder") < 3:
            return WorkflowState.CODING.value
        return WorkflowState.REPLAN_REQUIRED.value

    return WorkflowState.FINAL_REVIEW.value


def route_from_final_reviewer(state: CodingTaskState) -> str:
    """Conditional router following Final Reviewer evaluation."""
    if state.cancellation_requested or state.watchdog_state == WatchdogState.CANCELLED:
        return WorkflowState.CANCELLED.value

    if state.final_decision in {
        FinalReviewerOutcome.FINAL_APPROVED.value,
        FinalReviewerOutcome.FINAL_APPROVED_WITH_NOTES.value,
    }:
        return WorkflowState.COMPLETED.value

    if state.final_decision == FinalReviewerOutcome.OWNER_INPUT_REQUIRED.value:
        return WorkflowState.OWNER_INPUT_REQUIRED.value

    return WorkflowState.FAILED.value
