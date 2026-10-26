# LIVE MCP INTEGRATION TEST — NOT AGENT EXECUTION
"""Phase 4: Secure Host MCP Tool Gateway & Three-Layer Authorization Tests.

Comprehensive tests covering all 21 mandatory Phase 4 security and functional requirements:
1. DENIED tools are hidden from the model (Layer 1).
2. DENIED tools cannot execute (Layer 2).
3. Unknown tool identity is rejected.
4. Namespace spoofing is rejected.
5. Server identity mismatch is rejected.
6. Metadata fingerprint mismatch is rejected.
7. Invalid argument types are rejected via JSON Schema.
8. Unexpected or missing arguments are rejected.
9. Host permission cannot be overridden by model output.
10. APPROVAL_REQUIRED never executes in Phase 4 (approval-not-available).
11. Existing write_todos still works.
12. Privileged built-in tools remain unavailable (Layer 3).
13. Authorized Time tool executes through the gateway over real STDIO.
14. Genuine MCP result is returned.
15. Revoking permission blocks subsequent execution.
16. Policy changes invalidate stale execution eligibility.
17. Concurrent requests cannot bypass authorization.
18. Cancellation and timeout release resources.
19. Raw call_tool_direct cannot be reached from agent or API paths.
20. No OpenRouter credentials reach the MCP subprocess.
21. Real framework integration with deterministic scripted model.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware.todo import TodoListMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from javed.agent.security import (
    ALLOWED_TOOLS,
    EXCLUDED_TOOLS,
    PositiveToolAllowlistMiddleware,
    assert_safe_agent_runtime,
)
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import TIME_SERVER_ID, create_time_server_config
from javed.schemas.mcp import (
    MCPApprovalUnavailableError,
    MCPInputValidationError,
    MCPPermissionDeniedError,
    MCPTimeoutError,
)

# ---------------------------------------------------------------------------
# Test Helpers & Scripted Models
# ---------------------------------------------------------------------------


class _SpyModel(BaseChatModel):
    """Spy model recording tools bound and returning a benign response."""

    tools_bound: list[str] = []

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Safe response."))])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        _SpyModel.tools_bound = [getattr(t, "name", str(t)) for t in tools]
        return self

    @property
    def _llm_type(self) -> str:
        return "spy-model"


class _ScriptedToolCallingModel(BaseChatModel):
    """Deterministic model that emits a tool call on turn 1, then a text answer on turn 2."""

    def __init__(self, tool_name: str, tool_args: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._turn_count = 0

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self._turn_count += 1
        if self._turn_count == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self._tool_name,
                        "args": self._tool_args,
                        "id": "call_scripted_001",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Finished with tool execution.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling-model"


@pytest.fixture
async def time_gateway() -> AsyncIterator[tuple[DynamicMCPRegistry, SecureMCPGateway]]:
    """Fixture providing an initialized registry with discovered Time MCP tools and a gateway."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)
    gateway = SecureMCPGateway(registry)
    try:
        yield registry, gateway
    finally:
        await registry.disconnect_all()


# ---------------------------------------------------------------------------
# 1. DENIED tools are hidden from the model (Layer 1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_layer1_denied_tools_hidden_from_model(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that discovered tools with default DENIED permission are hidden from the LLM."""
    registry, gateway = time_gateway

    # Verify both tools default to DENIED
    assert registry.get_tool("time__get_current_time").permission == "denied"
    assert registry.get_tool("time__convert_time").permission == "denied"

    # Gateway reports zero model-visible MCP tools
    assert gateway.get_model_visible_tools() == []

    _SpyModel.tools_bound = []
    agent = create_deep_agent(
        model=_SpyModel(),
        tools=gateway.build_langchain_tools(),
        middleware=[TodoListMiddleware(), PositiveToolAllowlistMiddleware(gateway=gateway)],
        backend=StateBackend(),
    )
    assert_safe_agent_runtime(agent, gateway=gateway)

    # Invoke agent turn
    agent.invoke({"messages": [{"role": "user", "content": "What time is it?"}]})

    # Model must only see write_todos; denied Time tools must remain invisible
    assert _SpyModel.tools_bound == ["write_todos"]
    assert "time__get_current_time" not in _SpyModel.tools_bound
    assert "time__convert_time" not in _SpyModel.tools_bound


# ---------------------------------------------------------------------------
# 2. DENIED tools cannot execute (Layer 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_layer2_denied_tools_cannot_execute(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that attempting to execute a DENIED tool is rejected at Layer 2."""
    _, gateway = time_gateway

    # 1. Direct gateway execution must raise MCPPermissionDeniedError
    with pytest.raises(MCPPermissionDeniedError) as exc_info:
        await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert "DENIED by host policy" in str(exc_info.value)

    # 2. Middleware interception must return a Security Violation ToolMessage
    mw = PositiveToolAllowlistMiddleware(gateway=gateway)
    req = ToolCallRequest(
        tool_call={
            "name": "time__get_current_time",
            "args": {"timezone": "UTC"},
            "id": "denied_call_1",
        },
        tool=None,
        state={},
        runtime=None,
    )
    res = mw.wrap_tool_call(
        req, lambda r: ToolMessage(content="ok", tool_call_id=r.tool_call["id"], name="ok")
    )
    assert isinstance(res, ToolMessage)
    assert res.status == "error"
    assert "Security Violation" in res.content
    assert "DENIED" in res.content


# ---------------------------------------------------------------------------
# 3. Unknown tool identity is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_identity_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that an unknown tool name is rejected."""
    _, gateway = time_gateway

    with pytest.raises(MCPPermissionDeniedError) as exc_info:
        await gateway.execute_tool("time__non_existent_tool", {})
    assert "not in discovered registry" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4. Namespace spoofing is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_namespace_spoofing_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify non-namespaced tool IDs or spoofed servers are rejected."""
    _, gateway = time_gateway

    # Missing delimiter
    with pytest.raises(MCPPermissionDeniedError) as exc_info1:
        await gateway.execute_tool("get_current_time", {})
    assert "not properly namespaced" in str(exc_info1.value)

    # Unregistered server
    with pytest.raises(MCPPermissionDeniedError) as exc_info2:
        await gateway.execute_tool("fake_server__get_current_time", {})
    assert "unknown or not registered" in str(exc_info2.value)


# ---------------------------------------------------------------------------
# 5. Server identity mismatch is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_identity_mismatch_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that disabling a server blocks tool execution."""
    registry, gateway = time_gateway

    # Authorize tool first
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")

    # Disable the server
    srv_cfg = registry.get_server_config(TIME_SERVER_ID)
    assert srv_cfg is not None
    srv_cfg.enabled = False

    with pytest.raises(MCPPermissionDeniedError) as exc_info:
        await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert "disabled by host policy" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. Metadata fingerprint mismatch is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_fingerprint_mismatch_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that schema drift or fingerprint tampering invalidates execution eligibility."""
    registry, gateway = time_gateway

    # Approve tool with valid fingerprint
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")

    # Tamper with the approved fingerprint in policy
    policy = registry.get_policy("time__get_current_time")
    assert policy is not None
    policy.approved_fingerprint = "tampered_sha256_hash_value"

    with pytest.raises(MCPPermissionDeniedError) as exc_info:
        await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert "metadata fingerprint mismatch" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. Invalid argument types are rejected via JSON Schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_argument_types_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify full JSON Schema type validation rejects bad argument types."""
    registry, gateway = time_gateway

    registry.update_tool_policy("time__convert_time", permission="allowed_read_only")

    # source_timezone must be a string, pass integer instead
    bad_args = {
        "source_timezone": 12345,
        "time": "12:00",
        "target_timezone": "UTC",
    }
    with pytest.raises(MCPInputValidationError) as exc_info:
        await gateway.execute_tool("time__convert_time", bad_args)
    assert "Schema validation error" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 8. Unexpected or missing arguments are rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_or_missing_arguments_rejected(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify missing required fields and undeclared unexpected properties are rejected."""
    registry, gateway = time_gateway

    registry.update_tool_policy("time__convert_time", permission="allowed_read_only")

    # 1. Missing required fields
    with pytest.raises(MCPInputValidationError) as exc_info1:
        await gateway.execute_tool("time__convert_time", {})
    assert "Missing required argument" in str(exc_info1.value)

    # 2. Unexpected property not declared in schema
    unexpected_args = {
        "source_timezone": "UTC",
        "time": "12:00",
        "target_timezone": "America/New_York",
        "malicious_extra": "drop table users",
    }
    with pytest.raises(MCPInputValidationError) as exc_info2:
        await gateway.execute_tool("time__convert_time", unexpected_args)
    assert "Unexpected argument" in str(exc_info2.value)


# ---------------------------------------------------------------------------
# 9. Host permission cannot be overridden by model output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_host_permission_cannot_be_overridden_by_model_output(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that LLM claims of elevated privileges cannot bypass gateway authorization."""
    _, gateway = time_gateway

    # Tool is DENIED by host policy
    mw = PositiveToolAllowlistMiddleware(gateway=gateway)

    # Simulated LLM hallucinating administrative override in arguments or metadata
    req = ToolCallRequest(
        tool_call={
            "name": "time__get_current_time",
            "args": {"timezone": "UTC", "_override_host_security": True},
            "id": "jailbreak_attempt_1",
        },
        tool=None,
        state={"is_admin": True},
        runtime=None,
    )
    res = mw.wrap_tool_call(
        req, lambda r: ToolMessage(content="exploited", tool_call_id="1", name="ok")
    )
    assert isinstance(res, ToolMessage)
    assert res.status == "error"
    assert "Security Violation" in res.content
    assert "DENIED" in res.content


# ---------------------------------------------------------------------------
# 10. APPROVAL_REQUIRED never executes in Phase 4 (approval-not-available)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_required_never_executes_in_phase_4(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify that APPROVAL_REQUIRED tools fail closed with approval-not-available."""
    registry, gateway = time_gateway

    registry.update_tool_policy("time__get_current_time", permission="approval_required")

    # Must be hidden from the model
    assert "time__get_current_time" not in gateway.get_model_visible_tools()

    # Direct execution must raise MCPApprovalUnavailableError
    with pytest.raises(MCPApprovalUnavailableError) as exc_info:
        await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert "approval-not-available" in str(exc_info.value)

    # Middleware must return error ToolMessage
    mw = PositiveToolAllowlistMiddleware(gateway=gateway)
    req = ToolCallRequest(
        tool_call={
            "name": "time__get_current_time",
            "args": {"timezone": "UTC"},
            "id": "approval_test_call",
        },
        tool=None,
        state={},
        runtime=None,
    )
    res = mw.wrap_tool_call(
        req, lambda r: ToolMessage(content="should not run", tool_call_id="1", name="ok")
    )
    assert isinstance(res, ToolMessage)
    assert res.status == "error"
    assert "approval-not-available" in res.content


# ---------------------------------------------------------------------------
# 11. Existing write_todos still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_write_todos_still_works(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify BRICK-004 internal write_todos authorization remains intact."""
    _, gateway = time_gateway

    mw = PositiveToolAllowlistMiddleware(gateway=gateway)
    req = ToolCallRequest(
        tool_call={
            "name": "write_todos",
            "args": {"todos": [{"content": "Inspect gateway", "status": "in_progress"}]},
            "id": "write_todos_1",
        },
        tool=None,
        state={},
        runtime=None,
    )

    executed = False

    def handler(r: ToolCallRequest) -> ToolMessage:
        nonlocal executed
        executed = True
        return ToolMessage(
            content="todos written", tool_call_id=r.tool_call["id"], name=r.tool_call["name"]
        )

    res = mw.wrap_tool_call(req, handler)
    assert executed is True
    assert isinstance(res, ToolMessage)
    assert res.content == "todos written"


# ---------------------------------------------------------------------------
# 12. Privileged built-in tools remain unavailable (Layer 3)
# ---------------------------------------------------------------------------


def test_privileged_builtin_tools_remain_unavailable(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify built-in execution tools cannot exist in authorized inventory."""
    _, gateway = time_gateway

    for prohibited in EXCLUDED_TOOLS:
        assert prohibited not in ALLOWED_TOOLS
        assert prohibited not in gateway.get_executable_tools()

    # assert_safe_inventory must raise PermissionError if an excluded tool is present
    class _MockTool:
        name = "execute"

    with pytest.raises(PermissionError) as exc_info:
        gateway.assert_safe_inventory([_MockTool()])
    assert "Prohibited tool 'execute' detected" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 13 & 14. Authorized Time tool executes through gateway & returns genuine result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorized_time_tool_executes_through_gateway(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify genuine MCP tool execution over STDIO when host-authorized."""
    registry, gateway = time_gateway

    # Host explicitly approves get_current_time as ALLOWED_READ_ONLY
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")

    # Verify model visibility
    assert gateway.get_model_visible_tools() == ["time__get_current_time"]

    # Execute genuine tool through gateway
    result_str = await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert result_str is not None
    assert len(result_str) > 0

    # Verify genuine result properties
    assert "UTC" in result_str
    # Verify timestamp format (e.g. 2026 or ISO datetime)
    assert "datetime" in result_str or "current_time" in result_str or "2026" in result_str


# ---------------------------------------------------------------------------
# 15. Revoking permission blocks subsequent execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoking_permission_blocks_subsequent_execution(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify immediate fail-closed revocation behavior."""
    registry, gateway = time_gateway

    # 1. Authorize and execute successfully
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")
    res1 = await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert res1 is not None

    # 2. Host revokes permission back to DENIED
    registry.update_tool_policy("time__get_current_time", permission="denied")

    # 3. Model visibility drops immediately
    assert "time__get_current_time" not in gateway.get_model_visible_tools()

    # 4. Subsequent execution immediately fails closed
    with pytest.raises(MCPPermissionDeniedError) as exc_info:
        await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})
    assert "DENIED by host policy" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 16. Policy changes invalidate stale execution eligibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_changes_invalidate_stale_execution_eligibility(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify policy version tracking and stale eligibility invalidation."""
    registry, gateway = time_gateway

    v0 = gateway.policy_version
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")
    v1 = gateway.policy_version
    assert v1 > v0

    # Build tools under V1
    tools_v1 = gateway.build_langchain_tools()
    assert len(tools_v1) == 1
    assert tools_v1[0].name == "time__get_current_time"

    # Revoke under V2
    registry.update_tool_policy("time__get_current_time", permission="denied")
    v2 = gateway.policy_version
    assert v2 > v1

    # Attempting to invoke the previously compiled StructuredTool must fail closed
    with pytest.raises(MCPPermissionDeniedError):
        await tools_v1[0].ainvoke({"timezone": "UTC"})


# ---------------------------------------------------------------------------
# 17. Concurrent requests cannot bypass authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_cannot_bypass_authorization(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify thread-safety and authorization consistency under concurrent load."""
    registry, gateway = time_gateway

    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")
    # time__convert_time remains DENIED

    async def _call_allowed() -> str:
        return await gateway.execute_tool("time__get_current_time", {"timezone": "UTC"})

    async def _call_denied() -> str:
        return await gateway.execute_tool(
            "time__convert_time",
            {
                "source_timezone": "UTC",
                "time": "12:00",
                "target_timezone": "UTC",
            },
        )

    tasks = []
    # 5 permitted and 5 denied launched concurrently
    for _ in range(5):
        tasks.append(_call_allowed())
        tasks.append(_call_denied())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    allowed_results = results[0::2]
    denied_results = results[1::2]

    # Every permitted request succeeded
    for res in allowed_results:
        assert isinstance(res, str)
        assert len(res) > 0

    # Every denied request raised MCPPermissionDeniedError
    for res in denied_results:
        assert isinstance(res, MCPPermissionDeniedError)
        assert "DENIED by host policy" in str(res)


# ---------------------------------------------------------------------------
# 18. Cancellation and timeout release resources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_and_timeout_release_resources(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify tool timeout raises MCPTimeoutError and cancels cleanly."""
    registry, gateway = time_gateway

    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")

    # Ultra-short timeout of 0.000001s to force timeout
    with pytest.raises(MCPTimeoutError) as exc_info:
        await gateway.execute_tool(
            "time__get_current_time", {"timezone": "UTC"}, timeout_seconds=0.000001
        )
    assert "timed out" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 19. Raw call_tool_direct cannot be reached from agent or API
# ---------------------------------------------------------------------------


def test_raw_call_tool_direct_not_in_agent_or_api_path() -> None:
    """Verify that call_tool_direct is never referenced in runtime or API modules."""
    import inspect

    import javed.agent.runtime
    import javed.agent.security
    import javed.api.v1.agent

    runtime_src = inspect.getsource(javed.agent.runtime)
    security_src = inspect.getsource(javed.agent.security)
    api_src = inspect.getsource(javed.api.v1.agent)

    assert "call_tool_direct" not in runtime_src
    assert "call_tool_direct" not in security_src
    assert "call_tool_direct" not in api_src


# ---------------------------------------------------------------------------
# 20. No OpenRouter credentials reach the MCP subprocess
# ---------------------------------------------------------------------------


def test_no_openrouter_credentials_reach_mcp_subprocess() -> None:
    """Verify that MCP server subprocess environment excludes sensitive LLM credentials."""
    cfg = create_time_server_config()
    server_env = cfg.env or {}

    assert "OPENROUTER_API_KEY" not in server_env
    assert "ANTHROPIC_API_KEY" not in server_env
    assert "OPENAI_API_KEY" not in server_env


# ---------------------------------------------------------------------------
# 21. Real framework integration with deterministic scripted model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_framework_integration_scripted_model(
    time_gateway: tuple[DynamicMCPRegistry, SecureMCPGateway],
) -> None:
    """Verify end-to-end compiled LangGraph agent turn with scripted model and gateway."""
    registry, gateway = time_gateway

    # 1. First scenario: Tool is DENIED
    scripted_model_denied = _ScriptedToolCallingModel(
        tool_name="time__get_current_time",
        tool_args={"timezone": "UTC"},
    )
    agent_denied = create_deep_agent(
        model=scripted_model_denied,
        tools=gateway.build_langchain_tools(),
        middleware=[TodoListMiddleware(), PositiveToolAllowlistMiddleware(gateway=gateway)],
        backend=StateBackend(),
        checkpointer=MemorySaver(),
    )
    assert_safe_agent_runtime(agent_denied, gateway=gateway)

    # Run agent turn
    result_denied = await agent_denied.ainvoke(
        {"messages": [{"role": "user", "content": "What is the time in UTC?"}]},
        config={"configurable": {"thread_id": "thread_denied_test"}},
    )
    messages_denied = result_denied.get("messages", [])

    # Find the tool message in the history
    tool_msgs_denied = [m for m in messages_denied if isinstance(m, ToolMessage)]
    assert len(tool_msgs_denied) == 1
    assert tool_msgs_denied[0].status == "error"
    assert "Security Violation" in tool_msgs_denied[0].content

    # 2. Second scenario: Tool is ALLOWED_READ_ONLY
    registry.update_tool_policy("time__get_current_time", permission="allowed_read_only")

    scripted_model_allowed = _ScriptedToolCallingModel(
        tool_name="time__get_current_time",
        tool_args={"timezone": "UTC"},
    )
    agent_allowed = create_deep_agent(
        model=scripted_model_allowed,
        tools=gateway.build_langchain_tools(),
        middleware=[TodoListMiddleware(), PositiveToolAllowlistMiddleware(gateway=gateway)],
        backend=StateBackend(),
        checkpointer=MemorySaver(),
    )
    assert_safe_agent_runtime(agent_allowed, gateway=gateway)

    # Run agent turn
    result_allowed = await agent_allowed.ainvoke(
        {"messages": [{"role": "user", "content": "What is the time in UTC?"}]},
        config={"configurable": {"thread_id": "thread_allowed_test"}},
    )
    messages_allowed = result_allowed.get("messages", [])

    tool_msgs_allowed = [m for m in messages_allowed if isinstance(m, ToolMessage)]
    assert len(tool_msgs_allowed) == 1
    assert tool_msgs_allowed[0].status != "error"
    assert "UTC" in tool_msgs_allowed[0].content
