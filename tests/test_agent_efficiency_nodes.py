"""test_agent_efficiency_nodes.py — Deterministic tests for workflow nodes and contracts."""

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
    ReviewerOutcome,
    ReviewerOutput,
    TesterOutput,
)
from javed.agent.efficiency.ledger import FailureClassification
from javed.agent.efficiency.nodes import (
    CoderNode,
    FinalReviewerNode,
    IntakeNode,
    PlanGateNode,
    PlannerNode,
    RepositoryOrientationNode,
    ReviewerNode,
    RootCauseOrDesignNode,
    TesterNode,
)
from javed.agent.efficiency.state import CodingTaskState, WorkflowState
from javed.agent.efficiency.watchdog import WatchdogEngine


@pytest.fixture
def base_task_state() -> CodingTaskState:
    return CodingTaskState(
        task_id="TASK-NODE-001",
        task_type="DEFECT",
        objective="Fix off-by-one error in target function",
        repository_head="commit-1234567",
    )


@pytest.fixture
def watchdog_fixture() -> WatchdogEngine:
    w = WatchdogEngine(
        task_id="TASK-NODE-001",
        task_class=TaskClass.SINGLE_FILE_DEFECT,
        git_head="commit-1234567",
    )
    return w


def _make_valid_brief(task_id: str = "TASK-NODE-001") -> PreEditBrief:
    return PreEditBrief(
        task_id=task_id,
        task_type=TaskType.DEFECT,
        objective="Fix off-by-one error in target function",
        repository_head="commit-1234567",
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
                summary="Target loop index error",
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


def test_intake_node_valid(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    node = IntakeNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.REPOSITORY_ORIENTATION
    assert state.task_class == TaskClass.SINGLE_FILE_DEFECT
    assert state.get_visit_count("intake") == 1


def test_intake_node_invalid_task_type(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    base_task_state.task_type = "INVALID_TYPE"
    node = IntakeNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.FAILED
    assert "Unsupported task_type" in state.stop_reason


def test_repo_orientation_output_bounds(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    # Mock query returning excessive items
    def mock_query(obj: str):
        return {
            "owning_files": [f"file_{i}.py" for i in range(20)],
            "symbols": [f"sym_{i}" for i in range(50)],
            "tests": [f"test_{i}.py" for i in range(25)],
        }

    node = RepositoryOrientationNode(query_fn=mock_query)
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.ROOT_CAUSE_OR_DESIGN
    assert len(state.repository_context["owning_files"]) <= 12
    assert len(state.repository_context["symbols"]) <= 30
    assert len(state.repository_context["tests"]) <= 12


def test_root_cause_node_defect_brief(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    brief = _make_valid_brief()
    node = RootCauseOrDesignNode(brief_generator_fn=lambda s: brief)
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.PLANNING
    assert state.brief_hash is not None
    assert state.approved_files == ["src/javed/agent/target.py"]


def test_root_cause_node_investigation_read_only(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    inv_brief = PreEditBrief(
        task_id="TASK-NODE-001",
        task_type=TaskType.INVESTIGATION,
        objective="Investigate memory spike",
        repository_head="commit-1234567",
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
    node = RootCauseOrDesignNode(brief_generator_fn=lambda s: inv_brief)
    state = node(base_task_state, watchdog_fixture)
    # Investigation should not proceed to planning or coding
    assert state.current_state == WorkflowState.FINAL_REVIEW


def test_planner_node_limits(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    node = PlannerNode()
    base_task_state.approved_files = ["src/javed/agent/target.py"]
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.PLAN_GATE
    # Second visit allowed
    state = node(state, watchdog_fixture)
    assert state.get_visit_count("planner") == 2
    # Third visit blocked
    state = node(state, watchdog_fixture)
    assert state.current_state == WorkflowState.OWNER_INPUT_REQUIRED


def test_plan_gate_approves_valid_plan(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    base_task_state.pre_edit_brief = _make_valid_brief()
    node = PlanGateNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.CODING
    assert state.approval_id is not None


def test_plan_gate_rejects_stale_head(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    brief = _make_valid_brief()
    base_task_state.pre_edit_brief = brief
    base_task_state.repository_head = "commit-shifted-999"  # Differs from brief
    node = PlanGateNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.FAILED
    assert "Stale Git HEAD" in state.stop_reason


def test_coder_node_authorized(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    base_task_state.pre_edit_brief = _make_valid_brief()
    gate = PlanGateNode()
    state = gate(base_task_state, watchdog_fixture)
    coder = CoderNode()
    state = coder(state, watchdog_fixture)
    assert state.current_state == WorkflowState.REVIEW
    assert watchdog_fixture.counters.patch_count == 1


def test_coder_node_visit_limit(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    base_task_state.pre_edit_brief = _make_valid_brief()
    gate = PlanGateNode()
    state = gate(base_task_state, watchdog_fixture)
    coder = CoderNode()
    state = coder(state, watchdog_fixture)
    state = coder(state, watchdog_fixture)
    state = coder(state, watchdog_fixture)
    assert state.get_visit_count("coder") == 3
    # 4th visit fails closed
    state = coder(state, watchdog_fixture)
    assert state.current_state == WorkflowState.REPLAN_REQUIRED


def test_reviewer_node_approved(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    node = ReviewerNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.TARGETED_TESTING
    assert state.review_status == ReviewerOutcome.APPROVED.value


def test_reviewer_node_changes_required(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    def mock_rev(s):
        return ReviewerOutput(
            outcome=ReviewerOutcome.CHANGES_REQUIRED,
            findings=[{"issue": "Refactor helper"}],
            notes=[],
            complexity_score=2,
            unrelated_changes_detected=False,
            security_boundary_intact=True,
            public_contracts_intact=True,
        )

    node = ReviewerNode(review_fn=mock_rev)
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.CODING


def test_tester_node_passed(base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine):
    node = TesterNode()
    base_task_state.test_plan = ["pytest tests/test_target.py"]
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.FINAL_REVIEW
    assert watchdog_fixture.counters.targeted_test_runs == 1


def test_tester_node_identical_failure_loop(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    def mock_test(s):
        return TesterOutput(
            tests_executed=["pytest tests/test_target.py"],
            passed_count=0,
            failed_count=1,
            exit_code=1,
            safe_summary="AssertionError in line 15",
            failure_fingerprints=["fp_assert_err_15"],
            failure_classification=FailureClassification.PATCH_DEFECT,
            retryable=True,
        )

    node = TesterNode(test_runner_fn=mock_test)
    state = node(base_task_state, watchdog_fixture)
    # First failure -> routes to coder
    assert state.current_state == WorkflowState.CODING
    # Second identical failure -> routes to replan
    state = node(state, watchdog_fixture)
    assert state.current_state == WorkflowState.REPLAN_REQUIRED
    assert "Identical failure loop" in state.stop_reason


def test_final_reviewer_node_completed(
    base_task_state: CodingTaskState, watchdog_fixture: WatchdogEngine
):
    node = FinalReviewerNode()
    state = node(base_task_state, watchdog_fixture)
    assert state.current_state == WorkflowState.COMPLETED
    assert state.final_decision == FinalReviewerOutcome.FINAL_APPROVED.value
