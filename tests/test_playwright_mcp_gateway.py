"""Phase 7: @playwright/mcp Gateway Integration & Three-Tier Host Policy Tests.

Comprehensive tests verifying:
1. Dynamic server registration of @playwright/mcp with safe STDIO arguments.
2. Discovery of all 25 evaluated tools and default-denied classification (Layer 1 & Layer 2).
3. Authoritative 3-tier host permission model:
   - DENIED: dangerous tools (browser_run_code_unsafe, browser_evaluate, browser_file_upload)
     are permanently blocked from model visibility and execution.
   - APPROVAL_REQUIRED: mutating actions (browser_click, browser_fill_form, etc.) require HITL
     approval tickets before execution.
   - ALLOWED_READ_ONLY: safe inspection tools (browser_snapshot, browser_take_screenshot, etc.)
     can be authorized for unprompted reading.
4. Schema fingerprint integrity and tampering defense (re-discovery resets tools to DENIED).
5. Clean subprocess lifecycle management and adapter teardown with zero orphaned processes.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from javed.mcp.approval_store import ApprovalRecord
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import (
    DEFAULT_PLAYWRIGHT_MCP_ARGS,
    PLAYWRIGHT_MCP_DANGEROUS_TOOLS,
    PLAYWRIGHT_MCP_MUTATING_TOOLS,
    PLAYWRIGHT_MCP_READONLY_TOOLS,
    PLAYWRIGHT_MCP_SERVER_ID,
    PLAYWRIGHT_MCP_SERVER_NAME,
    create_playwright_mcp_config,
    find_playwright_mcp_command,
)
from javed.schemas.approval import compute_argument_digest
from javed.schemas.mcp import (
    MCPApprovalUnavailableError,
    MCPInputValidationError,
    MCPPermissionDeniedError,
    build_namespaced_tool_id,
)

# ---------------------------------------------------------------------------
# Mock Tool Definitions for the 25 Tools from BRICK-006 Phase 1 Audit
# ---------------------------------------------------------------------------


class MockMCPTool:
    """Simulates a raw MCP tool schema returned by FastMCP list_tools."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema or {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


def create_mock_playwright_tools() -> list[MockMCPTool]:
    """Return all 25 tools discovered in BRICK-006 Phase 1 audit."""
    tools: list[MockMCPTool] = []

    # 1. Dangerous Tools (3)
    tools.append(
        MockMCPTool(
            "browser_run_code_unsafe",
            "Run arbitrary JavaScript/Python code directly in the active browser page",
            {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        )
    )
    tools.append(
        MockMCPTool(
            "browser_evaluate",
            "Evaluate raw JavaScript expression in DOM",
            {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        )
    )
    tools.append(
        MockMCPTool(
            "browser_file_upload",
            "Upload local file from filesystem into file input selector",
            {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "file_path": {"type": "string"},
                },
                "required": ["selector", "file_path"],
            },
        )
    )

    # 2. Mutating Tools (9)
    mutating_specs = [
        (
            "browser_click",
            "Click an element matching selector",
            {"selector": {"type": "string"}},
        ),
        (
            "browser_fill_form",
            "Fill input field",
            {"selector": {"type": "string"}, "value": {"type": "string"}},
        ),
        (
            "browser_type",
            "Type text sequentially",
            {"text": {"type": "string"}},
        ),
        (
            "browser_press_key",
            "Press keyboard key",
            {"key": {"type": "string"}},
        ),
        (
            "browser_select_option",
            "Select dropdown option",
            {"selector": {"type": "string"}, "value": {"type": "string"}},
        ),
        (
            "browser_drop",
            "Drop draggable element on target",
            {"target": {"type": "string"}},
        ),
        (
            "browser_drag",
            "Drag element",
            {"source": {"type": "string"}, "target": {"type": "string"}},
        ),
        (
            "browser_handle_dialog",
            "Accept or dismiss dialog",
            {"accept": {"type": "boolean"}},
        ),
        ("browser_close", "Close browser page", {}),
    ]
    for name, desc, props in mutating_specs:
        tools.append(
            MockMCPTool(
                name,
                desc,
                {
                    "type": "object",
                    "properties": props,
                    "additionalProperties": False,
                },
            )
        )

    # 3. Readonly / Inspection Tools (13)
    readonly_specs = [
        ("browser_snapshot", "Capture DOM snapshot tree", {}),
        (
            "browser_take_screenshot",
            "Capture screenshot of page",
            {"full_page": {"type": "boolean"}},
        ),
        ("browser_find", "Find elements matching query", {"query": {"type": "string"}}),
        ("browser_console_messages", "Retrieve browser console logs", {}),
        ("browser_network_requests", "Retrieve recent network requests", {}),
        (
            "browser_network_request",
            "Retrieve single network request details",
            {"request_id": {"type": "string"}},
        ),
        ("browser_tabs", "List open browser tabs", {}),
        (
            "browser_wait_for",
            "Wait for selector or condition",
            {"selector": {"type": "string"}},
        ),
        (
            "browser_navigate",
            "Navigate active page to URL",
            {"url": {"type": "string"}},
        ),
        ("browser_navigate_back", "Navigate back in browser history", {}),
        (
            "browser_resize",
            "Resize viewport dimensions",
            {"width": {"type": "integer"}, "height": {"type": "integer"}},
        ),
        ("browser_emulate_media", "Emulate media features", {"media": {"type": "string"}}),
        ("browser_hover", "Hover over element", {"selector": {"type": "string"}}),
    ]
    for name, desc, props in readonly_specs:
        tools.append(
            MockMCPTool(
                name,
                desc,
                {
                    "type": "object",
                    "properties": props,
                    "additionalProperties": False,
                },
            )
        )

    return tools


def create_mock_playwright_adapter(tools: list[MockMCPTool] | None = None) -> MagicMock:
    """Create a mock LangChain MCPAdapter returning the specified tools."""
    tool_list = tools if tools is not None else create_mock_playwright_tools()

    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.protocol_version = "2026-07-28"
    mock_client.server_info = {"name": "@playwright/mcp", "version": "0.0.83"}
    mock_client.server_capabilities = {"tools": {"list_changed": False}}
    mock_client.list_tools.return_value = tool_list

    mock_adapter = MagicMock()
    mock_adapter.client = mock_client
    mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
    mock_adapter.__aexit__ = AsyncMock(return_value=None)
    return mock_adapter


def attach_mock_adapter(
    registry: DynamicMCPRegistry,
    adapter: MagicMock | None = None,
) -> MagicMock:
    """Attach a mock adapter to registry and set its state to connected."""
    mock = adapter or create_mock_playwright_adapter()
    registry._adapters["playwright"] = mock
    status = registry.get_server_status("playwright")
    if status:
        status.connection_state = "connected"
    return mock


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_playwright_mcp_config_creation() -> None:
    """Verify ServerConfig factory generates valid STDIO configuration."""
    config = create_playwright_mcp_config()
    assert config.server_id == PLAYWRIGHT_MCP_SERVER_ID
    assert config.server_name == PLAYWRIGHT_MCP_SERVER_NAME
    assert config.transport_type == "stdio"
    assert config.timeout_seconds == 45.0
    assert config.enabled is True

    # Validate command resolution and safe invocation args
    cmd, args = find_playwright_mcp_command()
    assert config.command == cmd
    assert config.args == DEFAULT_PLAYWRIGHT_MCP_ARGS
    assert "--browser" in config.args
    assert "chrome" in config.args
    assert "--isolated" in config.args
    assert "--headless" in config.args

    # Verify parent secrets are not leaked into subprocess environment
    assert "OPENROUTER_API_KEY" not in config.env
    assert "JAVED_OWNER_TOKEN" not in config.env


def test_playwright_mcp_tier_classification_constants() -> None:
    """Verify 3-tier classification covers all 25 tools without overlap."""
    assert len(PLAYWRIGHT_MCP_DANGEROUS_TOOLS) == 3
    assert len(PLAYWRIGHT_MCP_MUTATING_TOOLS) == 9
    assert len(PLAYWRIGHT_MCP_READONLY_TOOLS) == 13

    total_unique = (
        PLAYWRIGHT_MCP_DANGEROUS_TOOLS
        | PLAYWRIGHT_MCP_MUTATING_TOOLS
        | PLAYWRIGHT_MCP_READONLY_TOOLS
    )
    assert len(total_unique) == 25

    # Ensure zero overlap
    assert len(PLAYWRIGHT_MCP_DANGEROUS_TOOLS & PLAYWRIGHT_MCP_MUTATING_TOOLS) == 0
    assert len(PLAYWRIGHT_MCP_DANGEROUS_TOOLS & PLAYWRIGHT_MCP_READONLY_TOOLS) == 0
    assert len(PLAYWRIGHT_MCP_MUTATING_TOOLS & PLAYWRIGHT_MCP_READONLY_TOOLS) == 0


@pytest.mark.asyncio
async def test_playwright_mcp_registry_registration() -> None:
    """Verify @playwright/mcp can be registered in DynamicMCPRegistry."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)

    retrieved = registry.get_server_config(PLAYWRIGHT_MCP_SERVER_ID)
    assert retrieved is not None
    assert retrieved.server_id == "playwright"

    status = registry.get_server_status(PLAYWRIGHT_MCP_SERVER_ID)
    assert status is not None
    assert status.server_id == "playwright"
    assert status.connection_state == "disconnected"


@pytest.mark.asyncio
async def test_playwright_mcp_discovery_default_denied_all_25_tools() -> None:
    """CRITICAL SECURITY GATE: Verify all 25 discovered tools initialize as DENIED.

    Enforces Layer 1 (model visibility) and Layer 2 (execution eligibility) restrictions.
    """
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)

    # Attach mock adapter before discovery
    attach_mock_adapter(registry)

    # Discover tools
    discovered = await registry.discover_tools("playwright")
    assert len(discovered) == 25

    gateway = SecureMCPGateway(registry)

    # 1. Verify every single tool has permission='denied' and enabled=False
    for tool in discovered:
        assert tool.server_id == "playwright"
        assert tool.tool_id.startswith("playwright__")
        assert tool.permission == "denied"
        assert tool.enabled is False
        assert tool.fingerprint is not None
        assert len(tool.fingerprint) == 64

    # 2. Layer 1 Check: Zero tools visible to model by default
    visible_strict = gateway.get_model_visible_tools(include_approval_required=False)
    assert not any(t.startswith("playwright__") for t in visible_strict)

    visible_with_hitl = gateway.get_model_visible_tools(include_approval_required=True)
    assert not any(t.startswith("playwright__") for t in visible_with_hitl)

    # 3. Layer 2 Check: Zero tools executable
    executable = gateway.get_executable_tools()
    assert not any(t.startswith("playwright__") for t in executable)


@pytest.mark.asyncio
async def test_playwright_mcp_dangerous_tools_blocked() -> None:
    """Verify dangerous tools (browser_run_code_unsafe, browser_evaluate) fail closed."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)
    attach_mock_adapter(registry)

    await registry.discover_tools("playwright")
    gateway = SecureMCPGateway(registry)

    for dangerous_name in PLAYWRIGHT_MCP_DANGEROUS_TOOLS:
        tool_id = build_namespaced_tool_id("playwright", dangerous_name)

        # 1. Model visibility must be False
        assert gateway.is_model_visible(tool_id) is False
        assert gateway.is_model_visible(tool_id, include_approval_required=True) is False

        # 2. Execution eligibility verification must reject
        authorized, reason = gateway.verify_execution_eligibility(tool_id)
        assert authorized is False
        assert f"Tool '{tool_id}' is DENIED by host policy." in (reason or "")

        # 3. Direct execution attempt raises MCPPermissionDeniedError
        with pytest.raises(MCPPermissionDeniedError) as exc_info:
            await gateway.execute_tool(tool_id, {})
        assert "DENIED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_playwright_mcp_mutating_tools_require_hitl_approval() -> None:
    """Verify mutating actions (e.g. browser_click) require valid approved ticket."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)
    attach_mock_adapter(registry)

    await registry.discover_tools("playwright")
    gateway = SecureMCPGateway(registry)

    click_tool_id = "playwright__browser_click"

    # Step A: Initially DENIED
    assert gateway.is_model_visible(click_tool_id) is False

    # Step B: Promote to APPROVAL_REQUIRED
    registry.set_tool_permission(click_tool_id, "APPROVAL_REQUIRED", enabled=True)

    # Now visible when include_approval_required=True, but hidden from unprompted execution
    assert gateway.is_model_visible(click_tool_id, include_approval_required=False) is False
    assert gateway.is_model_visible(click_tool_id, include_approval_required=True) is True

    # Step C: Execution without approval ticket fails
    authorized, reason = gateway.verify_execution_eligibility(
        click_tool_id, arguments={"selector": "#submit-btn"}
    )
    assert authorized is False
    assert "approval" in (reason or "").lower()

    with pytest.raises(MCPApprovalUnavailableError):
        await gateway.execute_tool(click_tool_id, {"selector": "#submit-btn"})

    # Step D: Execution with approved ticket succeeds verification
    tool_record = registry.get_tool(click_tool_id)
    assert tool_record is not None

    now = datetime.now(UTC)
    args = {"selector": "#submit-btn"}
    approved_ticket = ApprovalRecord(
        approval_id="appr-click-123",
        interrupt_id="int-123",
        run_id="run-test",
        thread_id="thread-test",
        server_id="playwright",
        tool_id=click_tool_id,
        tool_call_id="call-click-123",
        arguments=args,
        argument_digest=compute_argument_digest(args),
        tool_fingerprint=tool_record.fingerprint,
        policy_version=registry.policy_version,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        status="approved",
        decision_at=now,
        decision_by="human_operator",
        dispatch_status="not_dispatched",
    )

    authorized, reason = gateway.verify_execution_eligibility(
        click_tool_id,
        arguments={"selector": "#submit-btn"},
        approval_record=approved_ticket,
    )
    assert authorized is True
    assert reason is None


@pytest.mark.asyncio
async def test_playwright_mcp_readonly_tool_allowed_read_only() -> None:
    """Verify safe read-only tool (browser_snapshot) can be authorized without HITL."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)
    attach_mock_adapter(registry)

    await registry.discover_tools("playwright")
    gateway = SecureMCPGateway(registry)

    snapshot_tool_id = "playwright__browser_snapshot"

    # Promote to ALLOWED_READ_ONLY
    registry.set_tool_permission(snapshot_tool_id, "ALLOWED_READ_ONLY", enabled=True)

    # Immediately visible without requiring HITL flag
    assert gateway.is_model_visible(snapshot_tool_id) is True
    assert snapshot_tool_id in gateway.get_model_visible_tools()

    # Verification passes without needing approval ticket
    authorized, reason = gateway.verify_execution_eligibility(snapshot_tool_id, arguments={})
    assert authorized is True
    assert reason is None


@pytest.mark.asyncio
async def test_playwright_mcp_fingerprint_drift_invalidates_policy() -> None:
    """Verify schema drift upon rediscovery resets an authorized tool to DENIED."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)

    # Initial discovery
    initial_tools = create_mock_playwright_tools()
    mock_adapter = create_mock_playwright_adapter(initial_tools)
    attach_mock_adapter(registry, mock_adapter)

    await registry.discover_tools("playwright")
    gateway = SecureMCPGateway(registry)

    tool_id = "playwright__browser_snapshot"
    registry.set_tool_permission(tool_id, "ALLOWED_READ_ONLY", enabled=True)
    assert gateway.is_model_visible(tool_id) is True

    # Simulate upstream schema poisoning / modification
    poisoned_tools = create_mock_playwright_tools()
    for t in poisoned_tools:
        if t.name == "browser_snapshot":
            t.description = "Poisoned snapshot description with injected prompt instructions"

    mock_adapter.client.list_tools.return_value = poisoned_tools

    # Re-discover tools
    rediscovered = await registry.discover_tools("playwright", refresh=True)
    assert len(rediscovered) == 25

    # Verification: tool approval is invalidated and reset to DENIED
    drifted_tool = registry.get_tool(tool_id)
    assert drifted_tool is not None
    assert drifted_tool.permission == "denied"
    assert drifted_tool.enabled is False
    assert gateway.is_model_visible(tool_id) is False


@pytest.mark.asyncio
async def test_playwright_mcp_input_argument_validation() -> None:
    """Verify JSON Schema validation rejects malformed tool arguments."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)
    attach_mock_adapter(registry)

    await registry.discover_tools("playwright")
    gateway = SecureMCPGateway(registry)

    tool_id = "playwright__browser_click"
    registry.set_tool_permission(tool_id, "ALLOWED_READ_ONLY", enabled=True)

    tool = registry.get_tool(tool_id)
    assert tool is not None

    # 1. Valid arguments pass
    gateway.validate_arguments(tool, {"selector": "button#submit"})

    # 2. Unexpected argument rejected
    with pytest.raises(MCPInputValidationError) as exc_info:
        gateway.validate_arguments(
            tool,
            {"selector": "button#submit", "extra_injected_field": "dangerous"},
        )
    assert "Unexpected argument" in str(exc_info.value)


@pytest.mark.asyncio
async def test_playwright_mcp_clean_disconnect() -> None:
    """Verify registry disconnect closes adapter and resets connection status."""
    registry = DynamicMCPRegistry()
    config = create_playwright_mcp_config()
    registry.register_server(config)

    mock_adapter = create_mock_playwright_adapter()
    attach_mock_adapter(registry, mock_adapter)

    status = registry.get_server_status("playwright")
    assert status is not None
    assert status.connection_state == "connected"

    await registry.disconnect("playwright")

    mock_adapter.__aexit__.assert_awaited_once()
    assert "playwright" not in registry._adapters
    assert status.connection_state == "disconnected"
