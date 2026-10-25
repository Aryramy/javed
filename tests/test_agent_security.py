"""Comprehensive tests for Deep Agents 3-Layer Zero-Trust Positive Allowlist Security."""

from typing import Any

import pytest
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.profiles.harness.harness_profiles import _get_harness_profile
from langchain.agents.middleware.todo import TodoListMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.security import (
    ALLOWED_TOOLS,
    EXCLUDED_TOOLS,
    PositiveToolAllowlistMiddleware,
    assert_safe_agent_runtime,
    assert_safe_tools,
    ensure_agent_security_profile,
)
from javed.schemas.agent import validate_thread_id


class _SpyModel(BaseChatModel):
    """Model that records tools received in bind_tools and emits a simulated response."""

    tools_bound: list[str] = []
    simulated_tool_call: dict[str, Any] | None = None

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        if self.simulated_tool_call:
            msg = AIMessage(
                content="",
                tool_calls=[self.simulated_tool_call],
            )
        else:
            msg = AIMessage(content="Safe response.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        _SpyModel.tools_bound = [getattr(t, "name", str(t)) for t in tools]
        return self

    @property
    def _llm_type(self) -> str:
        return "spy-model"


def test_positive_allowlist_catalog() -> None:
    """Verify that only write_todos is in ALLOWED_TOOLS and all privileged tools are excluded."""
    assert ALLOWED_TOOLS == frozenset({"write_todos"})
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
        assert tool_name in EXCLUDED_TOOLS
        assert tool_name not in ALLOWED_TOOLS


def test_security_profile_registration() -> None:
    """Verify ensure_agent_security_profile registers HarnessProfile with subagents disabled."""
    ensure_agent_security_profile()
    profile = _get_harness_profile("openrouter")
    assert profile is not None
    assert profile.excluded_tools == EXCLUDED_TOOLS
    assert profile.general_purpose_subagent.enabled is False


def test_assert_safe_tools_positive_allowlist() -> None:
    """Verify assert_safe_tools strictly requires tools to be in ALLOWED_TOOLS."""
    # Permitted: strictly write_todos
    assert_safe_tools({"write_todos": object()})

    # Prohibited: any tool not in ALLOWED_TOOLS (fail-closed)
    for unauthorized in (
        "execute",
        "read_file",
        "write_file",
        "delete",
        "ls",
        "bash",
        "custom_cmd",
    ):
        with pytest.raises(PermissionError) as exc_info:
            assert_safe_tools({"write_todos": object(), unauthorized: object()})
        assert "Security Violation: Unauthorized tools in agent registry" in str(exc_info.value)
        assert unauthorized in str(exc_info.value)


def test_positive_tool_allowlist_middleware_model_visible_exposure() -> None:
    """Layer 1: Verify that only allowlisted tools (write_todos) are exposed to the model."""
    _SpyModel.tools_bound = []
    model = _SpyModel()

    agent = create_deep_agent(
        model=model,
        middleware=[TodoListMiddleware(), PositiveToolAllowlistMiddleware()],
        backend=StateBackend(),
    )
    assert_safe_agent_runtime(agent)

    # Invoke agent to trigger model binding and middleware wrap_model_call
    _ = agent.invoke({"messages": [{"role": "user", "content": "Hello"}]})

    # The model must ONLY have seen write_todos; all filesystem tools must be filtered out
    assert _SpyModel.tools_bound == ["write_todos"]
    for prohibited in ("execute", "read_file", "write_file", "delete", "ls", "grep", "task"):
        assert prohibited not in _SpyModel.tools_bound


def test_positive_tool_allowlist_middleware_blocks_unauthorized_execution() -> None:
    """Layer 2: Verify executing unallowlisted tool is intercepted and blocked."""
    mw = PositiveToolAllowlistMiddleware()

    # 1. Allowed tool passes to handler
    def handler_ok(req: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="ok", tool_call_id=req.tool_call["id"], name=req.tool_call["name"]
        )

    req_ok = ToolCallRequest(
        tool_call={"name": "write_todos", "args": {"todos": []}, "id": "call_ok"},
        tool=None,
        state={},
        runtime=None,
    )
    res_ok = mw.wrap_tool_call(req_ok, handler_ok)
    assert isinstance(res_ok, ToolMessage)
    assert res_ok.content == "ok"

    # 2. Unauthorized tool ('execute') is blocked before execution
    called_handler = False

    def handler_should_not_run(req: ToolCallRequest) -> ToolMessage:
        nonlocal called_handler
        called_handler = True
        return ToolMessage(content="EXECUTED", tool_call_id="call_bad", name="execute")

    for bad_tool in ("execute", "read_file", "write_file", "delete", "arbitrary_eval"):
        req_bad = ToolCallRequest(
            tool_call={"name": bad_tool, "args": {"cmd": "whoami"}, "id": f"call_{bad_tool}"},
            tool=None,
            state={},
            runtime=None,
        )
        res_bad = mw.wrap_tool_call(req_bad, handler_should_not_run)
        assert called_handler is False, (
            f"Security failure: Handler executed for unauthorized tool {bad_tool}"
        )
        assert isinstance(res_bad, ToolMessage)
        assert res_bad.status == "error"
        assert f"Tool '{bad_tool}' is unauthorized" in res_bad.content


@pytest.mark.asyncio
async def test_positive_tool_allowlist_async_interception() -> None:
    """Verify async variant of tool execution interception blocks unauthorized calls."""
    mw = PositiveToolAllowlistMiddleware()

    async def async_handler_should_not_run(req: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("Host execution occurred! Security failed.")

    req = ToolCallRequest(
        tool_call={"name": "shell_exec", "args": {}, "id": "call_async_1"},
        tool=None,
        state={},
        runtime=None,
    )
    res = await mw.awrap_tool_call(req, async_handler_should_not_run)
    assert isinstance(res, ToolMessage)
    assert res.status == "error"
    assert "Security Violation: Tool 'shell_exec' is unauthorized" in res.content


def test_thread_id_validation_rejects_unsafe_identifiers() -> None:
    """Verify strict server-side thread ID validation rejects traversal and malformed inputs."""
    invalid_ids = [
        "../traversal",
        "..\\windows_traversal",
        "/etc/passwd",
        "thread/123",
        "thread 123",
        "thread;drop table",
        "thread$special",
        "thread\x00null",
        "",
        "   ",
        "a" * 129,  # exceeds 128 chars
    ]
    for bad_id in invalid_ids:
        with pytest.raises(ValueError):
            validate_thread_id(bad_id)


def test_thread_id_validation_accepts_valid_identifiers() -> None:
    """Verify thread ID validation accepts legitimate JAVED thread identifiers."""
    valid_ids = [
        "thread-1",
        "thread_orchid",
        "thread-20cd8abd",
        "session_2026_10_25",
        "ABC-123_xyz",
    ]
    for good_id in valid_ids:
        assert validate_thread_id(good_id) == good_id
