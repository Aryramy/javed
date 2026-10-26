"""Unit, security, and live integration tests for DynamicMCPRegistry."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.messages import ToolMessage

from javed.agent.security import (
    ALLOWED_TOOLS,
    PositiveToolAllowlistMiddleware,
)
from javed.mcp.env import get_sanitized_subprocess_env
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import create_time_server_config
from javed.schemas.mcp import (
    DiscoveredTool,
    ServerConfig,
    ServerStatus,
    build_namespaced_tool_id,
    compute_tool_fingerprint,
    parse_namespaced_tool_id,
    validate_server_id,
)

# ---------------------------------------------------------------------------
# Unit Tests: Identifiers, Namespace, Fingerprints & Environment Scrubbing
# ---------------------------------------------------------------------------


def test_server_id_validation():
    """Verify server ID format constraints and security boundaries."""
    assert validate_server_id("time") == "time"
    assert validate_server_id("time_v2") == "time_v2"
    assert validate_server_id("my-server-1") == "my-server-1"

    # Reject invalid characters, uppercase, whitespace, traversal
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_server_id("")
    with pytest.raises(ValueError, match="Invalid server_id"):
        validate_server_id("TimeServer")
    with pytest.raises(ValueError, match="Invalid server_id"):
        validate_server_id("time server")
    with pytest.raises(ValueError, match="Invalid server_id"):
        validate_server_id("../time")
    with pytest.raises(ValueError, match="exceeds maximum length"):
        validate_server_id("a" * 65)


def test_tool_namespace_and_fingerprint():
    """Verify collision-safe tool ID construction, parsing, and fingerprint determinism."""
    tool_id = build_namespaced_tool_id("time", "get_current_time")
    assert tool_id == "time__get_current_time"

    sid, raw_name = parse_namespaced_tool_id(tool_id)
    assert sid == "time"
    assert raw_name == "get_current_time"

    schema1 = {"type": "object", "properties": {"timezone": {"type": "string"}}}
    fp1 = compute_tool_fingerprint("get_current_time", "Get time in timezone", schema1)
    fp1_duplicate = compute_tool_fingerprint("get_current_time", "Get time in timezone", schema1)
    assert fp1 == fp1_duplicate, "Fingerprint must be strictly deterministic"

    # Any schema alteration must produce a different fingerprint
    schema2 = {
        "type": "object",
        "properties": {"timezone": {"type": "string"}, "format": {"type": "string"}},
    }
    fp2 = compute_tool_fingerprint("get_current_time", "Get time in timezone", schema2)
    assert fp1 != fp2, "Schema modification must alter fingerprint"

    # Description alteration must produce a different fingerprint
    fp3 = compute_tool_fingerprint("get_current_time", "Modified description", schema1)
    assert fp1 != fp3, "Description modification must alter fingerprint"


def test_subprocess_env_sanitization():
    """Verify sensitive environment variables and credentials are purged from subprocess env."""
    extra = {
        "CUSTOM_NON_SENSITIVE": "allowed_value",
        "OPENROUTER_API_KEY": "sk-or-v1-secret-token",
        "OPENAI_API_KEY": "sk-proj-secret-token",
        "MY_DATABASE_PASSWORD": "supersecretpassword",
        "AUTH_BEARER_TOKEN": "secret-auth-bearer",
    }
    cleaned = get_sanitized_subprocess_env(extra)

    assert cleaned["CUSTOM_NON_SENSITIVE"] == "allowed_value"
    assert cleaned["PYTHONUNBUFFERED"] == "1"

    # Essential system runtime vars preserved
    for var in ("SYSTEMROOT", "PATH"):
        if var in os.environ:
            assert var in cleaned

    # Sensitive keys strictly purged
    assert "OPENROUTER_API_KEY" not in cleaned
    assert "OPENAI_API_KEY" not in cleaned
    assert "MY_DATABASE_PASSWORD" not in cleaned
    assert "AUTH_BEARER_TOKEN" not in cleaned


# ---------------------------------------------------------------------------
# Unit Tests: Registry Server & Error Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unregistered_and_disabled_server_handling():
    """Verify connecting to an unknown or disabled server fails safely."""
    registry = DynamicMCPRegistry()

    with pytest.raises(ValueError, match="is not registered"):
        await registry.connect("unregistered")

    config = ServerConfig(
        server_id="disabled_srv",
        server_name="Disabled Server",
        command="python",
        enabled=False,
    )
    registry.register_server(config)

    with pytest.raises(ValueError, match="is disabled by host policy"):
        await registry.connect("disabled_srv")


@pytest.mark.asyncio
async def test_connection_failure_handling():
    """Verify pointing to a non-existent executable reports sanitized ConnectionError."""
    registry = DynamicMCPRegistry()
    config = ServerConfig(
        server_id="bad_srv",
        server_name="Bad Server",
        command="C:\\non_existent_binary_for_test_12345.exe",
        timeout_seconds=2.0,
    )
    registry.register_server(config)

    with pytest.raises(ConnectionError, match="Failed to connect to MCP server"):
        await registry.connect("bad_srv")

    status = registry.get_server_status("bad_srv")
    assert status is not None
    assert status.connection_state == "error"
    assert status.last_error is not None


# ---------------------------------------------------------------------------
# Integration Tests: Real STDIO Time Server Live Discovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_time_server_discovery_and_default_deny():
    """Live STDIO Test: Connect to official mcp-server-time, discover tools, assert default DENY."""
    registry = DynamicMCPRegistry()
    config = create_time_server_config()
    registry.register_server(config)

    # 1. Connect over STDIO
    adapter = await registry.connect("time")
    assert adapter is not None

    status = registry.get_server_status("time")
    assert status is not None
    assert status.connection_state == "connected"
    assert status.protocol_version is not None
    assert status.server_info is not None
    assert status.server_info.get("name") == "mcp-time"

    # Capability verification: Time server reports list_changed=False
    tools_cap = status.capabilities.get("tools", {}) if status.capabilities else {}
    assert tools_cap.get("list_changed") is False, (
        "Time server capability list_changed must be respected as False"
    )

    # 2. Discover tools
    discovered = await registry.discover_tools("time")
    assert len(discovered) == 2, "Expected exactly 2 tools from Time reference server"

    tool_names = [t.original_name for t in discovered]
    assert "get_current_time" in tool_names
    assert "convert_time" in tool_names

    # Check namespaced IDs
    get_time = next(t for t in discovered if t.original_name == "get_current_time")
    convert_time = next(t for t in discovered if t.original_name == "convert_time")

    assert get_time.tool_id == "time__get_current_time"
    assert convert_time.tool_id == "time__convert_time"

    # Schema preservation
    assert "timezone" in get_time.input_schema.get("properties", {})
    assert "source_timezone" in convert_time.input_schema.get("properties", {})
    assert "target_timezone" in convert_time.input_schema.get("properties", {})

    # MANDATORY Phase 2 Security Invariants:
    # 1. All newly discovered tools default to DENIED
    assert get_time.permission == "denied"
    assert convert_time.permission == "denied"

    # 2. All newly discovered tools default to disabled
    assert get_time.enabled is False
    assert convert_time.enabled is False

    # 3. Model visible tools is strictly empty in Phase 2
    assert registry.get_model_visible_mcp_tools() == []

    # 4. Executable tools is strictly empty in Phase 2
    assert registry.get_executable_mcp_tools() == []
    assert registry.is_tool_authorized_for_execution("time__get_current_time") is False
    assert registry.is_tool_authorized_for_execution("time__convert_time") is False

    # 3. Clean teardown
    await registry.disconnect("time")
    assert registry.get_server_status("time").connection_state == "disconnected"


@pytest.mark.asyncio
async def test_host_policy_approval_and_schema_change_invalidation():
    """Verify host policy approval records fingerprint and schema modification invalidates it."""
    registry = DynamicMCPRegistry()

    # Pre-register a tool record
    schema = {"type": "object", "properties": {"timezone": {"type": "string"}}}
    fp = compute_tool_fingerprint("get_current_time", "Get current time", schema)
    tool = DiscoveredTool(
        tool_id="time__get_current_time",
        server_id="time",
        original_name="get_current_time",
        description="Get current time",
        input_schema=schema,
        fingerprint=fp,
        permission="denied",
        enabled=False,
    )
    registry._tools["time__get_current_time"] = tool

    # Host approves tool
    registry.set_tool_policy("time__get_current_time", permission="allowed_read_only", enabled=True)
    assert tool.permission == "allowed_read_only"
    assert tool.enabled is True
    assert "time__get_current_time" in registry._policies
    assert registry._policies["time__get_current_time"].approved_fingerprint == fp

    # Mock re-discovery with modified schema (e.g. server updated or compromised)
    modified_schema = {
        "type": "object",
        "properties": {
            "timezone": {"type": "string"},
            "malicious_extra": {"type": "string"},
        },
    }
    raw_tool_mock = MagicMock()
    raw_tool_mock.name = "get_current_time"
    raw_tool_mock.description = "Get current time"
    raw_tool_mock.input_schema = modified_schema
    raw_tool_mock.output_schema = None

    mock_client = AsyncMock()
    mock_client.list_tools.return_value = [raw_tool_mock]
    mock_adapter = MagicMock()
    mock_adapter.client = mock_client

    registry._servers["time"] = ServerConfig(
        server_id="time",
        server_name="Time Server",
        command="python",
    )
    registry._statuses["time"] = ServerStatus(
        server_id="time",
        server_name="Time Server",
        transport_type="stdio",
        connection_state="connected",
    )
    registry._adapters["time"] = mock_adapter

    # Re-discover tools
    rediscovered = await registry.discover_tools("time")
    updated_tool = rediscovered[0]

    # SECURITY INVARIANT: Approval must be invalidated and permission reset to DENIED
    assert updated_tool.permission == "denied", "Modified tool must be reset to DENIED"
    assert updated_tool.enabled is False, "Modified tool must be reset to disabled"
    assert "time__get_current_time" not in registry._policies, (
        "Approval policy must be cleared on schema drift"
    )
    assert "Approval invalidated" in updated_tool.last_error


@pytest.mark.asyncio
async def test_duplicate_tool_name_rejection():
    """Verify that duplicate tool names returned by server are rejected as security violation."""
    registry = DynamicMCPRegistry()
    raw_tool1 = MagicMock(
        name="duplicate_tool",
        description="Tool 1",
        input_schema={},
        output_schema=None,
    )
    raw_tool1.name = "test_tool"
    raw_tool2 = MagicMock(
        name="duplicate_tool",
        description="Tool 2",
        input_schema={},
        output_schema=None,
    )
    raw_tool2.name = "test_tool"

    mock_client = AsyncMock()
    mock_client.list_tools.return_value = [raw_tool1, raw_tool2]
    mock_adapter = MagicMock()
    mock_adapter.client = mock_client

    registry._servers["mock_srv"] = ServerConfig(
        server_id="mock_srv",
        server_name="Mock Server",
        command="python",
    )
    registry._statuses["mock_srv"] = ServerStatus(
        server_id="mock_srv",
        server_name="Mock Server",
        transport_type="stdio",
        connection_state="connected",
    )
    registry._adapters["mock_srv"] = mock_adapter

    with pytest.raises(ValueError, match="Duplicate tool name 'test_tool' detected"):
        await registry.discover_tools("mock_srv")


# ---------------------------------------------------------------------------
# Security Invariant: BRICK-004 Boundary Preservation
# ---------------------------------------------------------------------------


def test_brick004_agent_boundary_preservation():
    """Verify that BRICK-004's positive tool allowlist strictly permits write_todos only.

    MCP tools, filesystem, shell, and subagent tools must be rejected by
    PositiveToolAllowlistMiddleware across both model visibility and execution gating.
    """
    middleware = PositiveToolAllowlistMiddleware()

    # Model visibility test: only write_todos passes through
    mock_tools = [
        {"name": "write_todos"},
        {"name": "time__get_current_time"},
        {"name": "get_current_time"},
        {"name": "read_file"},
        {"name": "execute"},
        {"name": "task"},
    ]
    req = ModelRequest(model=MagicMock(), messages=[], tools=mock_tools)
    captured_req = None

    def dummy_handler(request: ModelRequest):
        nonlocal captured_req
        captured_req = request
        return MagicMock()

    middleware.wrap_model_call(req, dummy_handler)
    assert captured_req is not None
    exposed_names = [t["name"] for t in captured_req.tools]
    assert exposed_names == ["write_todos"], "Only write_todos must reach the model in this phase"

    # Execution gating test: unapproved tools are blocked with Security Violation
    for blocked_name in (
        "time__get_current_time",
        "get_current_time",
        "convert_time",
        "ls",
        "bash",
        "execute",
    ):
        tool_req = ToolCallRequest(
            tool_call={"id": "call_1", "name": blocked_name, "args": {}},
            tool=None,
            state={},
            runtime=MagicMock(),
        )
        msg = middleware._block_unauthorized_call(tool_req)
        assert isinstance(msg, ToolMessage)
        assert "Security Violation" in msg.content
        assert blocked_name in msg.content

    # Authorized tool write_todos is not blocked
    allowed_req = ToolCallRequest(
        tool_call={"id": "call_2", "name": "write_todos", "args": {"todos": []}},
        tool=None,
        state={},
        runtime=MagicMock(),
    )
    assert middleware._block_unauthorized_call(allowed_req) is None
    assert ALLOWED_TOOLS == frozenset({"write_todos"})


def test_unknown_tool_rejection():
    """Verify registry rejects unknown tools and non-existent IDs."""
    registry = DynamicMCPRegistry()
    assert registry.get_tool("nonexistent__tool") is None
    with pytest.raises(KeyError, match="Tool 'nonexistent__tool' not found"):
        registry.set_tool_policy("nonexistent__tool", permission="allowed_read_only", enabled=True)
    is_valid, err = registry.validate_tool_arguments("nonexistent__tool", {})
    assert is_valid is False
    assert "not found in registry" in err
    assert registry.is_tool_authorized_for_execution("nonexistent__tool") is False


def test_model_visibility_and_executable_gating():
    """Verify strict model visibility and execution gating remains empty."""
    registry = DynamicMCPRegistry()
    assert registry.get_model_visible_mcp_tools() == []
    assert registry.get_executable_mcp_tools() == []

    # Even with tools pre-populated in registry, phase gating keeps lists empty
    tool = DiscoveredTool(
        tool_id="time__get_current_time",
        server_id="time",
        original_name="get_current_time",
        description="Get current time",
        input_schema={},
        fingerprint="dummy_fp",
        permission="allowed_read_only",
        enabled=True,
    )
    registry._tools["time__get_current_time"] = tool
    assert registry.get_model_visible_mcp_tools() == []
    assert registry.get_executable_mcp_tools() == []
    assert registry.is_tool_authorized_for_execution("time__get_current_time") is False


def test_input_schema_validation():
    """Verify host-side input schema validation enforces required and unexpected properties."""
    registry = DynamicMCPRegistry()
    schema = {
        "type": "object",
        "properties": {"timezone": {"type": "string"}},
        "required": ["timezone"],
    }
    tool = DiscoveredTool(
        tool_id="time__get_current_time",
        server_id="time",
        original_name="get_current_time",
        description="Get current time",
        input_schema=schema,
        fingerprint="fp123",
        permission="denied",
        enabled=False,
    )
    registry._tools["time__get_current_time"] = tool

    # 1. Missing required property
    valid, err = registry.validate_tool_arguments("time__get_current_time", {})
    assert valid is False
    assert "Missing required argument(s): ['timezone']" in err

    # 2. Unexpected property not in schema
    valid, err = registry.validate_tool_arguments(
        "time__get_current_time", {"timezone": "Asia/Qatar", "malicious": "injected"}
    )
    assert valid is False
    assert "Unexpected argument(s) not in declared schema: ['malicious']" in err

    # 3. Invalid JSON schema type
    valid, err = registry.validate_tool_arguments("time__get_current_time", {"timezone": 12345})
    assert valid is False
    assert "Schema validation error" in err

    # 4. Valid input
    valid, err = registry.validate_tool_arguments(
        "time__get_current_time", {"timezone": "Asia/Qatar"}
    )
    assert valid is True
    assert err is None
