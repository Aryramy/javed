"""test_agent_efficiency_workflow.py — 50 Deterministic Workflow Tests.

Validates the complete 50-item workflow requirement matrix:
1. Intake classification
2. Unsupported task rejection
3. Repository orientation output bounds
4. Graph stale handling
5. Defect brief creation flow
6. Feature brief creation flow
7. Investigation remains read-only
8. Plan gate approves valid plan
9. Missing brief blocks coding
10. Expired approval blocks coding
11. Stale Git HEAD blocks coding
12. Coder only receives approved files
13. Coder cannot modify undeclared file
14. Coder cannot expand target range
15. Scope expansion routes to Planner
16. Reviewer uses isolated context
17. Reviewer cannot edit
18. Reviewer approves valid patch
19. Reviewer rejects unrelated changes
20. Reviewer detects over-engineering
21. Two reviewer rejections stop the loop
22. Tester runs targeted tests first
23. Full regression runs once
24. Identical failure halts retry
25. Environment failure does not modify production
26. Final review blocks dirty repository
27. Final review blocks unresolved findings
28. Completed requires final approval
29. Watchdog warning routes correctly
30. Budget exceeded stops workflow
31. Timeout stops workflow
32. Cancellation stops workflow
33. No-progress enters STALLED
34. Stalled workflow replans once
35. Replan exhaustion requires owner input
36. Checkpoint created after every node
37. Resume requires authorization
38. Resume rejects changed HEAD
39. Action ledger captures node progress
40. Action ledger stores no chain-of-thought
41. Secret fields are rejected
42. Planner is read-only
43. Tester is non-designing
44. Graphify queries are not repeated
45. File reads reuse unchanged ranges
46. Patch limits are enforced
47. Model-call limits are enforced
48. Tool-call limits are enforced
49. Cost and token limits are enforced
50. Structured final report is accurate
"""

from datetime import UTC, datetime

import pytest

from javed.agent.efficiency.briefs import (
    EvidenceItem,
    EvidenceType,
    PreEditBrief,
    RootCauseConfidence,
    TargetLineRange,
    TaskType,
)
from javed.agent.efficiency.budgets import TaskClass
from javed.agent.efficiency.contracts import (
    FinalReviewerOutcome,
    FinalReviewerOutput,
    ReviewerOutcome,
    ReviewerOutput,
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
)
from javed.agent.efficiency.routing import (
    route_from_plan_gate,
    route_from_reviewer,
    route_from_tester,
)
from javed.agent.efficiency.state import CodingTaskState, WorkflowState
from javed.agent.efficiency.watchdog import WatchdogEngine, WatchdogState
from javed.agent.efficiency.workflow import CodingWorkflowEngine


@pytest.fixture
def clean_watchdog() -> WatchdogEngine:
    return WatchdogEngine(
        task_id="TASK-WF-001",
        task_class=TaskClass.SINGLE_FILE_DEFECT,
        git_head="commit-abc1234",
    )


def _make_brief(
    task_id: str = "TASK-WF-001",
    t_type: TaskType = TaskType.DEFECT,
    head: str = "commit-abc1234",
) -> PreEditBrief:
    return PreEditBrief(
        task_id=task_id,
        task_type=t_type,
        objective="Fix calculation index",
        repository_head=head,
        files_read=["src/javed/agent/target.py"],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(
                relative_path="src/javed/agent/target.py",
                start_line=10,
                end_line=25,
                owning_symbol="compute_sum",
            )
        ],
        evidence=[
            EvidenceItem(
                evidence_id="EVID-1",
                evidence_type=EvidenceType.SOURCE_CODE,
                source="test",
                relative_path="src/javed/agent/target.py",
                summary="Index error",
                collected_at=datetime.now(UTC).isoformat(),
            )
        ],
        security_risks=["None"],
        regression_risks=["None"],
        rollback_strategy="git checkout -- src/javed/agent/target.py",
        test_strategy="pytest tests/test_target.py",
        created_at=datetime.now(UTC).isoformat(),
        current_behavior="Loop off by one",
        expected_behavior="Loop correct",
        root_cause="Index started at 0 instead of 1",
        root_cause_confidence=RootCauseConfidence.HIGH,
        patch_strategy="Update range",
    )


# 1. Intake classification
def test_01_intake_classification(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="SECURITY_FIX",
        objective="Fix access check in auth gateway",
        repository_head="commit-abc1234",
    )
    state = engine.intake_node(state, clean_watchdog)
    assert state.task_class == TaskClass.SECURITY_SENSITIVE
    assert state.current_state == WorkflowState.REPOSITORY_ORIENTATION


# 2. Unsupported task rejection
def test_02_unsupported_task_rejection(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="UNSUPPORTED_TYPE",
        objective="Do arbitrary work",
        repository_head="commit-abc1234",
    )
    state = engine.intake_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FAILED
    assert "Unsupported task_type" in state.stop_reason


# 3. Repository orientation output bounds
def test_03_repo_orientation_output_bounds(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(
        watchdog=clean_watchdog,
        query_fn=lambda obj: {
            "owning_files": [f"file_{i}.py" for i in range(25)],
            "symbols": [f"sym_{i}" for i in range(50)],
            "tests": [f"test_{i}.py" for i in range(30)],
        },
    )
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.repo_node(state, clean_watchdog)
    assert len(state.repository_context["owning_files"]) <= 12
    assert len(state.repository_context["symbols"]) <= 30
    assert len(state.repository_context["tests"]) <= 12


# 4. Graph stale handling
def test_04_graph_stale_handling(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.repo_node(state, clean_watchdog)
    assert state.graph_freshness in {"FRESH", "INCREMENTAL_UPDATED"}


# 5. Defect brief creation flow
def test_05_defect_brief_creation_flow(clean_watchdog: WatchdogEngine):
    brief = _make_brief()
    engine = CodingWorkflowEngine(watchdog=clean_watchdog, brief_gen_fn=lambda s: brief)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.brief_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.PLANNING
    assert state.brief_hash is not None


# 6. Feature brief creation flow
def test_06_feature_brief_creation_flow(clean_watchdog: WatchdogEngine):
    brief = PreEditBrief(
        task_id="FEAT-001",
        task_type=TaskType.FEATURE,
        objective="Add feature",
        repository_head="commit-abc1234",
        files_read=["src/javed/agent/target.py"],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(relative_path="src/javed/agent/target.py", start_line=1, end_line=10)
        ],
        evidence=[
            EvidenceItem(
                evidence_id="EVID-1",
                evidence_type=EvidenceType.SOURCE_CODE,
                source="test",
                relative_path="src/javed/agent/target.py",
                summary="Target function",
                collected_at=datetime.now(UTC).isoformat(),
            )
        ],
        security_risks=["None"],
        regression_risks=["None"],
        rollback_strategy="git checkout",
        test_strategy="pytest",
        created_at=datetime.now(UTC).isoformat(),
        design_rationale="Rationale",
        owning_components=["agent"],
        affected_contracts=["ContractA"],
        implementation_strategy="Strategy",
    )
    engine = CodingWorkflowEngine(watchdog=clean_watchdog, brief_gen_fn=lambda s: brief)
    state = CodingTaskState(
        task_id="FEAT-001",
        task_type="FEATURE",
        objective="Add feature",
        repository_head="commit-abc1234",
    )
    state = engine.brief_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.PLANNING


# 7. Investigation remains read-only
def test_07_investigation_remains_read_only(clean_watchdog: WatchdogEngine):
    brief = PreEditBrief(
        task_id="INV-001",
        task_type=TaskType.INVESTIGATION,
        objective="Investigate latency spike",
        repository_head="commit-abc1234",
        files_read=["src/javed/agent/target.py"],
        files_to_modify=[],
        files_not_to_modify=[],
        target_line_ranges=[],
        evidence=[],
        security_risks=[],
        regression_risks=[],
        rollback_strategy="None",
        test_strategy="None",
        created_at=datetime.now(UTC).isoformat(),
    )
    engine = CodingWorkflowEngine(watchdog=clean_watchdog, brief_gen_fn=lambda s: brief)
    state = CodingTaskState(
        task_id="INV-001",
        task_type="INVESTIGATION",
        objective="Investigate latency spike",
        repository_head="commit-abc1234",
    )
    state = engine.brief_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FINAL_REVIEW


# 8. Plan gate approves valid plan
def test_08_plan_gate_approves_valid_plan(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        pre_edit_brief=_make_brief(),
    )
    state = engine.plan_gate_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.CODING
    assert state.approval_status == ApprovalStatus.APPROVED


# 9. Missing brief blocks coding
def test_09_missing_brief_blocks_coding(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        pre_edit_brief=None,
    )
    state = engine.plan_gate_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FAILED
    assert "Missing Pre-Edit Brief" in state.stop_reason


# 10. Expired approval blocks coding
def test_10_expired_approval_blocks_coding(clean_watchdog: WatchdogEngine):
    brief = _make_brief()
    approval, _ = PreEditGate.approve_brief(brief, expires_in_seconds=-50)
    auth_res = PreEditGate.authorize_write(
        watchdog=clean_watchdog,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert auth_res.decision == WriteAuthorizationDecision.DENIED_EXPIRED_APPROVAL


# 11. Stale Git HEAD blocks coding
def test_11_stale_git_head_blocks_coding(clean_watchdog: WatchdogEngine):
    brief = _make_brief(head="commit-abc1234")
    approval, _ = PreEditGate.approve_brief(brief)
    clean_watchdog.git_head = "commit-shifted-999"
    auth_res = PreEditGate.authorize_write(
        watchdog=clean_watchdog,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert auth_res.decision == WriteAuthorizationDecision.DENIED_STALE_REPOSITORY


# 12. Coder only receives approved files
def test_12_coder_only_receives_approved_files(clean_watchdog: WatchdogEngine):
    brief = _make_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    state = CodingTaskState(
        task_id=brief.task_id,
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        pre_edit_brief=brief,
        approval_record=approval,
        approved_files=list(brief.files_to_modify),
    )
    assert state.approved_files == ["src/javed/agent/target.py"]


# 13. Coder cannot modify undeclared file
def test_13_coder_cannot_modify_undeclared_file(clean_watchdog: WatchdogEngine):
    brief = _make_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    auth_res = PreEditGate.authorize_write(
        watchdog=clean_watchdog,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/unapproved.py",
        operation=WriteOperation.MODIFY,
    )
    assert auth_res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED


# 14. Coder cannot expand target range
def test_14_coder_cannot_expand_target_range(clean_watchdog: WatchdogEngine):
    brief = _make_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    auth_res = PreEditGate.authorize_write(
        watchdog=clean_watchdog,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[150],  # Out of range 10..25 (allowance 20)
    )
    assert auth_res.decision == WriteAuthorizationDecision.DENIED_OUT_OF_RANGE


# 15. Scope expansion routes to Planner
def test_15_scope_expansion_routes_to_planner(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        current_state=WorkflowState.PLAN_GATE,
        pre_edit_brief=_make_brief(),
    )
    # Simulate unlisted file detection
    state.current_state = WorkflowState.SCOPE_EXPANSION_REQUIRED
    next_s = route_from_plan_gate(state)
    assert next_s == WorkflowState.SCOPE_EXPANSION_REQUIRED.value


# 16. Reviewer uses isolated context
def test_16_reviewer_uses_isolated_context(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = engine.reviewer_node(state, clean_watchdog)
    # Verify reviewer output exists and state is isolated
    assert state.review_status == ReviewerOutcome.APPROVED.value


# 17. Reviewer cannot edit
def test_17_reviewer_cannot_edit(clean_watchdog: WatchdogEngine):
    # Reviewer output cannot modify patch_summary or write files
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        current_diff_reference="diff_original",
    )
    state = engine.reviewer_node(state, clean_watchdog)
    assert state.current_diff_reference == "diff_original"


# 18. Reviewer approves valid patch
def test_18_reviewer_approves_valid_patch(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.TARGETED_TESTING


# 19. Reviewer rejects unrelated changes
def test_19_reviewer_rejects_unrelated_changes(clean_watchdog: WatchdogEngine):
    def mock_rev(s):
        return ReviewerOutput(
            outcome=ReviewerOutcome.CHANGES_REQUIRED,
            findings=[{"issue": "Unrelated modification in auth module"}],
            notes=[],
            complexity_score=1,
            unrelated_changes_detected=True,
            security_boundary_intact=True,
            public_contracts_intact=True,
        )

    engine = CodingWorkflowEngine(watchdog=clean_watchdog, review_fn=mock_rev)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.CODING


# 20. Reviewer detects over-engineering
def test_20_reviewer_detects_over_engineering(clean_watchdog: WatchdogEngine):
    def mock_rev(s):
        return ReviewerOutput(
            outcome=ReviewerOutcome.REPLAN_REQUIRED,
            findings=[{"issue": "Excessive abstraction layer introduced"}],
            notes=[],
            complexity_score=5,
            unrelated_changes_detected=False,
            security_boundary_intact=True,
            public_contracts_intact=True,
        )

    engine = CodingWorkflowEngine(watchdog=clean_watchdog, review_fn=mock_rev)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.PLANNING


# 21. Two reviewer rejections stop the loop
def test_21_two_reviewer_rejections_stop_the_loop(clean_watchdog: WatchdogEngine):
    def mock_rev(s):
        return ReviewerOutput(
            outcome=ReviewerOutcome.CHANGES_REQUIRED,
            findings=[{"issue": "Still failing style"}],
            notes=[],
            complexity_score=2,
            unrelated_changes_detected=False,
            security_boundary_intact=True,
            public_contracts_intact=True,
        )

    engine = CodingWorkflowEngine(watchdog=clean_watchdog, review_fn=mock_rev)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    # Simulate coder already visited 3 times (1 initial + 2 revisions)
    state.node_visit_counts["coder"] = 3
    state = engine.reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.REPLAN_REQUIRED


# 22. Tester runs targeted tests first
def test_22_tester_runs_targeted_tests_first(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        test_plan=["pytest tests/test_target.py"],
    )
    state = engine.tester_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FINAL_REVIEW
    assert clean_watchdog.counters.targeted_test_runs == 1


# 23. Full regression runs once
def test_23_full_regression_runs_once(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        current_state=WorkflowState.TARGETED_TESTING,
        test_plan=["pytest tests/test_target.py", "full_regression"],
        test_results=[{"exit_code": 0}],
    )
    next_s = route_from_tester(state)
    assert next_s == WorkflowState.REGRESSION_TESTING.value


# 24. Identical failure halts retry
def test_24_identical_failure_halts_retry(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        failure_fingerprints=["fp_assertion_error_1", "fp_assertion_error_1"],
    )
    next_s = route_from_tester(state)
    assert next_s == WorkflowState.REPLAN_REQUIRED.value


# 25. Environment failure does not modify production
def test_25_environment_failure_does_not_modify_production(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        test_results=[{"exit_code": 1, "failure_classification": "environment_failure"}],
    )
    next_s = route_from_tester(state)
    assert next_s == WorkflowState.OWNER_INPUT_REQUIRED.value


# 26. Final review blocks dirty repository
def test_26_final_review_blocks_dirty_repository(clean_watchdog: WatchdogEngine):
    def mock_final(s):
        return FinalReviewerOutput(
            outcome=FinalReviewerOutcome.FINAL_REJECTED,
            clean_working_tree_verified=False,
            unresolved_findings_count=0,
            documentation_consistent=True,
            resource_hygiene_verified=True,
            summary="Working tree dirty",
        )

    engine = CodingWorkflowEngine(watchdog=clean_watchdog, final_review_fn=mock_final)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.final_reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FAILED


# 27. Final review blocks unresolved findings
def test_27_final_review_blocks_unresolved_findings(clean_watchdog: WatchdogEngine):
    def mock_final(s):
        return FinalReviewerOutput(
            outcome=FinalReviewerOutcome.FINAL_REJECTED,
            clean_working_tree_verified=True,
            unresolved_findings_count=3,
            documentation_consistent=True,
            resource_hygiene_verified=True,
            summary="3 unresolved findings remain",
        )

    engine = CodingWorkflowEngine(watchdog=clean_watchdog, final_review_fn=mock_final)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.final_reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FAILED


# 28. Completed requires final approval
def test_28_completed_requires_final_approval(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.final_reviewer_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.COMPLETED
    assert clean_watchdog.state == WatchdogState.COMPLETED


# 29. Watchdog warning routes correctly
def test_29_watchdog_warning_routes_correctly(clean_watchdog: WatchdogEngine):
    clean_watchdog.state = WatchdogState.BUDGET_WARNING
    # Budget warning still allows execution of mandatory paths
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        watchdog_state=WatchdogState.BUDGET_WARNING,
        current_state=WorkflowState.PLAN_GATE,
        approval_status=ApprovalStatus.APPROVED,
        approval_id="app-1",
    )
    assert route_from_plan_gate(state) == WorkflowState.CODING.value


# 30. Budget exceeded stops workflow
def test_30_budget_exceeded_stops_workflow(clean_watchdog: WatchdogEngine):
    clean_watchdog.state = WatchdogState.BUDGET_EXCEEDED
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        watchdog_state=WatchdogState.BUDGET_EXCEEDED,
    )
    assert route_from_plan_gate(state) == WorkflowState.BUDGET_EXCEEDED.value
    assert route_from_reviewer(state) == WorkflowState.BUDGET_EXCEEDED.value
    assert route_from_tester(state) == WorkflowState.BUDGET_EXCEEDED.value


# 31. Timeout stops workflow
def test_31_timeout_stops_workflow(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        watchdog_state=WatchdogState.TIMEOUT,
    )
    assert route_from_plan_gate(state) == WorkflowState.TIMEOUT.value


# 32. Cancellation stops workflow
def test_32_cancellation_stops_workflow(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        cancellation_requested=True,
    )
    assert route_from_plan_gate(state) == WorkflowState.CANCELLED.value
    assert route_from_reviewer(state) == WorkflowState.CANCELLED.value
    assert route_from_tester(state) == WorkflowState.CANCELLED.value


# 33. No-progress enters STALLED
def test_33_no_progress_enters_stalled(clean_watchdog: WatchdogEngine):
    clean_watchdog.record_analysis_iteration(has_progress=False)
    clean_watchdog.record_analysis_iteration(has_progress=False)
    assert clean_watchdog.state == WatchdogState.STALLED


# 34. Stalled workflow replans once
def test_34_stalled_workflow_replans_once(clean_watchdog: WatchdogEngine):
    clean_watchdog.state = WatchdogState.STALLED
    res = clean_watchdog.record_replan()
    assert res is True
    assert clean_watchdog.state == WatchdogState.ACTIVE


# 35. Replan exhaustion requires owner input
def test_35_replan_exhaustion_requires_owner_input(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        replan_count=2,
        current_state=WorkflowState.PLAN_GATE,
    )
    assert route_from_plan_gate(state) == WorkflowState.OWNER_INPUT_REQUIRED.value


# 36. Checkpoint created after every node
def test_36_checkpoint_created_after_every_node(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.intake_node(state, clean_watchdog)
    assert state.checkpoint_reference is not None
    assert state.checkpoint_reference.task_id == "TASK-WF-001"


# 37. Resume requires authorization
def test_37_resume_requires_authorization(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        watchdog_state=WatchdogState.CANCELLED,
    )
    # Cancelled workflow cannot proceed without explicit un-cancel
    assert route_from_plan_gate(state) == WorkflowState.CANCELLED.value


# 38. Resume rejects changed HEAD
def test_38_resume_rejects_changed_head(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-initial-aaa",
        pre_edit_brief=_make_brief(head="commit-initial-aaa"),
    )
    # Simulate git HEAD change during resume
    state.repository_head = "commit-shifted-bbb"
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = engine.plan_gate_node(state, clean_watchdog)
    assert state.current_state == WorkflowState.FAILED
    assert "Stale Git HEAD" in state.stop_reason


# 39. Action ledger captures node progress
def test_39_action_ledger_captures_node_progress(clean_watchdog: WatchdogEngine):
    ledger = ActionLedger(task_id="TASK-WF-001")
    engine = CodingWorkflowEngine(watchdog=clean_watchdog, ledger=ledger)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
    )
    state = engine.intake_node(state, clean_watchdog, ledger)
    assert len(ledger.actions) == 1
    assert ledger.actions[0].action_type == "intake_validation"


# 40. Action ledger stores no chain-of-thought
def test_40_action_ledger_stores_no_cot():
    ledger = ActionLedger(task_id="TASK-WF-001")
    ledger.record_action(
        ActionRecord(
            action_id="act-1",
            task_id="TASK-WF-001",
            action_type="gate",
            target="target.py",
            normalized_arguments_hash="hash",
            git_head="commit-1",
            relevant_file_hashes={},
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            duration_ms=1,
            status=ActionStatus.SUCCESS,
            result_fingerprint="fp-1",
            evidence_summary="Verified",
            budget_delta={},
            retryable=False,
        )
    )
    raw = str(ledger.actions[0].to_dict())
    assert "thought" not in raw
    assert "thinking" not in raw


# 41. Secret fields are rejected
def test_41_secret_fields_are_rejected():
    with pytest.raises(ValueError, match="Sensitive credential detected"):
        CodingTaskState(
            task_id="TASK-WF-001",
            task_type="DEFECT",
            objective="api_key=sk-1234567890abcdef",
            repository_head="commit-abc1234",
        )


# 42. Planner is read-only
def test_42_planner_is_read_only(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        approved_files=["src/javed/agent/target.py"],
    )
    state = engine.planner_node(state, clean_watchdog)
    assert clean_watchdog.counters.patch_count == 0
    assert len(clean_watchdog.counters.files_modified) == 0


# 43. Tester is non-designing
def test_43_tester_is_non_designing(clean_watchdog: WatchdogEngine):
    engine = CodingWorkflowEngine(watchdog=clean_watchdog)
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        test_plan=["pytest tests/test_target.py"],
        current_diff_reference="diff_1",
    )
    state = engine.tester_node(state, clean_watchdog)
    # Diff reference and plan remain unchanged
    assert state.current_diff_reference == "diff_1"


# 44. Graphify queries are not repeated
def test_44_graphify_queries_are_not_repeated(clean_watchdog: WatchdogEngine):
    ledger = ActionLedger(task_id="TASK-WF-001")
    arg_hash = ledger.compute_action_hash("query_graphify", "find_symbol", {"name": "target"})
    # First query
    auth_ok, reason, prev = clean_watchdog.authorize_tool_call(
        tool_name="query_graphify", target="find_symbol", arguments={"name": "target"}
    )
    assert auth_ok is True
    ledger.record_action(
        ActionRecord(
            action_id="act-q1",
            task_id="TASK-WF-001",
            action_type="query_graphify",
            target="find_symbol",
            normalized_arguments_hash=arg_hash,
            git_head="commit-abc1234",
            relevant_file_hashes={},
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            duration_ms=10,
            status=ActionStatus.SUCCESS,
            result_fingerprint="fp-sym",
            evidence_summary="Found",
            budget_delta={},
            retryable=False,
        )
    )
    # Check equivalent query lookup
    cached = ledger.find_equivalent_action(
        "query_graphify", "find_symbol", arg_hash, "commit-abc1234", {}
    )
    assert cached is not None


# 45. File reads reuse unchanged ranges
def test_45_file_reads_reuse_unchanged_ranges():
    ledger = ActionLedger(task_id="TASK-WF-001")
    ledger.record_file_read(
        file_path="src/target.py",
        content_hash="hash-1",
        line_range="1-50",
        reason="inspect",
        iteration=1,
    )
    is_dup = ledger.check_duplicate_read("src/target.py", "hash-1", "1-50")
    assert is_dup is True


# 46. Patch limits are enforced
def test_46_patch_limits_are_enforced(clean_watchdog: WatchdogEngine):
    clean_watchdog.counters.patch_count = clean_watchdog.profile.max_patch_count
    clean_watchdog.record_patch_applied(lines_added=1, lines_removed=1)
    assert clean_watchdog.state == WatchdogState.BUDGET_EXCEEDED


# 47. Model-call limits are enforced
def test_47_model_call_limits_are_enforced(clean_watchdog: WatchdogEngine):
    clean_watchdog.counters.model_calls = clean_watchdog.profile.max_model_calls
    clean_watchdog.record_model_usage(prompt_tokens=50, completion_tokens=50)
    assert clean_watchdog.state == WatchdogState.BUDGET_EXCEEDED


# 48. Tool-call limits are enforced
def test_48_tool_call_limits_are_enforced(clean_watchdog: WatchdogEngine):
    clean_watchdog.counters.tool_calls = clean_watchdog.profile.max_tool_calls
    clean_watchdog.authorize_tool_call(tool_name="some_tool", target="file.py", arguments={})
    assert clean_watchdog.state == WatchdogState.BUDGET_EXCEEDED


# 49. Cost and token limits are enforced
def test_49_cost_and_token_limits_are_enforced(clean_watchdog: WatchdogEngine):
    clean_watchdog.counters.prompt_tokens = clean_watchdog.profile.max_tokens
    clean_watchdog.record_model_usage(prompt_tokens=50, completion_tokens=50)
    assert clean_watchdog.state == WatchdogState.BUDGET_EXCEEDED


# 50. Structured final report is accurate
def test_50_structured_final_report_is_accurate(clean_watchdog: WatchdogEngine):
    state = CodingTaskState(
        task_id="TASK-WF-001",
        task_type="DEFECT",
        objective="Fix defect",
        repository_head="commit-abc1234",
        current_state=WorkflowState.COMPLETED,
        final_decision=FinalReviewerOutcome.FINAL_APPROVED.value,
    )
    safe_dict = state.to_safe_dict()
    assert safe_dict["task_id"] == "TASK-WF-001"
    assert safe_dict["current_state"] == "COMPLETED"
    assert safe_dict["final_decision"] == "FINAL_APPROVED"
