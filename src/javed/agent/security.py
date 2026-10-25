"""Zero-Trust security profile and tool gating for Deep Agents runtime."""

import logging
from typing import Any

from deepagents.profiles.harness.harness_profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

logger = logging.getLogger("javed.agent.security")

# Tools explicitly banned from model visibility and execution in BRICK-004
EXCLUDED_TOOLS: frozenset[str] = frozenset(
    {
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
)

ALLOWED_TOOLS: list[str] = ["write_todos"]

_PROFILES_REGISTERED = False


def ensure_agent_security_profile() -> None:
    """Register the mandatory Zero-Trust HarnessProfile for OpenRouter models.

    This ensures that whenever Deep Agents instantiates an agent with an OpenRouter
    model, all unapproved built-in filesystem, shell, interpreter, and subagent
    spawning tools are explicitly excluded from the model's tool surface and rejected
    at the execution boundary.
    """
    global _PROFILES_REGISTERED
    if _PROFILES_REGISTERED:
        return

    profile = HarnessProfile(
        excluded_tools=EXCLUDED_TOOLS,
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    )

    # Register for provider-wide defaults as well as specific router keys
    for key in ("openrouter", "openrouter/auto", "fake_test_model"):
        register_harness_profile(key, profile)

    _PROFILES_REGISTERED = True
    logger.info(
        "Registered Zero-Trust agent security profile for openrouter "
        "(excluded %d tools, subagents disabled)",
        len(EXCLUDED_TOOLS),
    )


def assert_safe_tools(tools_by_name: dict[str, Any]) -> None:
    """Verify that no unapproved or privileged tools are registered in the graph.

    Raises:
        PermissionError: If any prohibited tool is detected in the tool registry.
    """
    prohibited_found = set(tools_by_name.keys()) & EXCLUDED_TOOLS
    if prohibited_found:
        raise PermissionError(
            f"Security Violation: Prohibited tools in agent registry: {sorted(prohibited_found)}"
        )
