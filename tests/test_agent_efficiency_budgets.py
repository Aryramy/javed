"""test_agent_efficiency_budgets.py — Unit tests for budget profiles and constraints."""

import pytest

from javed.agent.efficiency.budgets import (
    DEFAULT_BUDGET_PROFILES,
    GLOBAL_MAX_DURATION_SECONDS,
    TaskBudgetProfile,
    TaskClass,
    get_budget_profile,
)


def test_budget_profile_validation():
    profile = get_budget_profile(TaskClass.SINGLE_FILE_DEFECT)
    assert profile.max_duration_seconds == 1200
    assert profile.max_files_modified == 3
    assert profile.max_cost_usd == 0.50


def test_unknown_task_class_rejection():
    with pytest.raises(ValueError, match="Unknown task class"):
        get_budget_profile("non_existent_class")


def test_negative_limit_rejection():
    with pytest.raises(ValueError, match="max_duration_seconds must be positive"):
        TaskBudgetProfile(
            task_class=TaskClass.DOCUMENTATION,
            max_duration_seconds=-10,
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
        )


def test_global_max_duration_ceiling():
    with pytest.raises(ValueError, match="exceeds global ceiling"):
        TaskBudgetProfile(
            task_class=TaskClass.ARCHITECTURE_CHANGE,
            max_duration_seconds=GLOBAL_MAX_DURATION_SECONDS + 1,
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
        )


def test_all_six_canonical_profiles_exist():
    for tc in TaskClass:
        assert tc in DEFAULT_BUDGET_PROFILES
        profile = DEFAULT_BUDGET_PROFILES[tc]
        assert profile.max_duration_seconds <= GLOBAL_MAX_DURATION_SECONDS
        assert profile.max_cost_usd > 0
