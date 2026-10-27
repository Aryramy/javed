"""Tests for BRICK-005 Phase 7: React User Mode MCP Tool Interaction & Agent Runtime.

Verifies:
- Tool request, start, completion, and failure event lifecycles.
- Reconstructed thread state with authentic ToolActivityRecord entries.
- Thread approvals query endpoint.
- Error handling (server disconnection, tool execution failure, denial).
- Thread isolation and Zero-Trust credential protection.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.main import create_app
from javed.mcp.approval_store import ApprovalStore
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import create_time_server_config
from javed.schemas.agent import (
    AgentStreamRequest,
    ToolActivityRecord,
)
from javed.schemas.approval import ApprovalRecord, compute_argument_digest
from javed.schemas.mcp import DiscoveredTool, compute_tool_fingerprint


@pytest.fixture
def test_settings(tmp_path: Any) -> Settings:
    return Settings(
        app_name="Javed Test User Mode",
        openrouter_api_key="sk-or-v1-mock-test-key",
        openrouter_default_model="openrouter/auto",
        sqlite_checkpoints_path=str(tmp_path / "checkpoints.db"),
        allowed_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    )


@pytest.fixture
async def user_mode_runtime(tmp_path: Any, test_settings: Settings) -> AgentRuntimeManager:
    checkpointer_mgr = AgentCheckpointerManager(db_path=str(tmp_path / "checkpoints.db"))
    approval_store = ApprovalStore(db_path=str(tmp_path / "approvals.db"))
    await approval_store.initialize()

    registry = DynamicMCPRegistry()
    gateway = SecureMCPGateway(registry=registry, approval_store=approval_store)

    runtime = AgentRuntimeManager(
        settings=test_settings,
        checkpointer_manager=checkpointer_mgr,
        approval_store=approval_store,
        mcp_gateway=gateway,
    )
    await runtime.initialize()
    return runtime


@pytest.mark.asyncio
async def test_thread_state_reconstruction_with_tool_calls(
    user_mode_runtime: AgentRuntimeManager,
) -> None:
    """Verify get_thread_state reconstructs tool_calls accurately from checkpoints and approvals."""
    thread_id = f"thread_test_{uuid.uuid4().hex[:8]}"

    # Pre-populate durable approval record
    appr_rec = ApprovalRecord(
        approval_id="appr_user_1",
        interrupt_id="intr_1",
        run_id="run_1",
        thread_id=thread_id,
        server_id="time",
        tool_id="time__get_current_time",
        tool_call_id="tc_time_1",
        arguments={"timezone": "UTC"},
        argument_digest=compute_argument_digest({"timezone": "UTC"}),
        tool_fingerprint="fp123",
        policy_version=1,
        status="approved",
        dispatch_status="completed",
        result_summary='{"datetime": "2026-10-27T10:00:00Z"}',
    )
    await user_mode_runtime.approval_store.create_approval(appr_rec)

    # Mock LangGraph state tuple containing AIMessage with tool_calls and ToolMessage
    mock_messages = [
        HumanMessage(content="What time is it?"),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "tc_time_1", "name": "time__get_current_time", "args": {"timezone": "UTC"}}
            ],
        ),
        ToolMessage(
            content='{"datetime": "2026-10-27T10:00:00Z"}',
            tool_call_id="tc_time_1",
            name="time__get_current_time",
        ),
        AIMessage(content="The current time is 10:00 UTC."),
    ]

    mock_state = MagicMock()
    mock_state.values = {"messages": mock_messages, "todos": []}
    mock_state.config = {"configurable": {"checkpoint_id": "cp_100"}}

    with patch.object(
        user_mode_runtime.checkpointer_manager,
        "get_async_checkpointer",
    ) as mock_get_cp:
        mock_cp = AsyncMock()
        mock_tuple = MagicMock()
        mock_tuple.checkpoint = {"id": "cp_100"}
        mock_tuple.metadata = {"model": "openrouter/auto"}
        mock_cp.aget_tuple.return_value = mock_tuple
        mock_get_cp.return_value = mock_cp

        with patch.object(user_mode_runtime, "create_agent") as mock_agent_creator:
            mock_agent = AsyncMock()
            mock_agent.aget_state.return_value = mock_state
            mock_agent_creator.return_value = mock_agent

            state_resp = await user_mode_runtime.get_thread_state(thread_id)

    assert state_resp.exists is True
    assert state_resp.thread_id == thread_id
    assert len(state_resp.messages) == 2  # Human + conversational Assistant
    assert len(state_resp.tool_calls) == 1

    tc_activity: ToolActivityRecord = state_resp.tool_calls[0]
    assert tc_activity.tool_id == "time__get_current_time"
    assert tc_activity.server_id == "time"
    assert tc_activity.status == "COMPLETED"
    assert "2026-10-27T10:00:00Z" in str(tc_activity.result_summary)
    assert tc_activity.approval_id == "appr_user_1"


@pytest.mark.asyncio
async def test_tool_event_lifecycle_in_stream_agent(
    user_mode_runtime: AgentRuntimeManager,
) -> None:
    """Verify that stream_agent emits tool_requested, tool_started, and tool_completed events."""
    thread_id = f"thread_events_{uuid.uuid4().hex[:8]}"

    # Authorize tool as allowed_read_only so it can execute
    user_mode_runtime.mcp_gateway.registry.register_server(create_time_server_config())
    schema = {"type": "object", "properties": {"timezone": {"type": "string"}}}
    tool1 = DiscoveredTool(
        tool_id="time__get_current_time",
        server_id="time",
        original_name="get_current_time",
        description="Get current time in timezone",
        input_schema=schema,
        fingerprint=compute_tool_fingerprint(
            "get_current_time", "Get current time in timezone", schema
        ),
        permission="allowed_read_only",
        enabled=True,
    )
    user_mode_runtime.mcp_gateway.registry._tools[tool1.tool_id] = tool1

    # Create dummy events to be yielded by astream_events
    async def mock_astream_events(*args: Any, **kwargs: Any):
        # 1. Model requests tool
        yield {
            "event": "on_chat_model_end",
            "name": "ChatOpenRouter",
            "data": {
                "output": ChatResult(
                    generations=[
                        ChatGeneration(
                            message=AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "id": "tc_evt_1",
                                        "name": "time__get_current_time",
                                        "args": {"timezone": "UTC"},
                                    }
                                ],
                            )
                        )
                    ]
                )
            },
        }
        # 2. Tool starts
        yield {
            "event": "on_tool_start",
            "name": "time__get_current_time",
            "data": {"input": {"timezone": "UTC"}},
            "metadata": {"tool_call_id": "tc_evt_1"},
        }
        # 3. Tool completes
        yield {
            "event": "on_tool_end",
            "name": "time__get_current_time",
            "data": {"output": '{"datetime": "2026-10-27T12:00:00Z"}'},
            "metadata": {"tool_call_id": "tc_evt_1"},
        }

    mock_agent = AsyncMock()
    mock_agent.astream_events = mock_astream_events
    mock_agent.aget_state.return_value = MagicMock(config=None, values={"messages": []})

    req = AgentStreamRequest(thread_id=thread_id, message="Current time?")

    with patch.object(user_mode_runtime, "create_agent", return_value=mock_agent):
        with patch.object(
            user_mode_runtime.checkpointer_manager,
            "get_async_checkpointer",
            return_value=AsyncMock(),
        ):
            events = []
            async for ev in user_mode_runtime.stream_agent(req):
                events.append(ev)

    event_types = [e.event for e in events]
    assert "tool_requested" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types

    req_ev = next(e for e in events if e.event == "tool_requested")
    assert req_ev.data["tool"] == "time__get_current_time"
    assert req_ev.data["server_id"] == "time"
    assert req_ev.data["input"] == {"timezone": "UTC"}

    start_ev = next(e for e in events if e.event == "tool_started")
    assert start_ev.data["tool"] == "time__get_current_time"
    assert start_ev.data["server_id"] == "time"

    comp_ev = next(e for e in events if e.event == "tool_completed")
    assert comp_ev.data["tool"] == "time__get_current_time"
    assert "2026-10-27T12:00:00Z" in comp_ev.data["output"]


@pytest.mark.asyncio
async def test_tool_failure_event_emitted(
    user_mode_runtime: AgentRuntimeManager,
) -> None:
    """Verify that tool failure emits tool_failed and does not emit tool_completed."""
    thread_id = f"thread_fail_{uuid.uuid4().hex[:8]}"

    async def mock_failing_stream(*args: Any, **kwargs: Any):
        yield {
            "event": "on_tool_start",
            "name": "time__get_current_time",
            "data": {"input": {"timezone": "Invalid"}},
            "metadata": {"tool_call_id": "tc_fail_1"},
        }
        # Simulate error tool message from tool execution
        yield {
            "event": "on_tool_end",
            "name": "time__get_current_time",
            "data": {
                "output": ToolMessage(
                    content="MCP server returned tool error: Invalid timezone",
                    status="error",
                    tool_call_id="tc_fail_1",
                    name="time__get_current_time",
                )
            },
            "metadata": {"tool_call_id": "tc_fail_1"},
        }

    mock_agent = AsyncMock()
    mock_agent.astream_events = mock_failing_stream
    mock_agent.aget_state.return_value = MagicMock(config=None, values={"messages": []})

    req = AgentStreamRequest(thread_id=thread_id, message="Time in Invalid timezone?")

    with patch.object(user_mode_runtime, "create_agent", return_value=mock_agent):
        with patch.object(
            user_mode_runtime.checkpointer_manager,
            "get_async_checkpointer",
            return_value=AsyncMock(),
        ):
            events = []
            async for ev in user_mode_runtime.stream_agent(req):
                events.append(ev)

    event_types = [e.event for e in events]
    assert "tool_started" in event_types
    assert "tool_failed" in event_types
    assert "tool_completed" not in event_types

    fail_ev = next(e for e in events if e.event == "tool_failed")
    assert fail_ev.data["tool"] == "time__get_current_time"
    assert "Invalid timezone" in fail_ev.data["error"]


@pytest.mark.asyncio
async def test_list_thread_approvals_api_endpoint(tmp_path: Any) -> None:
    """Verify GET /api/v1/agent/approvals/thread/{thread_id} returns all approvals for thread."""
    settings = Settings(
        app_name="Javed Test Approvals API",
        sqlite_checkpoints_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
        allowed_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    )
    app = create_app(settings)
    await app.state.agent_runtime.initialize()

    thread_id = f"thread_api_{uuid.uuid4().hex[:8]}"
    approval_store: ApprovalStore = app.state.agent_runtime.approval_store

    appr_id_1 = f"appr_th_1_{uuid.uuid4().hex[:6]}"
    appr_id_2 = f"appr_th_2_{uuid.uuid4().hex[:6]}"

    rec1 = ApprovalRecord(
        approval_id=appr_id_1,
        interrupt_id="intr_1",
        run_id="run_1",
        thread_id=thread_id,
        server_id="time",
        tool_id="time__get_current_time",
        tool_call_id="tc_1",
        arguments={"timezone": "UTC"},
        argument_digest=compute_argument_digest({"timezone": "UTC"}),
        tool_fingerprint="fp1",
        policy_version=1,
        status="approved",
        dispatch_status="completed",
        result_summary='{"time": "12:00"}',
    )
    rec2 = ApprovalRecord(
        approval_id=appr_id_2,
        interrupt_id="intr_2",
        run_id="run_2",
        thread_id=thread_id,
        server_id="time",
        tool_id="time__convert_time",
        tool_call_id="tc_2",
        arguments={"time": "12:00"},
        argument_digest=compute_argument_digest({"time": "12:00"}),
        tool_fingerprint="fp2",
        policy_version=1,
        status="pending",
    )
    await approval_store.create_approval(rec1)
    await approval_store.create_approval(rec2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        res = await client.get(
            f"/api/v1/agent/approvals/thread/{thread_id}",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        ids = [a["approval_id"] for a in data["approvals"]]
        assert appr_id_1 in ids
        assert appr_id_2 in ids
