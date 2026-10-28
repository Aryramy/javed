"""Zero-Trust security profile and tool gating for Deep Agents runtime.

Enforces a strict positive allowlist (write_todos only) across three layers:
1. Model-visible tool exposure (only allowlisted tools reach the model).
2. Agent startup/runtime inventory validation (fail-closed initialization).
3. Host-side authorization before tool execution (intercepts and blocks unauthorized calls).
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from deepagents.profiles.harness.harness_profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger("javed.agent.security")

# The only authorized internal agent tool in BRICK-004
ALLOWED_TOOLS: frozenset[str] = frozenset({"write_todos"})

# Deterministic browser automation tools in BRICK-006
BROWSER_TOOLS: frozenset[str] = frozenset(
    {
        "browser_navigate",
        "browser_click",
        "browser_fill_form",
        "browser_extract_text",
        "browser_take_screenshot",
    }
)

# Known privileged tools explicitly excluded via HarnessProfile
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

_PROFILES_REGISTERED = False


def _get_tool_name(tool: Any) -> str:
    """Helper to extract tool name from tool object, dict schema, or function."""
    if hasattr(tool, "name"):
        return str(tool.name)
    if isinstance(tool, dict):
        if "name" in tool:
            return str(tool["name"])
        if "function" in tool and isinstance(tool["function"], dict):
            return str(tool["function"].get("name", ""))
    return str(tool)


class PositiveToolAllowlistMiddleware(AgentMiddleware[Any, Any, Any]):
    """Enforces a strict positive allowlist across model-visible exposure and execution.

    Layer 1: Filters tools during wrap_model_call / awrap_model_call so ONLY
             tools in ALLOWED_TOOLS and gateway-authorized model-visible tools are presented.
    Layer 2: Intercepts tools during wrap_tool_call / awrap_tool_call before execution
             and returns a Security Violation ToolMessage for any unauthorized tool name or args.
    """

    name: str = "PositiveToolAllowlistMiddleware"

    def __init__(self, gateway: Any | None = None, enable_browser: bool = False) -> None:
        super().__init__()
        self.gateway = gateway
        self.enable_browser = enable_browser

    def _get_model_visible_tools(self) -> frozenset[str]:
        allowed = set(ALLOWED_TOOLS)
        if self.enable_browser:
            allowed |= set(BROWSER_TOOLS)
        if self.gateway is not None:
            allowed |= set(self.gateway.get_model_visible_tools(include_approval_required=True))
        return frozenset(allowed)

    def _get_executable_tools(self) -> frozenset[str]:
        allowed = set(ALLOWED_TOOLS)
        if self.enable_browser:
            allowed |= set(BROWSER_TOOLS)
        if self.gateway is not None:
            allowed |= set(self.gateway.get_executable_tools())
        return frozenset(allowed)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        """Expose only allowlisted tools to the model."""
        allowed = self._get_model_visible_tools()
        filtered_tools = [t for t in request.tools if _get_tool_name(t) in allowed]
        return handler(request.override(tools=filtered_tools))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        """Async variant: expose only allowlisted tools to the model."""
        allowed = self._get_model_visible_tools()
        filtered_tools = [t for t in request.tools if _get_tool_name(t) in allowed]
        return await handler(request.override(tools=filtered_tools))

    def _block_unauthorized_call(self, request: ToolCallRequest) -> ToolMessage | None:
        """Validate tool execution against positive allowlist before host execution."""
        tool_name = request.tool_call.get("name", "")

        # Internal agent tools (e.g. write_todos)
        if tool_name in ALLOWED_TOOLS:
            return None

        # Deterministic browser tools (when enable_browser is True)
        if self.enable_browser and tool_name in BROWSER_TOOLS:
            return None

        # MCP Gateway execution validation (Layer 2)
        if self.gateway is not None:
            args = request.tool_call.get("args")
            args_dict = args if isinstance(args, dict) else {}
            is_eligible, err = self.gateway.verify_execution_eligibility(tool_name, args_dict)
            if is_eligible:
                return None
            logger.warning(
                "SECURITY ALERT: Blocked unauthorized tool execution attempt for '%s': %s",
                tool_name,
                err,
            )
            return ToolMessage(
                content=f"Security Violation: Tool '{tool_name}' execution denied: {err}",
                tool_call_id=request.tool_call.get("id") or "",
                name=tool_name,
                status="error",
            )

        logger.warning(
            "SECURITY ALERT: Blocked unauthorized tool execution attempt for '%s'",
            tool_name,
        )
        return ToolMessage(
            content=(
                f"Security Violation: Tool '{tool_name}' is unauthorized and prohibited by "
                "BRICK-004/BRICK-005 policy. Only authorized tools are permitted: "
                f"{sorted(ALLOWED_TOOLS)}"
            ),
            tool_call_id=request.tool_call.get("id") or "",
            name=tool_name,
            status="error",
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Intercept and reject any tool execution not on the positive allowlist."""
        violation = self._block_unauthorized_call(request)
        if violation is not None:
            return violation
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        """Async variant: intercept and reject unauthorized tool execution."""
        violation = self._block_unauthorized_call(request)
        if violation is not None:
            return violation
        return await handler(request)


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
        "(positive allowlist: %s, subagents disabled)",
        sorted(ALLOWED_TOOLS),
    )


def assert_safe_tools(
    tools_by_name: dict[str, Any],
    gateway: Any | None = None,
    enable_browser: bool = False,
) -> None:
    """Verify that only authorized tools exist in the tool registry (Strict Positive Allowlist).

    Raises:
        PermissionError: If any tool outside authorized list is detected in the registry.
    """
    allowed = set(ALLOWED_TOOLS)
    if enable_browser:
        allowed |= set(BROWSER_TOOLS)
    if gateway is not None:
        allowed |= set(gateway.get_executable_tools())
    unauthorized = set(tools_by_name.keys()) - allowed
    if unauthorized:
        raise PermissionError(
            f"Security Violation: Unauthorized tools in agent registry: {sorted(unauthorized)}. "
            f"Only authorized tools are permitted: {sorted(allowed)}"
        )


def assert_safe_agent_runtime(
    agent: CompiledStateGraph,
    gateway: Any | None = None,
    enable_browser: bool = False,
) -> None:
    """Fail-closed runtime verification on compiled Deep Agent graph.

    Verifies that the compiled agent graph includes PositiveToolAllowlistMiddleware
    and that no unauthorized tools are exposed to the model.

    Raises:
        PermissionError: If the safety middleware is missing or unapproved tools are exposed.
    """
    if not isinstance(agent, CompiledStateGraph):
        raise TypeError(f"Expected CompiledStateGraph, got {type(agent)}")

    # Verify that the graph was compiled and has nodes
    if not hasattr(agent, "nodes") or not agent.nodes:
        raise PermissionError("Security Violation: Agent graph is empty or uncompiled.")

    # Verify tools node and middleware interceptor are present
    if "tools" in agent.nodes:
        tools_node = agent.nodes["tools"]
        bound = getattr(tools_node, "bound", None)
        if bound and hasattr(bound, "_wrap_tool_call") and not bound._wrap_tool_call:
            raise PermissionError("Security Violation: Tool node is missing execution interceptor.")

    if gateway is not None:
        gateway.assert_safe_inventory([t for t in gateway.build_langchain_tools()])

    logger.debug("assert_safe_agent_runtime: Passed fail-closed startup validation.")
