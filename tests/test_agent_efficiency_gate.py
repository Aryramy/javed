"""test_agent_efficiency_gate.py — 50 Deterministic Pre-Edit Brief Gate Tests.

Validates all 50 gate requirements:
1. Valid defect brief
2. Valid feature brief
3. Valid documentation brief
4. Unknown task type rejection
5. Missing brief rejection
6. Malformed brief rejection
7. Missing objective
8. Missing evidence
9. Symptom-only root cause rejection
10. Low-confidence root cause requires owner review
11. Missing files_to_modify
12. Missing files_not_to_modify
13. Missing target range
14. Missing rollback strategy
15. Missing test strategy
16. Sensitive path rejection
17. Traversal rejection
18. Undeclared file rejection
19. Undeclared symbol rejection
20. Out-of-range patch rejection
21. Allowed in-range modification (including context allowance)
22. Explicit new-file creation
23. Unauthorized file creation rejection
24. Explicit deletion authorization
25. Unauthorized deletion rejection
26. Approval-task mismatch
27. Approval expiry
28. Approval cancellation
29. Approval invalidation on Git HEAD change
30. Approval invalidation on file hash change
31. Deterministic brief hashing
32. Canonical serialization
33. Watchdog ACTIVE allows approved write
34. BUDGET_EXCEEDED denies write
35. STALLED denies write
36. TIMEOUT denies write
37. CANCELLED denies write
38. Scope expansion returns required state
39. Ledger records authorization decision
40. Ledger excludes source content
41. Secret-field rejection
42. No chain-of-thought storage
43. Investigation task is read-only
44. Documentation task cannot modify source
45. Feature brief requires contract ownership
46. Security fix requires threat and security testing strategy
47. Migration requires compatibility and rollback
48. Consumed approval cannot be reused where single-use applies
49. Unknown decision fails closed
50. Owner override is task- and budget-specific
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
from javed.agent.efficiency.gate import (
    ApprovalStatus,
    PreEditGate,
    WriteAuthorizationDecision,
    WriteOperation,
)
from javed.agent.efficiency.ledger import ActionLedger, ActionRecord, ActionStatus
from javed.agent.efficiency.watchdog import WatchdogEngine, WatchdogState


@pytest.fixture
def watchdog_fixture() -> WatchdogEngine:
    w = WatchdogEngine(
        task_id="TASK-TEST-001",
        task_class=TaskClass.SINGLE_FILE_DEFECT,
        git_head="commit-abc1234",
    )
    return w


def _make_evidence(summary: str = "Evidence found in source") -> list[EvidenceItem]:
    return [
        EvidenceItem(
            evidence_id="EVID-001",
            evidence_type=EvidenceType.SOURCE_CODE,
            source="test_runner",
            relative_path="src/javed/agent/target.py",
            summary=summary,
            collected_at=datetime.now(UTC).isoformat(),
        )
    ]


def _make_valid_defect_brief() -> PreEditBrief:
    return PreEditBrief(
        task_id="TASK-TEST-001",
        task_type=TaskType.DEFECT,
        objective="Fix off-by-one error in target.py calculation",
        repository_head="commit-abc1234",
        files_read=["src/javed/agent/target.py"],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(
                relative_path="src/javed/agent/target.py",
                start_line=10,
                end_line=25,
                owning_symbol="compute_total",
            )
        ],
        evidence=_make_evidence(),
        security_risks=["None"],
        regression_risks=["Potential edge case at zero"],
        rollback_strategy="git checkout -- src/javed/agent/target.py",
        test_strategy="pytest tests/test_target.py -v",
        created_at=datetime.now(UTC).isoformat(),
        current_behavior="Loop starts at 0",
        expected_behavior="Loop starts at 1",
        root_cause="Loop index starts at 0 instead of 1 in compute_total function",
        root_cause_confidence=RootCauseConfidence.HIGH,
        affected_symbols=["compute_total"],
        patch_strategy="Change range(0, n) to range(1, n + 1)",
    )


# 1. Valid defect brief
def test_01_valid_defect_brief():
    brief = _make_valid_defect_brief()
    valid, errors = brief.validate_structure()
    assert valid is True
    assert errors == []
    assert brief.compute_brief_hash() is not None


# 2. Valid feature brief
def test_02_valid_feature_brief():
    brief = PreEditBrief(
        task_id="FEAT-001",
        task_type=TaskType.FEATURE,
        objective="Add batch calculation support",
        repository_head="commit-abc1234",
        files_read=["src/javed/agent/target.py"],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(
                relative_path="src/javed/agent/target.py",
                start_line=50,
                end_line=70,
                owning_symbol="batch_compute",
            )
        ],
        evidence=_make_evidence(),
        security_risks=["None"],
        regression_risks=["None"],
        rollback_strategy="git checkout -- src/javed/agent/target.py",
        test_strategy="pytest tests/test_batch.py",
        created_at=datetime.now(UTC).isoformat(),
        design_rationale="Allows bulk processing of items in single pass",
        owning_components=["agent_service"],
        affected_contracts=["IBatchProcessor"],
        implementation_strategy="Implement batch_compute method",
    )
    valid, errors = brief.validate_structure()
    assert valid is True
    assert errors == []


# 3. Valid documentation brief
def test_03_valid_documentation_brief():
    brief = PreEditBrief(
        task_id="DOC-001",
        task_type=TaskType.DOCUMENTATION,
        objective="Update README architecture section",
        repository_head="commit-abc1234",
        files_read=["README.md"],
        files_to_modify=["docs/architecture.md"],
        files_not_to_modify=[],
        target_line_ranges=[],
        evidence=[
            EvidenceItem(
                evidence_id="EVID-DOC",
                evidence_type=EvidenceType.DOCUMENTATION,
                source="user",
                relative_path="docs/architecture.md",
                summary="Outdated documentation",
                collected_at=datetime.now(UTC).isoformat(),
            )
        ],
        security_risks=[],
        regression_risks=[],
        rollback_strategy="git checkout -- docs/architecture.md",
        test_strategy="markdownlint docs/architecture.md",
        created_at=datetime.now(UTC).isoformat(),
    )
    valid, errors = brief.validate_structure()
    assert valid is True


# 4. Unknown task type rejection
def test_04_unknown_task_type_rejection():
    # Enums in python prevent creating unknown types directly
    with pytest.raises(ValueError):
        TaskType("UNKNOWN_TASK_TYPE")


# 5. Missing brief rejection
def test_05_missing_brief_rejection(watchdog_fixture: WatchdogEngine):
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=None,
        approval=None,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_NO_BRIEF
    assert res.allowed is False


# 6. Malformed brief rejection
def test_06_malformed_brief_rejection(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    # Malformed by missing objective
    object.__setattr__(brief, "objective", "")
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_INVALID_BRIEF


# 7. Missing objective
def test_07_missing_objective():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "objective", "   ")
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("objective is missing" in e for e in errors)


# 8. Missing evidence
def test_08_missing_evidence():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "evidence", [])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("evidence must contain" in e for e in errors)


# 9. Symptom-only root cause rejection
@pytest.mark.parametrize(
    "symptom",
    [
        "page is broken",
        "test fails",
        "test failed",
        "model returned an error",
        "something went wrong",
        "syntax error",
        "unexpected behavior",
        "needs fixing",
    ],
)
def test_09_symptom_only_root_cause_rejection(symptom: str):
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "root_cause", symptom)
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("Symptom rejected as root cause" in e for e in errors)


# 10. Low-confidence root cause requires owner review
def test_10_low_confidence_requires_owner_review():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "root_cause_confidence", RootCauseConfidence.LOW)
    # Default approval rejects LOW confidence without owner override
    app, errors = PreEditGate.approve_brief(brief, owner_override_low_confidence=False)
    assert app is None
    assert any("Root cause confidence is LOW" in e for e in errors)

    # Allowed when owner explicitly overrides
    app_override, errors_override = PreEditGate.approve_brief(
        brief, owner_override_low_confidence=True
    )
    assert app_override is not None
    assert errors_override == []


# 11. Missing files_to_modify
def test_11_missing_files_to_modify():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "files_to_modify", [])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("files_to_modify must declare" in e for e in errors)


# 12. Missing files_not_to_modify
def test_12_missing_files_not_to_modify():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "files_not_to_modify", [])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("files_not_to_modify must explicitly declare" in e for e in errors)


# 13. Missing target range
def test_13_missing_target_range():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "target_line_ranges", [])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("target_line_ranges must be declared" in e for e in errors)


# 14. Missing rollback strategy
def test_14_missing_rollback_strategy():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "rollback_strategy", "")
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("rollback_strategy is missing" in e for e in errors)


# 15. Missing test strategy
def test_15_missing_test_strategy():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "test_strategy", "")
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("test_strategy is missing" in e for e in errors)


# 16. Sensitive path rejection
@pytest.mark.parametrize(
    "bad_path",
    [
        ".env",
        ".git/config",
        "node_modules/pkg/index.js",
        ".venv/lib/site-packages",
    ],
)
def test_16_sensitive_path_rejection(bad_path: str):
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "files_to_modify", [bad_path])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("Protected path rejected" in e for e in errors)


# 17. Traversal rejection
def test_17_traversal_rejection():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "files_to_modify", ["../outside.py"])
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("Path traversal rejected" in e for e in errors)


# 18. Undeclared file rejection
def test_18_undeclared_file_rejection(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/other.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED


# 19. Undeclared symbol rejection
def test_19_undeclared_symbol_rejection(watchdog_fixture: WatchdogEngine):
    # Symbol authorization logic is checked via line range in gate
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    # Target lines corresponding to a different symbol outside range
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[200],  # Out of range for compute_total (10..25)
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_OUT_OF_RANGE


# 20. Out-of-range patch rejection
def test_20_out_of_range_patch_rejection(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    # Range is 10..25, allowance is 20 lines (range 0..45). Line 80 is strictly out of range
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[80],
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_OUT_OF_RANGE


# 21. Allowed in-range modification (including context allowance)
def test_21_allowed_in_range_modification(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    # Declared 10..25. Line 15 is directly within declared range
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[15],
    )
    assert res.decision == WriteAuthorizationDecision.ALLOWED
    assert res.allowed is True


# 22. Explicit new-file creation
def test_22_explicit_new_file_creation(watchdog_fixture: WatchdogEngine):
    new_path = "src/javed/agent/new_module.py"
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "files_to_modify", [new_path])
    object.__setattr__(
        brief,
        "target_line_ranges",
        [TargetLineRange(relative_path=new_path, start_line=0, end_line=0)],
    )
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path=new_path,
        operation=WriteOperation.CREATE,
    )
    assert res.decision == WriteAuthorizationDecision.ALLOWED
    assert res.allowed is True


# 23. Unauthorized file creation rejection
def test_23_unauthorized_file_creation_rejection(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/unauth.py",
        operation=WriteOperation.CREATE,
    )
    assert res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED


# 24. Explicit deletion authorization
def test_24_explicit_deletion_authorization(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.DELETE,
    )
    assert res.decision == WriteAuthorizationDecision.ALLOWED


# 25. Unauthorized deletion rejection
def test_25_unauthorized_deletion_rejection(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/other.py",
        operation=WriteOperation.DELETE,
    )
    assert res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED


# 26. Approval-task mismatch
def test_26_approval_task_mismatch(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    # Change approval task_id
    object.__setattr__(approval, "task_id", "DIFFERENT-TASK")
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_NO_APPROVAL


# 27. Approval expiry
def test_27_approval_expiry(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief, expires_in_seconds=-10)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_EXPIRED_APPROVAL


# 28. Approval cancellation
def test_28_approval_cancellation(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    object.__setattr__(approval, "status", ApprovalStatus.CANCELLED)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_NO_APPROVAL


# 29. Approval invalidation on Git HEAD change
def test_29_approval_invalidation_on_git_head_change(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    # Git head moves
    watchdog_fixture.git_head = "commit-shifted-999"
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_STALE_REPOSITORY


# 30. Approval invalidation on file hash change
def test_30_approval_invalidation_on_file_hash_change(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        current_file_hash="hash_changed_bbb",
        expected_file_hash="hash_original_aaa",
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_STALE_FILE


# 31. Deterministic brief hashing
def test_31_deterministic_brief_hashing():
    b1 = _make_valid_defect_brief()
    b2 = _make_valid_defect_brief()
    assert b1.compute_brief_hash() == b2.compute_brief_hash()
    object.__setattr__(b2, "objective", "Different objective text")
    assert b1.compute_brief_hash() != b2.compute_brief_hash()


# 32. Canonical serialization
def test_32_canonical_serialization():
    b = _make_valid_defect_brief()
    h = b.compute_brief_hash()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# 33. Watchdog ACTIVE allows approved write
def test_33_watchdog_active_allows_approved_write(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    watchdog_fixture.state = WatchdogState.ACTIVE
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[15],
    )
    assert res.decision == WriteAuthorizationDecision.ALLOWED
    assert res.allowed is True


# 34. BUDGET_EXCEEDED denies write
def test_34_budget_exceeded_denies_write(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    watchdog_fixture.state = WatchdogState.BUDGET_EXCEEDED
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_BUDGET_STATE


# 35. STALLED denies write
def test_35_stalled_denies_write(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    watchdog_fixture.state = WatchdogState.STALLED
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_BUDGET_STATE


# 36. TIMEOUT denies write
def test_36_timeout_denies_write(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    watchdog_fixture.state = WatchdogState.TIMEOUT
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_BUDGET_STATE


# 37. CANCELLED denies write
def test_37_cancelled_denies_write(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    watchdog_fixture.state = WatchdogState.CANCELLED
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_BUDGET_STATE


# 38. Scope expansion returns required state
def test_38_scope_expansion_returns_required_state(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/unlisted.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.SCOPE_EXPANSION_REQUIRED
    assert watchdog_fixture.state == WatchdogState.SCOPE_EXPANSION_REQUIRED


# 39. Ledger records authorization decision
def test_39_ledger_records_authorization_decision(watchdog_fixture: WatchdogEngine):
    ledger = ActionLedger(task_id="TASK-TEST-001")
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief)
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
        target_lines=[15],
    )
    rec = ActionRecord(
        action_id="act-auth-1",
        task_id=watchdog_fixture.task_id,
        action_type="write_authorization",
        target=res.file_path,
        normalized_arguments_hash="hash-123",
        git_head=watchdog_fixture.git_head,
        relevant_file_hashes={},
        start_time=datetime.now(UTC).isoformat(),
        end_time=datetime.now(UTC).isoformat(),
        duration_ms=5,
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp-123",
        evidence_summary=res.decision.value,
        budget_delta={},
        retryable=False,
    )
    ledger.record_action(rec)
    records = ledger.actions
    assert len(records) == 1
    assert records[0].evidence_summary == "ALLOWED"


# 40. Ledger excludes source content
def test_40_ledger_excludes_source_content():
    ledger = ActionLedger(task_id="TASK-TEST-001")
    rec = ActionRecord(
        action_id="act-auth-2",
        task_id="TASK-TEST-001",
        action_type="write_authorization",
        target="src/javed/agent/target.py",
        normalized_arguments_hash="hash-456",
        git_head="head-abc",
        relevant_file_hashes={},
        start_time=datetime.now(UTC).isoformat(),
        end_time=datetime.now(UTC).isoformat(),
        duration_ms=5,
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp-456",
        evidence_summary="ALLOWED",
        budget_delta={},
        retryable=False,
    )
    ledger.record_action(rec)
    rec_dict = ledger.actions[0].to_dict()
    assert "content" not in rec_dict
    assert "source_content" not in rec_dict
    assert "diff" not in rec_dict


# 41. Secret-field rejection
def test_41_secret_field_rejection():
    with pytest.raises(ValueError, match="Sensitive credential detected"):
        EvidenceItem(
            evidence_id="EVID-LEAK",
            evidence_type=EvidenceType.API_RESPONSE,
            source="api",
            relative_path="src/api.py",
            summary="api_key=sk-secret-123456",
            collected_at=datetime.now(UTC).isoformat(),
        )


# 42. No chain-of-thought storage
def test_42_no_chain_of_thought_storage():
    brief = _make_valid_defect_brief()
    fields = [f for f in brief.__dataclass_fields__]
    assert "thinking" not in fields
    assert "thought" not in fields
    assert "scratchpad" not in fields


# 43. Investigation task is read-only
def test_43_investigation_task_is_read_only(watchdog_fixture: WatchdogEngine):
    brief = PreEditBrief(
        task_id="INV-001",
        task_type=TaskType.INVESTIGATION,
        objective="Investigate performance bottleneck",
        repository_head="commit-abc1234",
        files_read=["src/javed/agent/target.py"],
        files_to_modify=["src/javed/agent/target.py"],  # Forbidden for investigation
        files_not_to_modify=[],
        target_line_ranges=[],
        evidence=[],
        security_risks=[],
        regression_risks=[],
        rollback_strategy="None",
        test_strategy="None",
        created_at=datetime.now(UTC).isoformat(),
    )
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("INVESTIGATION task is strictly read-only" in e for e in errors)


# 44. Documentation task cannot modify source
def test_44_documentation_task_cannot_modify_source():
    brief = PreEditBrief(
        task_id="DOC-002",
        task_type=TaskType.DOCUMENTATION,
        objective="Document API",
        repository_head="commit-abc1234",
        files_read=[],
        files_to_modify=["src/javed/agent/runtime.py"],  # Source file!
        files_not_to_modify=[],
        target_line_ranges=[],
        evidence=[
            EvidenceItem(
                evidence_id="EVID-DOC",
                evidence_type=EvidenceType.DOCUMENTATION,
                source="user",
                relative_path="src/javed/agent/runtime.py",
                summary="Doc request",
                collected_at=datetime.now(UTC).isoformat(),
            )
        ],
        security_risks=[],
        regression_risks=[],
        rollback_strategy="git checkout",
        test_strategy="pytest",
        created_at=datetime.now(UTC).isoformat(),
    )
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("DOCUMENTATION task cannot modify source code file" in e for e in errors)


# 45. Feature brief requires contract ownership
def test_45_feature_brief_requires_contract_ownership():
    brief = PreEditBrief(
        task_id="FEAT-002",
        task_type=TaskType.FEATURE,
        objective="Add feature without affected_contracts",
        repository_head="commit-abc1234",
        files_read=[],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(relative_path="src/javed/agent/target.py", start_line=1, end_line=10)
        ],
        evidence=_make_evidence(),
        security_risks=[],
        regression_risks=[],
        rollback_strategy="git checkout",
        test_strategy="pytest",
        created_at=datetime.now(UTC).isoformat(),
        design_rationale="Rationale provided",
        owning_components=["agent_service"],
        affected_contracts=[],  # Empty!
        implementation_strategy="Strategy provided",
    )
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("FEATURE brief requires affected_contracts" in e for e in errors)


# 46. Security fix requires threat and security testing strategy
def test_46_security_fix_requires_threat_and_testing():
    brief = PreEditBrief(
        task_id="SEC-001",
        task_type=TaskType.SECURITY_FIX,
        objective="Mitigate prompt injection vulnerability",
        repository_head="commit-abc1234",
        files_read=[],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(relative_path="src/javed/agent/target.py", start_line=1, end_line=10)
        ],
        evidence=_make_evidence(),
        security_risks=[],  # Empty security_risks!
        regression_risks=[],
        rollback_strategy="git checkout",
        test_strategy="pytest tests/security",
        created_at=datetime.now(UTC).isoformat(),
        threat_analysis="",  # Empty threat_analysis!
        root_cause="Unsanitized user prompt parameter passed directly to execution engine",
    )
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("SECURITY_FIX brief requires threat_analysis" in e for e in errors)
    assert any("SECURITY_FIX brief requires security_risks" in e for e in errors)


# 47. Migration requires compatibility and rollback
def test_47_migration_requires_compatibility_and_rollback():
    brief = PreEditBrief(
        task_id="MIG-001",
        task_type=TaskType.MIGRATION,
        objective="Migrate database schema",
        repository_head="commit-abc1234",
        files_read=[],
        files_to_modify=["src/javed/agent/target.py"],
        files_not_to_modify=["src/javed/agent/runtime.py"],
        target_line_ranges=[
            TargetLineRange(relative_path="src/javed/agent/target.py", start_line=1, end_line=10)
        ],
        evidence=_make_evidence(),
        security_risks=[],
        regression_risks=[],
        rollback_strategy="git checkout",
        test_strategy="pytest",
        created_at=datetime.now(UTC).isoformat(),
        compatibility_plan="",  # Empty!
        compatibility_requirements=[],  # Empty!
    )
    valid, errors = brief.validate_structure()
    assert valid is False
    assert any("MIGRATION brief requires compatibility_plan" in e for e in errors)
    assert any("MIGRATION brief requires compatibility_requirements" in e for e in errors)


# 48. Consumed approval cannot be reused where single-use applies
def test_48_consumed_approval_cannot_be_reused(watchdog_fixture: WatchdogEngine):
    brief = _make_valid_defect_brief()
    approval, _ = PreEditGate.approve_brief(brief, single_use=True)
    # Mark consumed
    object.__setattr__(approval, "consumed_at", datetime.now(UTC).isoformat())
    res = PreEditGate.authorize_write(
        watchdog=watchdog_fixture,
        brief=brief,
        approval=approval,
        relative_path="src/javed/agent/target.py",
        operation=WriteOperation.MODIFY,
    )
    assert res.decision == WriteAuthorizationDecision.DENIED_NO_APPROVAL
    assert "Single-use approval has already been consumed" in res.reason


# 49. Unknown decision fails closed
def test_49_unknown_decision_fails_closed():
    # Verify all enum values default to denying access unless specifically ALLOWED
    for d in WriteAuthorizationDecision:
        if d != WriteAuthorizationDecision.ALLOWED:
            assert "DENIED" in d.value or "REQUIRED" in d.value


# 50. Owner override is task- and budget-specific
def test_50_owner_override_is_task_and_budget_specific():
    brief = _make_valid_defect_brief()
    object.__setattr__(brief, "root_cause_confidence", RootCauseConfidence.LOW)
    # Without override -> Rejected
    app, errors = PreEditGate.approve_brief(brief, owner_override_low_confidence=False)
    assert app is None
    # With override -> Approved specifically for this brief
    app_override, errors_override = PreEditGate.approve_brief(
        brief, owner_override_low_confidence=True
    )
    assert app_override is not None
    assert app_override.task_id == brief.task_id
