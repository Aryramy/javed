"""Phase 8: Dual-Mode End-to-End Orchestration & LangGraph Agent Binding Tests.

Comprehensive integration tests covering all Phase 8 requirements:
1. Agent graph initialization with deterministic browser tools inventory bound.
2. Positive tool allowlist exposure filtering (browser tools visible, privileged tools excluded).
3. Multi-step browser planning execution (scripted model issuing navigation + text extraction).
4. HITL interruption and approval resumption for mutating browser actions (browser_click).
5. HITL rejection preventing mutating action dispatch (browser_fill_form).
6. Sensitive input argument redaction in execution telemetry and approval events.
7. Clean browser session lifecycle and teardown on AgentRuntimeManager.close().
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from javed.agent.runtime import AgentRuntimeManager
from javed.agent.security import (
    ALLOWED_TOOLS,
    BROWSER_TOOLS,
    PositiveToolAllowlistMiddleware,
    assert_safe_agent_runtime,
    assert_safe_tools,
)
from javed.browser.engine import BrowserEngineManager
from javed.browser.tools import BrowserSession, create_browser_tools_inventory
from javed.config import Settings
from javed.schemas.agent import AgentStreamRequest

# ---------------------------------------------------------------------------
# Test Helpers & Scripted Browser Models
# ---------------------------------------------------------------------------


class _ScriptedBrowserMultiStepModel(BaseChatModel):
    """Deterministic model that emits browser_navigate on turn 1,
    browser_extract_text on turn 2, then a final text summary on turn 3.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
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
                        "name": "browser_navigate",
                        "args": {"url": "https://example.com"},
                        "id": "call_nav_001",
                        "type": "tool_call",
                    }
                ],
            )
        elif self._turn_count == 2:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "browser_extract_text",
                        "args": {"selector": "body"},
                        "id": "call_ext_002",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Navigated to example.com and extracted page text.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-browser-multistep-model"


class _ScriptedBrowserMutatingModel(BaseChatModel):
    """Deterministic model that emits a mutating browser action (e.g. browser_click),
    requiring HITL approval, followed by a final completion message on resumption.
    """

    def __init__(
        self,
        tool_name: str = "browser_click",
        tool_args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_args = (
            tool_args if tool_args is not None else {"selector": "button#submit-action"}
        )
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
                        "id": "call_mut_001",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Mutating browser operation executed successfully.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-browser-mutating-model"


def _build_mock_browser_session() -> BrowserSession:
    """Construct a mock BrowserSession with deterministic return values."""
    mock_engine = MagicMock(spec=BrowserEngineManager)
    mock_engine.is_ready = True
    mock_session = BrowserSession(engine=mock_engine)

    mock_session.navigate = AsyncMock(
        return_value={
            "success": True,
            "url": "https://example.com",
            "title": "Example Domain",
            "status": 200,
        }
    )
    mock_session.click = AsyncMock(
        return_value={
            "success": True,
            "selector": "button#submit-action",
            "button": "left",
            "url": "https://example.com",
            "title": "Example Domain",
        }
    )
    mock_session.fill_form = AsyncMock(
        return_value={
            "success": True,
            "selector": "input#search-query",
            "value_length": 5,
            "url": "https://example.com",
        }
    )
    mock_session.extract_text = AsyncMock(
        return_value={
            "success": True,
            "selector": "body",
            "text": "This domain is for use in illustrative examples in documents.",
            "character_count": 64,
        }
    )
    mock_session.take_screenshot = AsyncMock(
        return_value={
            "success": True,
            "format": "jpeg",
            "data_bytes_length": 1024,
            "data_url": "data:image/jpeg;base64,mockbase64",
        }
    )
    mock_session.close = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_create_browser_tools_inventory_standalone() -> None:
    """Verify standalone factory returns all 5 tools with expected names and schemas."""
    tools = create_browser_tools_inventory()
    assert len(tools) == 5
    tool_names = {t.name for t in tools}
    assert tool_names == BROWSER_TOOLS


def test_positive_allowlist_middleware_with_browser_enabled() -> None:
    """Verify middleware exposes ALLOWED_TOOLS + BROWSER_TOOLS when enable_browser=True."""
    middleware = PositiveToolAllowlistMiddleware(enable_browser=True)
    visible = middleware._get_model_visible_tools()
    executable = middleware._get_executable_tools()

    assert visible == ALLOWED_TOOLS | BROWSER_TOOLS
    assert executable == ALLOWED_TOOLS | BROWSER_TOOLS
    assert "browser_navigate" in visible
    assert "browser_click" in visible
    assert "write_todos" in visible
    assert "read_file" not in visible
    assert "execute" not in visible


def test_assert_safe_tools_with_browser_tools() -> None:
    """Verify assert_safe_tools allows browser tools only when enable_browser=True."""
    tools_dict = {name: object() for name in BROWSER_TOOLS}
    tools_dict["write_todos"] = object()

    # Should succeed with enable_browser=True
    assert_safe_tools(tools_dict, enable_browser=True)

    # Should raise PermissionError when enable_browser=False
    with pytest.raises(PermissionError) as exc_info:
        assert_safe_tools(tools_dict, enable_browser=False)
    assert "Security Violation: Unauthorized tools" in str(exc_info.value)


@pytest.mark.asyncio
async def test_browser_agent_graph_compilation_and_status(tmp_path: Any) -> None:
    """Verify AgentRuntimeManager compiles state graph with browser tools bound and safe runtime."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    settings = Settings(
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
    )
    mock_session = _build_mock_browser_session()
    scripted_model = _ScriptedBrowserMultiStepModel()

    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_browser=True,
        browser_session=mock_session,
    )
    await runtime.initialize()

    checkpointer = MemorySaver()
    agent = runtime.create_agent(model=scripted_model, checkpointer=checkpointer)

    # Verify runtime validation passes fail-closed
    assert_safe_agent_runtime(agent, enable_browser=True)

    # Verify runtime status reports browser tools in allowed_tools
    status = await runtime.get_status()
    for b_tool in BROWSER_TOOLS:
        assert b_tool in status.allowed_tools

    await runtime.close()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_agent_e2e_multistep_execution(tmp_path: Any) -> None:
    """Verify end-to-end multi-step planning: navigate -> extract_text -> synthesis."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    settings = Settings(
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
    )
    mock_session = _build_mock_browser_session()
    scripted_model = _ScriptedBrowserMultiStepModel()

    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_browser=True,
        browser_session=mock_session,
    )
    await runtime.initialize()

    thread_id = f"test-thread-browser-{uuid.uuid4().hex[:6]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="Navigate to example.com and extract page content.",
    )

    events = []
    async for ev in runtime.stream_agent(req):
        events.append(ev)

    event_types = [e.event for e in events]
    assert "run_started" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "run_completed" in event_types

    # Verify both browser tools were invoked and completed
    completed_tools = [e.data.get("tool") for e in events if e.event == "tool_completed"]
    assert "browser_navigate" in completed_tools
    assert "browser_extract_text" in completed_tools

    # Verify mock was called
    mock_session.navigate.assert_awaited_once()
    mock_session.extract_text.assert_awaited_once()

    await runtime.close()


@pytest.mark.asyncio
async def test_browser_agent_e2e_hitl_approval_for_click(tmp_path: Any) -> None:
    """Verify mutating action (browser_click) triggers HITL interrupt and resumes on approval."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    settings = Settings(
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
    )
    mock_session = _build_mock_browser_session()
    scripted_model = _ScriptedBrowserMutatingModel(tool_name="browser_click")

    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_browser=True,
        browser_session=mock_session,
        browser_approval_required=True,
    )
    await runtime.initialize()

    thread_id = f"test-thread-click-{uuid.uuid4().hex[:6]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="Click the submit button.",
    )

    # 1. Initial invocation: must pause on approval_required
    events_turn1 = []
    async for ev in runtime.stream_agent(req):
        events_turn1.append(ev)

    approval_events = [e for e in events_turn1 if e.event == "approval_required"]
    assert len(approval_events) == 1
    appr_data = approval_events[0].data
    assert appr_data["tool_id"] == "browser_click"
    assert appr_data["server_id"] == "browser"
    approval_id = appr_data["approval_id"]

    # Verify click was NOT executed prior to approval
    mock_session.click.assert_not_awaited()

    # 2. Human approves: resume execution
    events_turn2 = []
    async for ev in runtime.resume_agent(
        thread_id=thread_id,
        approval_id=approval_id,
        decision="approve",
        reason="User verified safe button target",
    ):
        events_turn2.append(ev)

    turn2_types = [e.event for e in events_turn2]
    assert "approval_approved" in turn2_types
    assert "agent_resumed" in turn2_types
    assert "tool_started" in turn2_types
    assert "tool_completed" in turn2_types
    assert "run_completed" in turn2_types

    # Verify click WAS executed upon approval
    mock_session.click.assert_awaited_once()

    await runtime.close()


@pytest.mark.asyncio
async def test_browser_agent_e2e_hitl_rejection_for_fill(tmp_path: Any) -> None:
    """Verify mutating action (browser_fill_form) rejected by user does not execute."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    settings = Settings(
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
    )
    mock_session = _build_mock_browser_session()
    scripted_model = _ScriptedBrowserMutatingModel(
        tool_name="browser_fill_form",
        tool_args={"selector": "input#query", "value": "test query"},
    )

    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_browser=True,
        browser_session=mock_session,
        browser_approval_required=True,
    )
    await runtime.initialize()

    thread_id = f"test-thread-fill-{uuid.uuid4().hex[:6]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="Fill the query input.",
    )

    # 1. Initial invocation: must pause on approval_required
    events_turn1 = []
    async for ev in runtime.stream_agent(req):
        events_turn1.append(ev)

    approval_events = [e for e in events_turn1 if e.event == "approval_required"]
    assert len(approval_events) == 1
    approval_id = approval_events[0].data["approval_id"]

    # 2. Human rejects: resume with rejection
    events_turn2 = []
    async for ev in runtime.resume_agent(
        thread_id=thread_id,
        approval_id=approval_id,
        decision="reject",
        reason="Suspicious form target",
    ):
        events_turn2.append(ev)

    turn2_types = [e.event for e in events_turn2]
    assert "approval_rejected" in turn2_types
    assert "agent_resumed" in turn2_types
    assert "run_completed" in turn2_types

    # Verify form fill was NEVER executed
    mock_session.fill_form.assert_not_awaited()

    await runtime.close()


@pytest.mark.asyncio
async def test_browser_agent_sensitive_input_redacted_in_telemetry(tmp_path: Any) -> None:
    """Verify sensitive input in browser_fill_form is redacted in approval_required events."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    settings = Settings(
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
    )
    mock_session = _build_mock_browser_session()
    scripted_model = _ScriptedBrowserMutatingModel(
        tool_name="browser_fill_form",
        tool_args={
            "selector": "input[type='password']",
            "value": "super_secret_password_123",
            "allow_sensitive_override": True,
        },
    )

    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_browser=True,
        browser_session=mock_session,
        browser_approval_required=True,
    )
    await runtime.initialize()

    thread_id = f"test-thread-redact-{uuid.uuid4().hex[:6]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="Enter the password.",
    )

    events = []
    async for ev in runtime.stream_agent(req):
        events.append(ev)

    approval_events = [e for e in events if e.event == "approval_required"]
    assert len(approval_events) == 1
    appr_args = approval_events[0].data["arguments"]

    # Verify sensitive password value was redacted to '***REDACTED***'
    assert appr_args["value"] == "***REDACTED***"
    assert "super_secret_password_123" not in str(appr_args)

    await runtime.close()
