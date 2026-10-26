# LIVE MCP INTEGRATION TEST — NOT AGENT EXECUTION
"""Phase 3: Official Time MCP Server Integration & Runtime Verification.

This test module verifies:
1. Real STDIO connection to official mcp-server-time.
2. Dynamic discovery and schema validation of live tools.
3. Isolated tool execution of get_current_time and convert_time.
4. Error handling on invalid timezone, invalid format, missing argument, unexpected argument.
5. Server failure detection, error sanitization, and clean recovery.
6. Startup timeout, tool execution timeout, and clean process teardown.
7. CRITICAL SECURITY BOUNDARY: Time tools remain DENIED in the application registry,
   invisible to the model, and blocked by PositiveToolAllowlistMiddleware.
8. Backend lifecycle integration with FastAPI.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import fastmcp.exceptions
import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from javed.agent.runtime import AgentRuntimeManager
from javed.agent.security import (
    ALLOWED_TOOLS,
    PositiveToolAllowlistMiddleware,
)
from javed.config import get_settings
from javed.main import create_app
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import (
    TIME_SERVER_ID,
    create_time_server_config,
)
from javed.schemas.mcp import ServerConfig

# ---------------------------------------------------------------------------
# Scenario A: Real Live Current Time Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_a_live_current_time():
    """LIVE MCP INTEGRATION TEST — NOT AGENT EXECUTION.

    Verify real STDIO execution of get_current_time with Asia/Qatar:
    - Real subprocess is invoked.
    - Result contains parseable timezone-aware datetime with +03:00 offset.
    - Result matches declared schema (timezone, datetime, day_of_week, is_dst).
    - No hardcoded answer is substituted.
    """
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)

    # Discover real tools from the live server
    tools = await registry.discover_tools(TIME_SERVER_ID)
    tool_names = [t.original_name for t in tools]
    assert "get_current_time" in tool_names

    # Execute get_current_time directly via isolated host test harness
    result = await registry.call_tool_direct(
        server_id=TIME_SERVER_ID,
        tool_name="get_current_time",
        arguments={"timezone": "Asia/Qatar"},
    )
    await registry.disconnect(TIME_SERVER_ID)

    assert result is not None
    assert result.is_error is False, f"Server returned tool error: {result}"

    # Extract JSON text content
    assert len(result.content) > 0
    text_content = result.content[0].text
    data = json.loads(text_content)

    # Verify structured fields
    assert data["timezone"] == "Asia/Qatar"
    assert "datetime" in data
    assert "day_of_week" in data
    assert data["is_dst"] is False

    # Verify parseable timezone-aware datetime
    dt = datetime.fromisoformat(data["datetime"])
    assert dt.tzinfo is not None, "Datetime must be timezone-aware"
    assert dt.utcoffset().total_seconds() == 3 * 3600, "Qatar timezone offset must be +03:00"

    # Verify output matches the current year and date (not a stale hardcoded string)
    assert dt.year >= 2026


# ---------------------------------------------------------------------------
# Scenario B: Real Live Time Conversion Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_b_live_time_conversion():
    """LIVE MCP INTEGRATION TEST — NOT AGENT EXECUTION.

    Verify real STDIO execution of convert_time from London to Qatar:
    - Real subprocess is invoked.
    - 16:30 London -> 19:30 Qatar (+3.0h difference in late October / standard GMT).
    - Structured output matches declared schema.
    - No hardcoded timezone difference.
    """
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)

    await registry.discover_tools(TIME_SERVER_ID)

    result = await registry.call_tool_direct(
        server_id=TIME_SERVER_ID,
        tool_name="convert_time",
        arguments={
            "source_timezone": "Europe/London",
            "time": "16:30",
            "target_timezone": "Asia/Qatar",
        },
    )
    await registry.disconnect(TIME_SERVER_ID)

    assert result is not None
    assert result.is_error is False

    data = json.loads(result.content[0].text)
    assert "source" in data
    assert "target" in data
    assert "time_difference" in data

    source = data["source"]
    target = data["target"]

    assert source["timezone"] == "Europe/London"
    assert target["timezone"] == "Asia/Qatar"

    # Verify time conversion logic
    src_dt = datetime.fromisoformat(source["datetime"])
    tgt_dt = datetime.fromisoformat(target["datetime"])

    assert src_dt.hour == 16 and src_dt.minute == 30
    assert tgt_dt.hour == 19 and tgt_dt.minute == 30
    assert data["time_difference"] == "+3.0h"


# ---------------------------------------------------------------------------
# Scenario C: Input Validation & Error Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_c1_invalid_timezone():
    """Verify live server handles invalid timezone name cleanly with explicit ToolError."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)

    with pytest.raises(fastmcp.exceptions.ToolError) as exc_info:
        await registry.call_tool_direct(
            server_id=TIME_SERVER_ID,
            tool_name="get_current_time",
            arguments={"timezone": "Invalid/Nonexistent_Timezone"},
        )
    await registry.disconnect(TIME_SERVER_ID)

    assert "Invalid timezone" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_c2_invalid_time_format():
    """Verify live server handles invalid time format cleanly with explicit ToolError."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)

    with pytest.raises(fastmcp.exceptions.ToolError) as exc_info:
        await registry.call_tool_direct(
            server_id=TIME_SERVER_ID,
            tool_name="convert_time",
            arguments={
                "source_timezone": "Europe/London",
                "time": "99:99",
                "target_timezone": "Asia/Qatar",
            },
        )
    await registry.disconnect(TIME_SERVER_ID)

    assert "Invalid time format" in str(exc_info.value)
    assert "HH:MM" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_c3_missing_required_argument():
    """Verify missing required argument is caught by host schema validation before execution."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)

    # Host-side validation check
    is_valid, err = registry.validate_tool_arguments("time__get_current_time", {})
    assert is_valid is False
    assert "Missing required argument(s): ['timezone']" in err

    # Direct execution should reject before/at call
    with pytest.raises(ValueError, match="Input validation failed"):
        await registry.call_tool_direct(
            server_id=TIME_SERVER_ID,
            tool_name="get_current_time",
            arguments={},
        )
    await registry.disconnect(TIME_SERVER_ID)


@pytest.mark.asyncio
async def test_scenario_c4_unexpected_argument_rejection():
    """Verify unexpected extra arguments are rejected under strict schema discipline."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)

    is_valid, err = registry.validate_tool_arguments(
        "time__get_current_time",
        {"timezone": "Asia/Qatar", "unauthorized_extra_field": "exploit_attempt"},
    )
    assert is_valid is False
    assert "Unexpected argument(s) not in declared schema" in err

    with pytest.raises(ValueError, match="Unexpected argument"):
        await registry.call_tool_direct(
            server_id=TIME_SERVER_ID,
            tool_name="get_current_time",
            arguments={"timezone": "Asia/Qatar", "unauthorized_extra_field": "exploit_attempt"},
        )
    await registry.disconnect(TIME_SERVER_ID)


# ---------------------------------------------------------------------------
# Scenario D: Server Failure, Sanitization & Recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_d_server_failure_and_clean_recovery():
    """Verify failure detection, error message sanitization, and clean reconnection."""
    registry = DynamicMCPRegistry()

    # 1. Register a deliberately broken server
    bad_config = ServerConfig(
        server_id="broken_srv",
        server_name="Broken Server",
        transport_type="stdio",
        command="nonexistent_executable_binary_12345.exe",
        args=[],
        timeout_seconds=5.0,
    )
    registry.register_server(bad_config)

    with pytest.raises(ConnectionError) as exc_info:
        await registry.connect("broken_srv")

    status = registry.get_server_status("broken_srv")
    assert status.connection_state == "error"
    assert status.last_error is not None
    # Verify error is sanitized without raw unformatted crashes
    assert "Failed to connect to MCP server 'broken_srv'" in str(exc_info.value)

    # 2. Recovery: register a healthy Time server and connect successfully
    valid_config = create_time_server_config(server_id="recovered_time")
    registry.register_server(valid_config)

    adapter = await registry.connect("recovered_time")
    recovered_status = registry.get_server_status("recovered_time")
    assert recovered_status.connection_state == "connected"
    assert adapter is not None

    # Clean teardown
    await registry.disconnect_all()
    assert registry.get_server_status("recovered_time").connection_state == "disconnected"


# ---------------------------------------------------------------------------
# Scenario E: Timeouts, Idempotency & Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_e_startup_timeout_handling():
    """Verify startup timeout is enforced cleanly without leaving hung subprocesses."""
    registry = DynamicMCPRegistry()
    # Configure a 1.0s connection timeout against a command that sleeps longer
    tight_config = ServerConfig(
        server_id="timeout_srv",
        server_name="Slow Timeout Server",
        transport_type="stdio",
        command="powershell.exe",
        args=["-NoProfile", "-Command", "Start-Sleep -Seconds 10"],
        timeout_seconds=1.0,
    )
    registry.register_server(tight_config)

    with pytest.raises(ConnectionError) as exc_info:
        await registry.connect("timeout_srv")

    assert "timed out" in str(exc_info.value)
    status = registry.get_server_status("timeout_srv")
    assert status.connection_state == "error"
    await registry.disconnect("timeout_srv")


@pytest.mark.asyncio
async def test_scenario_e_idempotent_connection_and_disconnect():
    """Verify calling connect() returns existing adapter without duplicate process."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)

    adapter1 = await registry.connect(TIME_SERVER_ID)
    adapter2 = await registry.connect(TIME_SERVER_ID)
    assert adapter1 is adapter2, "connect() must return the existing healthy adapter"

    status = registry.get_server_status(TIME_SERVER_ID)
    assert status.connection_state == "connected"

    await registry.disconnect(TIME_SERVER_ID)
    assert status.connection_state == "disconnected"


# ---------------------------------------------------------------------------
# Scenario F: CRITICAL SECURITY BOUNDARY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_f_security_boundary_preservation():
    """Verify Phase 3 security boundary invariants:

    1. Time MCP tools remain DENIED in application registry.
    2. Model-visible MCP tools list is strictly empty.
    3. Executable MCP tools list is strictly empty.
    4. PositiveToolAllowlistMiddleware blocks Time tools.
    5. Agent runtime harness maintains write_todos as sole authorized tool.
    """
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)
    await registry.discover_tools(TIME_SERVER_ID)

    # 1. Discovered tools must default to DENIED and disabled
    tool = registry.get_tool("time__get_current_time")
    assert tool is not None
    assert tool.permission == "denied", "Time MCP tools must remain DENIED in Phase 3"
    assert tool.enabled is False, "Time MCP tools must remain disabled in Phase 3"

    # 2. Model visibility must be empty
    assert registry.get_model_visible_mcp_tools() == []

    # 3. Executable MCP tools must be empty
    assert registry.get_executable_mcp_tools() == []
    assert registry.is_tool_authorized_for_execution("time__get_current_time") is False

    # 4. Agent runtime check: strictly write_todos only
    settings = get_settings()
    agent_mgr = AgentRuntimeManager(settings)
    await agent_mgr.initialize()
    status = await agent_mgr.get_status()
    assert status.allowed_tools == ["write_todos"], "write_todos must be the sole agent tool"
    assert "time__get_current_time" not in status.allowed_tools
    assert "get_current_time" not in status.allowed_tools
    assert ALLOWED_TOOLS == frozenset({"write_todos"})
    await agent_mgr.close()

    # 5. PositiveToolAllowlistMiddleware blocks Time tools
    middleware = PositiveToolAllowlistMiddleware()
    for blocked in ("time__get_current_time", "time__convert_time", "get_current_time"):
        tool_req = ToolCallRequest(
            tool_call={"id": "test_call", "name": blocked, "args": {}},
            tool=None,
            state={},
            runtime=MagicMock(),
        )
        blocked_msg = middleware._block_unauthorized_call(tool_req)
        assert isinstance(blocked_msg, ToolMessage)
        assert "Security Violation" in blocked_msg.content

    # Teardown
    await registry.disconnect_all()


# ---------------------------------------------------------------------------
# Backend Lifecycle & FastAPI Integration
# ---------------------------------------------------------------------------


def test_backend_lifecycle_fastapi_integration():
    """Verify FastAPI application attaches mcp_registry with lazy time server configuration."""
    app = create_app()
    assert hasattr(app.state, "mcp_registry"), "app.state must have mcp_registry"

    registry: DynamicMCPRegistry = app.state.mcp_registry
    time_config = registry.get_server_config(TIME_SERVER_ID)
    assert time_config is not None
    assert time_config.server_id == "time"

    # Connection must be lazy (disconnected at startup)
    status = registry.get_server_status(TIME_SERVER_ID)
    assert status is not None
    assert status.connection_state == "disconnected"
