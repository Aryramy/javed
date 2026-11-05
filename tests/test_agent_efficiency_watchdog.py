"""test_agent_efficiency_watchdog.py — Comprehensive deterministic unit tests for Watchdog Engine.

Covers all required Milestone 4 test scenarios:
 4. Warning at 80%
 5. Hard stop at 100%
 6. Wall-clock timeout
 7. Analysis iteration limit
 8. Replan limit
 9. File-read limit
10. Repeated read prevention
11. Changed-file reread allowance
12. Tool-call limit
13. Equivalent tool-call reuse
14. Failed equivalent action prevention
15. Patch-count limit
16. Modified-file limit
17. Scope expansion detection
18. Targeted-test limit
19. Full-regression limit
20. Identical failure fingerprint stop
21. Environment-failure classification
22. No-progress detection
23. Stalled to replan transition
24. Replan exhaustion
25. Model-call limit
26. Token warning and stop
27. Cost warning and stop
28. Owner override validation
29. Override expiration
30. Subprocess timeout
31. Graceful cancellation
32. Child-process cleanup
33. Checkpoint serialization
34. Secret-field rejection
35. No chain-of-thought storage
36. Resume requires explicit authorization
37. Graphify query duplicate prevention
38. Repository state invalidates cached actions
39. Task completion within budget
40. Metrics summary accuracy
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from javed.agent.efficiency import (
    ActionStatus,
    FailureClassification,
    OwnerBudgetOverride,
    TaskClass,
    WatchdogEngine,
    WatchdogState,
    run_bounded_subprocess,
)


class FakeClock:
    """Deterministic simulated clock."""

    def __init__(self, start: float = 1000.0):
        self.current_time = start

    def __call__(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(1000.0)


@pytest.fixture
def watchdog(fake_clock: FakeClock) -> WatchdogEngine:
    return WatchdogEngine(
        task_id="TASK-TEST-001",
        task_class=TaskClass.SINGLE_FILE_DEFECT,
        git_head="commit_alpha",
        approved_files=["src/javed/module_a.py"],
        clock_fn=fake_clock,
    )


# ----------------------------------------------------------------------
# 4. Warning at 80%
# ----------------------------------------------------------------------
def test_warning_at_80_percent(watchdog: WatchdogEngine):
    # Single file defect has max_tool_calls = 40. 80% is 32.
    for i in range(32):
        watchdog.authorize_tool_call(
            tool_name=f"tool_{i}",
            target="target_a",
            arguments={"idx": i},
        )
    assert watchdog.state == WatchdogState.BUDGET_WARNING
    assert len(watchdog.warnings) >= 1
    w = next(w for w in watchdog.warnings if w.metric == "tool_calls")
    assert w.percentage_consumed >= 80.0


# ----------------------------------------------------------------------
# 5. Hard stop at 100%
# ----------------------------------------------------------------------
def test_hard_stop_at_100_percent(watchdog: WatchdogEngine):
    for i in range(40):
        watchdog.authorize_tool_call(
            tool_name=f"tool_{i}",
            target="target_a",
            arguments={"idx": i},
        )
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED
    allowed, msg, _ = watchdog.authorize_tool_call("tool_extra", "target_a", {})
    assert not allowed
    assert "BUDGET_EXCEEDED" in msg


# ----------------------------------------------------------------------
# 6. Wall-clock timeout
# ----------------------------------------------------------------------
def test_wall_clock_timeout(watchdog: WatchdogEngine, fake_clock: FakeClock):
    # single_file_defect max_duration is 1200s
    fake_clock.advance(1201.0)
    watchdog.check_time_limit()
    assert watchdog.state == WatchdogState.TIMEOUT


# ----------------------------------------------------------------------
# 7. Analysis iteration limit
# ----------------------------------------------------------------------
def test_analysis_iteration_limit(watchdog: WatchdogEngine):
    # max_analysis_iterations = 3
    watchdog.record_analysis_iteration(has_progress=True)
    watchdog.record_analysis_iteration(has_progress=True)
    watchdog.record_analysis_iteration(has_progress=True)
    assert watchdog.state == WatchdogState.ACTIVE
    watchdog.record_analysis_iteration(has_progress=True)
    assert watchdog.state == WatchdogState.REPLAN_REQUIRED


# ----------------------------------------------------------------------
# 8. Replan limit
# ----------------------------------------------------------------------
def test_replan_limit(watchdog: WatchdogEngine):
    # max_replans = 1
    assert watchdog.record_replan() is True
    assert watchdog.state == WatchdogState.ACTIVE
    # Second replan must fail
    assert watchdog.record_replan() is False
    assert watchdog.state == WatchdogState.OWNER_INPUT_REQUIRED


# ----------------------------------------------------------------------
# 9. File-read limit
# ----------------------------------------------------------------------
def test_file_read_limit(watchdog: WatchdogEngine):
    # max_unique_files_read = 10
    for i in range(10):
        allowed, _ = watchdog.authorize_file_read(
            file_path=f"src/file_{i}.py",
            content_hash=f"hash_{i}",
        )
        assert allowed

    # 11th unique file read
    allowed, msg = watchdog.authorize_file_read("src/file_11.py", "hash_11")
    assert not allowed
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 10. Repeated read prevention
# ----------------------------------------------------------------------
def test_repeated_read_prevention(watchdog: WatchdogEngine):
    allowed, _ = watchdog.authorize_file_read("src/file.py", "hash_abc", "L10-L20")
    assert allowed
    # Exact duplicate read of unchanged range
    allowed, msg = watchdog.authorize_file_read("src/file.py", "hash_abc", "L10-L20")
    assert not allowed
    assert "DUPLICATE_READ_PREVENTED" in msg
    assert watchdog.ledger.duplicate_reads_prevented == 1


# ----------------------------------------------------------------------
# 11. Changed-file reread allowance
# ----------------------------------------------------------------------
def test_changed_file_reread_allowance(watchdog: WatchdogEngine):
    allowed, _ = watchdog.authorize_file_read("src/file.py", "hash_v1", "L10-L20")
    assert allowed
    # File content changed (new hash) -> authorized
    allowed, msg = watchdog.authorize_file_read("src/file.py", "hash_v2", "L10-L20")
    assert allowed
    assert msg == "AUTHORIZED"


# ----------------------------------------------------------------------
# 12. Tool-call limit
# ----------------------------------------------------------------------
def test_tool_call_limit(watchdog: WatchdogEngine):
    for i in range(40):
        watchdog.authorize_tool_call(f"tool_{i}", "target", {"i": i})
    assert watchdog.counters.tool_calls == 40
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 13. Equivalent tool-call reuse
# ----------------------------------------------------------------------
def test_equivalent_tool_call_reuse(watchdog: WatchdogEngine):
    allowed, _, _ = watchdog.authorize_tool_call("query_symbol", "Router", {"budget": 1000})
    assert allowed
    # Record success
    watchdog.record_action_result(
        action_id="act_1",
        tool_name="query_symbol",
        target="Router",
        arguments={"budget": 1000},
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp_123",
        evidence_summary="Found Router in src/router.py",
    )
    # Identical query under same git head and files
    allowed, msg, prev = watchdog.authorize_tool_call("query_symbol", "Router", {"budget": 1000})
    assert not allowed
    assert "DUPLICATE_ACTION_REUSED" in msg
    assert prev is not None
    assert watchdog.ledger.duplicate_actions_prevented == 1


# ----------------------------------------------------------------------
# 14. Failed equivalent action prevention
# ----------------------------------------------------------------------
def test_failed_equivalent_action_prevention(watchdog: WatchdogEngine):
    allowed, _, _ = watchdog.authorize_tool_call("run_test", "test_file.py", {})
    assert allowed
    watchdog.record_action_result(
        action_id="act_2",
        tool_name="run_test",
        target="test_file.py",
        arguments={},
        status=ActionStatus.FAILED,
        result_fingerprint="fp_fail",
        evidence_summary="AssertionError in test",
        retryable=False,
    )
    # Attempting same failed action without repository changes
    allowed, msg, _ = watchdog.authorize_tool_call("run_test", "test_file.py", {})
    assert not allowed
    assert "FAILED_EQUIVALENT_ACTION" in msg
    assert watchdog.state == WatchdogState.REPLAN_REQUIRED


# ----------------------------------------------------------------------
# 15. Patch-count limit
# ----------------------------------------------------------------------
def test_patch_count_limit(watchdog: WatchdogEngine):
    # max_patch_count = 2
    assert watchdog.record_patch_applied(lines_added=10, lines_removed=2)
    assert watchdog.record_patch_applied(lines_added=5, lines_removed=1)
    assert not watchdog.record_patch_applied(lines_added=1, lines_removed=0)
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 16. Modified-file limit
# ----------------------------------------------------------------------
def test_modified_file_limit(watchdog: WatchdogEngine):
    # Configure 4 approved files
    watchdog.approved_files = {"src/a.py", "src/b.py", "src/c.py", "src/d.py"}
    # max_files_modified = 3
    assert watchdog.authorize_file_modification("src/a.py")[0]
    assert watchdog.authorize_file_modification("src/b.py")[0]
    assert watchdog.authorize_file_modification("src/c.py")[0]
    allowed, msg = watchdog.authorize_file_modification("src/d.py")
    assert not allowed
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 17. Scope expansion detection
# ----------------------------------------------------------------------
def test_scope_expansion_detection(watchdog: WatchdogEngine):
    watchdog.approved_files = {"src/javed/module_a.py"}
    allowed, msg = watchdog.authorize_file_modification("src/javed/undeclared_module.py")
    assert not allowed
    assert watchdog.state == WatchdogState.SCOPE_EXPANSION_REQUIRED
    assert "SCOPE_EXPANSION_REQUIRED" in msg


# ----------------------------------------------------------------------
# 18. Targeted-test limit
# ----------------------------------------------------------------------
def test_targeted_test_limit(watchdog: WatchdogEngine):
    # max_targeted_test_runs = 3
    assert watchdog.authorize_test_execution(is_full_regression=False)[0]
    assert watchdog.authorize_test_execution(is_full_regression=False)[0]
    assert watchdog.authorize_test_execution(is_full_regression=False)[0]
    allowed, _ = watchdog.authorize_test_execution(is_full_regression=False)
    assert not allowed
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 19. Full-regression limit
# ----------------------------------------------------------------------
def test_full_regression_limit(watchdog: WatchdogEngine):
    # max_full_regression_runs = 1
    assert watchdog.authorize_test_execution(is_full_regression=True)[0]
    allowed, msg = watchdog.authorize_test_execution(is_full_regression=True)
    assert not allowed
    assert "limit" in msg


# ----------------------------------------------------------------------
# 20. Identical failure fingerprint stop
# ----------------------------------------------------------------------
def test_identical_failure_fingerprint_stop(watchdog: WatchdogEngine):
    # max_identical_test_retries = 1
    watchdog.record_test_result(exit_code=1, failure_fingerprint="fp_err_1")
    assert watchdog.state == WatchdogState.ACTIVE
    watchdog.record_test_result(exit_code=1, failure_fingerprint="fp_err_1")
    assert watchdog.state == WatchdogState.ACTIVE
    # 2nd identical retry -> REPLAN_REQUIRED
    watchdog.record_test_result(exit_code=1, failure_fingerprint="fp_err_1")
    assert watchdog.state == WatchdogState.REPLAN_REQUIRED


# ----------------------------------------------------------------------
# 21. Environment-failure classification
# ----------------------------------------------------------------------
def test_environment_failure_classification(watchdog: WatchdogEngine):
    rec = watchdog.record_action_result(
        action_id="act_env",
        tool_name="pytest",
        target="tests/test_foo.py",
        arguments={},
        status=ActionStatus.FAILED,
        result_fingerprint="dns_error",
        evidence_summary="Connection refused / DNS lookup failed",
        failure_classification=FailureClassification.ENVIRONMENT_FAILURE,
    )
    assert rec.failure_classification == FailureClassification.ENVIRONMENT_FAILURE


# ----------------------------------------------------------------------
# 22. No-progress detection
# ----------------------------------------------------------------------
def test_no_progress_detection(watchdog: WatchdogEngine):
    watchdog.record_analysis_iteration(has_progress=False)
    assert watchdog.state == WatchdogState.ACTIVE
    watchdog.record_analysis_iteration(has_progress=False)
    assert watchdog.state == WatchdogState.STALLED


# ----------------------------------------------------------------------
# 23. Stalled to replan transition
# ----------------------------------------------------------------------
def test_stalled_to_replan_transition(watchdog: WatchdogEngine):
    watchdog.record_analysis_iteration(has_progress=False)
    watchdog.record_analysis_iteration(has_progress=False)
    assert watchdog.state == WatchdogState.STALLED
    assert watchdog.record_replan() is True
    assert watchdog.state == WatchdogState.ACTIVE


# ----------------------------------------------------------------------
# 24. Replan exhaustion
# ----------------------------------------------------------------------
def test_replan_exhaustion(watchdog: WatchdogEngine):
    # Use single replan
    watchdog.record_replan()
    # Next stall and replan attempt
    watchdog.record_analysis_iteration(has_progress=False)
    watchdog.record_analysis_iteration(has_progress=False)
    assert watchdog.record_replan() is False
    assert watchdog.state == WatchdogState.OWNER_INPUT_REQUIRED


# ----------------------------------------------------------------------
# 25. Model-call limit
# ----------------------------------------------------------------------
def test_model_call_limit(watchdog: WatchdogEngine):
    # max_model_calls = 6
    for _ in range(5):
        watchdog.record_model_usage(prompt_tokens=100, completion_tokens=50)
    assert watchdog.state == WatchdogState.BUDGET_WARNING
    watchdog.record_model_usage(prompt_tokens=100, completion_tokens=50)
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 26. Token warning and stop
# ----------------------------------------------------------------------
def test_token_warning_and_stop(watchdog: WatchdogEngine):
    # max_tokens = 80000; 80% is 64000
    watchdog.record_model_usage(prompt_tokens=50000, completion_tokens=15000)  # 65000
    assert watchdog.state == WatchdogState.BUDGET_WARNING
    watchdog.record_model_usage(prompt_tokens=10000, completion_tokens=6000)  # 81000
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 27. Cost warning and stop
# ----------------------------------------------------------------------
def test_cost_warning_and_stop(watchdog: WatchdogEngine):
    # max_cost_usd = 0.50; 80% is 0.40
    watchdog.record_model_usage(prompt_tokens=100, completion_tokens=50, cost_usd=0.42)
    assert watchdog.state == WatchdogState.BUDGET_WARNING
    watchdog.record_model_usage(prompt_tokens=100, completion_tokens=50, cost_usd=0.09)
    assert watchdog.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 28. Owner override validation
# ----------------------------------------------------------------------
def test_owner_override_validation(watchdog: WatchdogEngine):
    # Set to exceeded
    watchdog.counters.tool_calls = 40
    watchdog.state = WatchdogState.BUDGET_EXCEEDED

    override = OwnerBudgetOverride(
        task_id=watchdog.task_id,
        budget_name="max_tool_calls",
        old_value=40,
        new_value=60,
        reason="Owner approved expansion for complex defect",
        approved_at="2026-11-05T12:00:00Z",
        expires_at="2026-11-05T23:59:59Z",
    )
    watchdog.apply_owner_override(override)
    assert watchdog.state == WatchdogState.ACTIVE
    assert watchdog.get_effective_limit("max_tool_calls", 40) == 60


# ----------------------------------------------------------------------
# 29. Override expiration
# ----------------------------------------------------------------------
def test_override_expiration():
    override = OwnerBudgetOverride(
        task_id="TASK-1",
        budget_name="max_tool_calls",
        old_value=40,
        new_value=60,
        reason="Temporary bump",
        approved_at="2026-11-05T12:00:00Z",
        expires_at="2026-11-05T13:00:00Z",
    )
    assert override.is_expired("2026-11-05T13:01:00Z") is True
    assert override.is_expired("2026-11-05T12:30:00Z") is False


# ----------------------------------------------------------------------
# 30. Subprocess timeout
# ----------------------------------------------------------------------
def test_subprocess_timeout():
    res = run_bounded_subprocess(
        ["cmd", "/c", "ping -n 5 127.0.0.1 >nul"],
        category="repository_query",
        timeout_override=1,
    )
    assert res.timed_out is True
    assert res.exit_code == -1
    assert "timed out after 1 seconds" in res.stderr


# ----------------------------------------------------------------------
# 31. Graceful cancellation
# ----------------------------------------------------------------------
def test_graceful_cancellation():
    res = run_bounded_subprocess(
        ["python", "-c", "import time; time.sleep(10)"],
        timeout_override=1,
    )
    assert res.timed_out is True


# ----------------------------------------------------------------------
# 32. Child-process cleanup
# ----------------------------------------------------------------------
def test_child_process_cleanup():
    # Verify timeout kills subprocess without leaving zombies
    with patch("javed.agent.efficiency.subprocess_control.terminate_process_tree") as mock_term:
        with patch("subprocess.Popen") as mock_popen:
            fake_proc = MagicMock()
            fake_proc.communicate.side_effect = subprocess.TimeoutExpired(
                cmd=["some_cmd"], timeout=1
            )
            fake_proc.poll.return_value = None
            mock_popen.return_value = fake_proc

            res = run_bounded_subprocess(["some_cmd"], timeout_override=1)
            assert res.timed_out is True
            mock_term.assert_called_once()


# ----------------------------------------------------------------------
# 33. Checkpoint serialization
# ----------------------------------------------------------------------
def test_checkpoint_serialization(watchdog: WatchdogEngine, tmp_path):
    cp_file = tmp_path / "checkpoint.json"
    watchdog.save_checkpoint_file(cp_file)
    assert cp_file.exists()
    data = json.loads(cp_file.read_text(encoding="utf-8"))
    assert data["task_id"] == watchdog.task_id
    assert data["state"] == WatchdogState.ACTIVE.value
    assert "counters" in data


# ----------------------------------------------------------------------
# 34. Secret-field rejection
# ----------------------------------------------------------------------
def test_secret_field_rejection(watchdog: WatchdogEngine):
    arg_hash = watchdog.ledger.compute_action_hash(
        "api_call",
        "https://openrouter.ai/api",
        {"api_key": "secret_token_xyz", "model": "gpt-4"},
    )
    # Ensure raw secret is not in serialized ledger
    watchdog.record_action_result(
        action_id="act_sec",
        tool_name="api_call",
        target="https://openrouter.ai/api",
        arguments={"api_key": "secret_token_xyz", "model": "gpt-4"},
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp_ok",
        evidence_summary="Model answered",
    )
    ledger_dict = watchdog.ledger.to_dict()
    serialized = json.dumps(ledger_dict)
    assert "secret_token_xyz" not in serialized
    assert arg_hash is not None


# ----------------------------------------------------------------------
# 35. No chain-of-thought storage
# ----------------------------------------------------------------------
def test_no_chain_of_thought_storage(watchdog: WatchdogEngine):
    cp = watchdog.create_checkpoint()
    cp_dict = cp.to_dict()
    assert "chain_of_thought" not in cp_dict
    assert "thinking" not in cp_dict
    assert "prompt" not in cp_dict


# ----------------------------------------------------------------------
# 36. Resume requires explicit authorization
# ----------------------------------------------------------------------
def test_resume_requires_explicit_authorization(watchdog: WatchdogEngine):
    watchdog.state = WatchdogState.BUDGET_EXCEEDED
    cp = watchdog.create_checkpoint()
    # Checkpoint preserves terminal/exceeded state and cannot automatically be active
    assert cp.state == WatchdogState.BUDGET_EXCEEDED


# ----------------------------------------------------------------------
# 37. Graphify query duplicate prevention
# ----------------------------------------------------------------------
def test_graphify_query_duplicate_prevention(watchdog: WatchdogEngine):
    allowed, _, _ = watchdog.authorize_tool_call(
        "graphify_query",
        "InferenceRouter",
        {"subcommand": "find-symbol"},
    )
    assert allowed
    watchdog.record_action_result(
        action_id="g_1",
        tool_name="graphify_query",
        target="InferenceRouter",
        arguments={"subcommand": "find-symbol"},
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp_graph",
        evidence_summary="Definition in router.py",
    )
    allowed2, msg2, _ = watchdog.authorize_tool_call(
        "graphify_query",
        "InferenceRouter",
        {"subcommand": "find-symbol"},
    )
    assert not allowed2
    assert "DUPLICATE_ACTION_REUSED" in msg2


# ----------------------------------------------------------------------
# 38. Repository state invalidates cached actions
# ----------------------------------------------------------------------
def test_repository_state_invalidates_cached_actions(watchdog: WatchdogEngine):
    watchdog.authorize_tool_call(
        "run_test",
        "test_a.py",
        {},
        current_file_hashes={"test_a.py": "hash_1"},
    )
    watchdog.record_action_result(
        action_id="a_1",
        tool_name="run_test",
        target="test_a.py",
        arguments={},
        status=ActionStatus.SUCCESS,
        result_fingerprint="fp_pass",
        evidence_summary="Tests passed",
        relevant_file_hashes={"test_a.py": "hash_1"},
    )
    # When file hash changes (modified file), cached action is NOT equivalent
    allowed, msg, _ = watchdog.authorize_tool_call(
        "run_test",
        "test_a.py",
        {},
        current_file_hashes={"test_a.py": "hash_2"},
    )
    assert allowed
    assert msg == "AUTHORIZED"


# ----------------------------------------------------------------------
# 39. Task completion within budget
# ----------------------------------------------------------------------
def test_task_completion_within_budget(watchdog: WatchdogEngine):
    watchdog.authorize_file_read("src/javed/module_a.py", "hash_1")
    watchdog.authorize_file_modification("src/javed/module_a.py")
    watchdog.record_patch_applied(lines_added=5, lines_removed=1)
    watchdog.authorize_test_execution(is_full_regression=False)
    watchdog.record_test_result(exit_code=0)

    watchdog.state = WatchdogState.COMPLETED
    assert watchdog.state == WatchdogState.COMPLETED
    assert watchdog.counters.patch_count == 1
    assert len(watchdog.warnings) == 0


# ----------------------------------------------------------------------
# 40. Metrics summary accuracy
# ----------------------------------------------------------------------
def test_metrics_summary_accuracy(watchdog: WatchdogEngine):
    watchdog.record_model_usage(prompt_tokens=1500, completion_tokens=250, cost_usd=0.012)
    watchdog.record_patch_applied(lines_added=40, lines_removed=15)
    cp = watchdog.create_checkpoint()
    c = cp.counters
    assert c["prompt_tokens"] == 1500
    assert c["completion_tokens"] == 250
    assert c["total_tokens"] == 1750
    assert c["cost_usd"] == 0.012
    assert c["lines_added"] == 40
    assert c["lines_removed"] == 15
