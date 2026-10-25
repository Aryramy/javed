"""Tests for Deep Agents Zero-Trust security profile and tool gating."""

import pytest
from deepagents.profiles.harness.harness_profiles import _get_harness_profile

from javed.agent.security import (
    ALLOWED_TOOLS,
    EXCLUDED_TOOLS,
    assert_safe_tools,
    ensure_agent_security_profile,
)


def test_excluded_tools_catalog() -> None:
    """Verify that EXCLUDED_TOOLS explicitly forbids all privileged and host-access tools."""
    mandatory_excluded = {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "eval",
        "task",
    }
    for tool_name in mandatory_excluded:
        assert tool_name in EXCLUDED_TOOLS, f"Mandatory security failure: {tool_name} not excluded"


def test_allowed_tools_catalog() -> None:
    """Verify that only safe state-only planning tools are permitted in BRICK-004."""
    assert ALLOWED_TOOLS == ["write_todos"]
    for allowed in ALLOWED_TOOLS:
        assert allowed not in EXCLUDED_TOOLS


def test_security_profile_registration() -> None:
    """Verify that ensure_agent_security_profile registers HarnessProfile with excluded tools."""
    ensure_agent_security_profile()
    profile = _get_harness_profile("openrouter")
    assert profile is not None
    assert profile.excluded_tools == EXCLUDED_TOOLS
    assert profile.general_purpose_subagent.enabled is False


def test_assert_safe_tools_passes_for_safe_tools() -> None:
    """Verify assert_safe_tools passes when only safe tools are registered."""
    safe_registry = {"write_todos": object()}
    # Should not raise
    assert_safe_tools(safe_registry)


def test_assert_safe_tools_rejects_privileged_tools() -> None:
    """Verify assert_safe_tools raises PermissionError when any privileged tool is detected."""
    unsafe_registry = {
        "write_todos": object(),
        "execute": object(),
    }
    with pytest.raises(PermissionError) as exc_info:
        assert_safe_tools(unsafe_registry)
    assert "Security Violation: Prohibited tools in agent registry" in str(exc_info.value)
    assert "execute" in str(exc_info.value)


def test_assert_safe_tools_rejects_filesystem_tools() -> None:
    """Verify assert_safe_tools raises PermissionError if filesystem operations are present."""
    for fs_tool in ("read_file", "write_file", "delete", "ls"):
        with pytest.raises(PermissionError):
            assert_safe_tools({fs_tool: object()})
