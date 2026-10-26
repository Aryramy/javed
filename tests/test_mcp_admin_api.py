"""Comprehensive unit, integration, and security tests for MCP Administration APIs.

Covers:
- MCP server status and telemetry.
- Dynamic tool catalog, schema preservation, and deterministic fingerprinting.
- Strict rejection of unknown servers and unknown tools.
- Immutable protection of internal tools (write_todos).
- Default DENIED canonical permission state.
- Local owner authorization: token, Origin, Sec-Fetch-Site, Origin: null rejection.
- Optimistic concurrency rejection on stale policy version.
- Metadata integrity rejection on fingerprint mismatch.
- Atomic mutation success and durable policy persistence in SQLite.
- Immediate SecureMCPGateway enforcement and execution revocation.
- Durable policy restart safety and schema drift detection.
- Revocation invalidation of outstanding pending approvals.
- Execution ledger state machine review and duplicate dispatch rejection.
- Bounded audit ledger and approvals summary queries.
- Absence of generic arbitrary tool execution endpoints.
- E2E test-mode isolation and developer diagnostics visibility.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.main import create_app
from javed.mcp.approval_store import ApprovalStore
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import create_time_server_config
from javed.schemas.approval import ApprovalRecord
from javed.schemas.mcp import (
    DiscoveredTool,
    compute_tool_fingerprint,
)


@pytest.fixture
async def admin_fixture(tmp_path):
    """Set up an isolated application runtime with persistent SQLite databases."""
    checkpoint_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")
    owner_token = "test-owner-secret-token-12345"

    settings = Settings(
        env="test",
        agent_checkpoint_db_path=checkpoint_db,
        agent_approvals_db_path=approvals_db,
        owner_token=owner_token,
        allowed_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    )

    app = create_app(settings)

    # Initialize store and runtime
    approval_store = ApprovalStore(db_path=approvals_db)
    await approval_store.initialize()

    registry = DynamicMCPRegistry(approval_store=approval_store)
    registry.register_server(create_time_server_config())

    # Manually populate two mock discovered tools for deterministic testing
    fp1 = compute_tool_fingerprint(
        tool_name="get_current_time",
        description="Get the current time in a specified timezone.",
        input_schema={
            "type": "object",
            "properties": {"timezone": {"type": "string"}},
            "required": ["timezone"],
        },
    )
    tool1 = DiscoveredTool(
        tool_id="time__get_current_time",
        server_id="time",
        original_name="get_current_time",
        description="Get the current time in a specified timezone.",
        input_schema={
            "type": "object",
            "properties": {"timezone": {"type": "string"}},
            "required": ["timezone"],
        },
        fingerprint=fp1,
        permission="denied",
        enabled=False,
    )

    fp2 = compute_tool_fingerprint(
        tool_name="convert_time",
        description="Convert a time between two timezones.",
        input_schema={
            "type": "object",
            "properties": {
                "source_timezone": {"type": "string"},
                "target_timezone": {"type": "string"},
                "time": {"type": "string"},
            },
            "required": ["source_timezone", "target_timezone", "time"],
        },
    )
    tool2 = DiscoveredTool(
        tool_id="time__convert_time",
        server_id="time",
        original_name="convert_time",
        description="Convert a time between two timezones.",
        input_schema={
            "type": "object",
            "properties": {
                "source_timezone": {"type": "string"},
                "target_timezone": {"type": "string"},
                "time": {"type": "string"},
            },
            "required": ["source_timezone", "target_timezone", "time"],
        },
        fingerprint=fp2,
        permission="denied",
        enabled=False,
    )

    registry._tools[tool1.tool_id] = tool1
    registry._tools[tool2.tool_id] = tool2

    gateway = SecureMCPGateway(registry=registry, approval_store=approval_store)
    runtime = AgentRuntimeManager(settings=settings, mcp_gateway=gateway)
    runtime.approval_store = approval_store

    app.state.settings = settings
    app.state.mcp_registry = registry
    app.state.mcp_gateway = gateway
    app.state.agent_runtime = runtime
    app.state.approval_store = approval_store

    auth_headers = {
        "X-Javed-Owner-Token": owner_token,
        "Origin": "http://localhost:5173",
    }

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8000")

    yield {
        "app": app,
        "client": client,
        "registry": registry,
        "gateway": gateway,
        "approval_store": approval_store,
        "settings": settings,
        "owner_token": owner_token,
        "auth_headers": auth_headers,
        "tool1": tool1,
        "tool2": tool2,
        "approvals_db": approvals_db,
    }

    await client.aclose()
    await approval_store.close()


# ---------------------------------------------------------------------------
# Server Status & Discovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_status_and_filtering(admin_fixture):
    """Server status accurately reflects registered connection state and rejects unknown servers."""
    client = admin_fixture["client"]

    # 1. List servers
    resp = await client.get("/api/v1/mcp/servers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    server = data["servers"][0]
    assert server["server_id"] == "time"
    assert server["server_name"] in ("Official Time MCP Server", "Time Reference Server")
    assert server["transport_type"] == "stdio"

    # 2. Get specific valid server
    resp2 = await client.get("/api/v1/mcp/servers/time")
    assert resp2.status_code == 200
    assert resp2.json()["server_id"] == "time"

    # 3. Get unknown server -> 404
    resp3 = await client.get("/api/v1/mcp/servers/unapproved_server")
    assert resp3.status_code == 404
    assert "not registered" in resp3.json()["detail"]


@pytest.mark.asyncio
async def test_tool_catalog_preserves_schemas_and_default_denied(admin_fixture):
    """Dynamic tool catalog preserves schema, deterministic fingerprints, and defaults to DENIED."""
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]

    resp = await client.get("/api/v1/mcp/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["policy_version"] == 0

    tool_entry = next(t for t in data["tools"] if t["tool_id"] == "time__get_current_time")
    assert tool_entry["permission"] == "denied"
    assert tool_entry["enabled"] is False
    assert tool_entry["fingerprint"] == tool1.fingerprint
    assert "timezone" in tool_entry["input_schema"]["properties"]

    # Detail endpoint
    detail_resp = await client.get("/api/v1/mcp/tools/time__get_current_time")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["tool"]["tool_id"] == "time__get_current_time"
    assert detail_data["policy"] is None

    # Unknown tool detail -> 404
    err_resp = await client.get("/api/v1/mcp/tools/nonexistent__tool")
    assert err_resp.status_code == 404


# ---------------------------------------------------------------------------
# Local Owner Authorization & Anti-CSRF Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_mutation_owner_auth_rejection(admin_fixture):
    """Unauthenticated or invalid token requests are strictly rejected (401)."""
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]

    body = {
        "permission": "approval_required",
        "expected_policy_version": 0,
        "expected_fingerprint": tool1.fingerprint,
    }

    # Missing auth token
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 401
    assert "Local owner authorization token required" in resp.json()["detail"]

    # Invalid auth token
    resp2 = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers={
            "X-Javed-Owner-Token": "bad-token",
            "Origin": "http://localhost:5173",
        },
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_permission_mutation_origin_and_csrf_rejection(admin_fixture):
    """Mutations with Origin: null, cross-site, or untrusted origins are strictly rejected (403)."""
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]
    token = admin_fixture["auth_headers"]["X-Javed-Owner-Token"]

    body = {
        "permission": "approval_required",
        "expected_policy_version": 0,
        "expected_fingerprint": tool1.fingerprint,
    }

    # 1. Origin: null
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers={"X-Javed-Owner-Token": token, "Origin": "null"},
    )
    assert resp.status_code == 403
    assert "Origin 'null' is strictly rejected" in resp.json()["detail"]

    # 2. Untrusted Origin
    resp2 = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers={"X-Javed-Owner-Token": token, "Origin": "http://evil-attacker.com"},
    )
    assert resp2.status_code == 403
    assert "Origin 'http://evil-attacker.com' is not authorized" in resp2.json()["detail"]

    # 3. Sec-Fetch-Site: cross-site
    resp3 = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers={
            "X-Javed-Owner-Token": token,
            "Origin": "http://localhost:5173",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert resp3.status_code == 403
    assert "Cross-site requests are rejected" in resp3.json()["detail"]


@pytest.mark.asyncio
async def test_optimistic_concurrency_and_fingerprint_checks(admin_fixture):
    """Stale policy versions (409) and fingerprint mismatches (400) are rejected."""
    client = admin_fixture["client"]
    headers = admin_fixture["auth_headers"]
    tool1 = admin_fixture["tool1"]

    # 1. Stale policy version -> 409 Conflict
    stale_body = {
        "permission": "approval_required",
        "expected_policy_version": 999,  # current is 0
        "expected_fingerprint": tool1.fingerprint,
    }
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=stale_body,
        headers=headers,
    )
    assert resp.status_code == 409
    assert "Policy version conflict" in resp.json()["detail"]

    # 2. Tampered fingerprint -> 400 Bad Request
    tampered_body = {
        "permission": "approval_required",
        "expected_policy_version": 0,
        "expected_fingerprint": "a" * 64,
    }
    resp2 = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=tampered_body,
        headers=headers,
    )
    assert resp2.status_code == 400
    assert "Tool fingerprint mismatch" in resp2.json()["detail"]

    # 3. Attempting to mutate internal write_todos -> 400 Bad Request
    resp3 = await client.post(
        "/api/v1/mcp/tools/write_todos/permission",
        json={
            "permission": "allowed_read_only",
            "expected_policy_version": 0,
            "expected_fingerprint": "a" * 64,
        },
        headers=headers,
    )
    assert resp3.status_code == 400
    assert "immutable" in resp3.json()["detail"]


# ---------------------------------------------------------------------------
# Mutation, Durability & Immediate Gateway Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_mutation_persists_and_enforces_immediately(admin_fixture):
    """Valid owner mutation succeeds, persists durably, and immediately governs the gateway."""
    client = admin_fixture["client"]
    headers = admin_fixture["auth_headers"]
    registry = admin_fixture["registry"]
    gateway = admin_fixture["gateway"]
    store = admin_fixture["approval_store"]
    tool1 = admin_fixture["tool1"]
    assert registry.policy_version == 0

    # Step 1: Mutate time__get_current_time to ALLOWED_READ_ONLY
    body = {
        "permission": "allowed_read_only",
        "enabled": True,
        "expected_policy_version": 0,
        "expected_fingerprint": tool1.fingerprint,
    }
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=body,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool"]["permission"] == "allowed_read_only"
    assert data["tool"]["enabled"] is True
    assert data["policy_version"] == 1

    # Immediate gateway check: Tool is now eligible
    eligible, reason = gateway.verify_execution_eligibility(
        tool_id=tool1.tool_id,
        arguments={"timezone": "UTC"},
    )
    assert eligible is True
    assert reason is None

    # Step 2: Verify durable persistence in SQLite
    persisted = await store.get_host_tool_policy(tool1.tool_id)
    assert persisted is not None
    assert persisted["permission"] == "allowed_read_only"
    assert persisted["enabled"] is True
    assert persisted["approved_fingerprint"] == tool1.fingerprint
    assert persisted["policy_version"] == 1

    # Step 3: Revoke permission back to DENIED
    revoke_body = {
        "permission": "denied",
        "enabled": False,
        "expected_policy_version": 1,
        "expected_fingerprint": tool1.fingerprint,
    }
    resp_rev = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json=revoke_body,
        headers=headers,
    )
    assert resp_rev.status_code == 200
    rev_data = resp_rev.json()
    assert rev_data["tool"]["permission"] == "denied"
    assert rev_data["tool"]["enabled"] is False
    assert rev_data["policy_version"] == 2

    # Immediate gateway check: Tool is now DENIED
    eligible2, reason2 = gateway.verify_execution_eligibility(
        tool_id=tool1.tool_id,
        arguments={"timezone": "UTC"},
    )
    assert eligible2 is False
    assert "DENIED" in reason2


@pytest.mark.asyncio
async def test_restart_safety_and_schema_drift_invalidation(admin_fixture):
    """Backend restart restores persisted permissions, but downgrades to DENIED on schema drift."""
    headers = admin_fixture["auth_headers"]
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]
    approvals_db = admin_fixture["approvals_db"]

    # 1. Set tool to APPROVAL_REQUIRED
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "approval_required",
            "enabled": True,
            "expected_policy_version": 0,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["tool"]["permission"] == "approval_required"

    # 2. Simulate Backend Process Restart with fresh DynamicMCPRegistry
    fresh_store = ApprovalStore(db_path=approvals_db)
    fresh_registry = DynamicMCPRegistry(approval_store=fresh_store)
    fresh_registry.register_server(create_time_server_config())

    # Load persisted policies
    await fresh_registry.load_persisted_policies()
    assert fresh_registry.policy_version == 1

    # Simulate rediscovery where fingerprint matches
    fresh_registry._tools[tool1.tool_id] = tool1
    await fresh_registry.load_persisted_policies()
    restored_tool = fresh_registry.get_tool(tool1.tool_id)
    assert restored_tool.permission == "approval_required"
    assert restored_tool.enabled is True

    # 3. Simulate rediscovery with schema drift (e.g. server modified tool schema)
    drifted_fp = compute_tool_fingerprint(
        tool_name="get_current_time",
        description="Modified description triggering drift",
        input_schema={"type": "object", "properties": {"tz": {"type": "string"}}},
    )
    drifted_tool = DiscoveredTool(
        tool_id=tool1.tool_id,
        server_id="time",
        original_name="get_current_time",
        description="Modified description triggering drift",
        input_schema={"type": "object", "properties": {"tz": {"type": "string"}}},
        fingerprint=drifted_fp,
        permission="denied",
        enabled=False,
    )

    fresh_registry._tools[tool1.tool_id] = drifted_tool
    await fresh_registry.load_persisted_policies()
    assert fresh_registry.get_tool(tool1.tool_id).permission == "denied"
    assert fresh_registry.get_tool(tool1.tool_id).enabled is False
    assert fresh_registry.get_tool_policy(tool1.tool_id) is None


@pytest.mark.asyncio
async def test_revocation_invalidates_outstanding_pending_approvals(admin_fixture):
    """Revoking a tool permission cancels outstanding pending approvals in ApprovalStore."""
    client = admin_fixture["client"]
    headers = admin_fixture["auth_headers"]
    store = admin_fixture["approval_store"]
    tool1 = admin_fixture["tool1"]

    # 1. Authorize tool to APPROVAL_REQUIRED
    await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "approval_required",
            "enabled": True,
            "expected_policy_version": 0,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers=headers,
    )

    # 2. Create a pending approval record
    approval = ApprovalRecord(
        approval_id=f"app_{uuid.uuid4().hex[:12]}",
        interrupt_id="int_1",
        run_id="run_1",
        thread_id="th_1",
        server_id="time",
        tool_id=tool1.tool_id,
        tool_call_id="call_1",
        arguments={"timezone": "UTC"},
        argument_digest="digest_123",
        tool_fingerprint=tool1.fingerprint,
        policy_version=1,
        created_at=datetime.now(UTC),
        status="pending",
        dispatch_status="not_dispatched",
    )
    await store.create_approval(approval)

    pending_before = await store.get_pending_approvals()
    assert len(pending_before) == 1

    # 3. Revoke tool to DENIED
    rev_resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "denied",
            "enabled": False,
            "expected_policy_version": 1,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers=headers,
    )
    assert rev_resp.status_code == 200

    # 4. Verify the pending approval was cancelled
    pending_after = await store.get_pending_approvals()
    assert len(pending_after) == 0

    record = await store.get_approval(approval.approval_id)
    assert record.status == "cancelled"
    assert "Host policy set to DENIED" in record.rejection_reason


# ---------------------------------------------------------------------------
# Execution Ledger Safety Review & Duplicate Dispatch Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_ledger_state_machine_and_atomic_reservation(admin_fixture):
    """Review execution ledger state machine and confirm atomic reservation prevents duplicate."""
    store = admin_fixture["approval_store"]
    tool1 = admin_fixture["tool1"]

    # Create approved record
    approval = ApprovalRecord(
        approval_id=f"app_{uuid.uuid4().hex[:12]}",
        interrupt_id="int_2",
        run_id="run_2",
        thread_id="th_2",
        server_id="time",
        tool_id=tool1.tool_id,
        tool_call_id="call_2",
        arguments={"timezone": "UTC"},
        argument_digest="digest_abc",
        tool_fingerprint=tool1.fingerprint,
        policy_version=1,
        created_at=datetime.now(UTC),
        status="approved",
        dispatch_status="not_dispatched",
    )
    await store.create_approval(approval)

    # Initial state is not_dispatched
    rec = await store.get_approval(approval.approval_id)
    assert rec.dispatch_status == "not_dispatched"

    # First dispatch reservation succeeds
    reserved = await store.start_dispatch(
        approval_id=approval.approval_id,
        tool_id=tool1.tool_id,
        argument_digest="digest_abc",
    )
    assert reserved is True

    # State is now in_flight
    rec_in_flight = await store.get_approval(approval.approval_id)
    assert rec_in_flight.dispatch_status == "in_flight"

    # Second concurrent reservation attempt MUST be rejected
    second_attempt = await store.start_dispatch(
        approval_id=approval.approval_id,
        tool_id=tool1.tool_id,
        argument_digest="digest_abc",
    )
    assert second_attempt is False

    # Complete the dispatch
    await store.complete_dispatch(
        approval_id=approval.approval_id,
        result_summary="Completed successfully",
    )

    ledger_entry = await store.get_ledger_entry(approval_id=approval.approval_id)
    assert ledger_entry is not None
    assert ledger_entry["state"] == "completed"

    # Attempting to dispatch after completion MUST be rejected
    post_complete_attempt = await store.start_dispatch(
        approval_id=approval.approval_id,
        tool_id=tool1.tool_id,
        argument_digest="digest_abc",
    )
    assert post_complete_attempt is False


@pytest.mark.asyncio
async def test_ledger_query_and_approvals_summary_endpoints(admin_fixture):
    """Audit ledger endpoint returns bounded records; approvals summary returns telemetry."""
    client = admin_fixture["client"]
    store = admin_fixture["approval_store"]
    tool1 = admin_fixture["tool1"]

    # Seed one approval and dispatch in ledger
    app_id = f"app_{uuid.uuid4().hex[:12]}"
    approval = ApprovalRecord(
        approval_id=app_id,
        interrupt_id="int_3",
        run_id="run_3",
        thread_id="th_3",
        server_id="time",
        tool_id=tool1.tool_id,
        tool_call_id="call_3",
        arguments={"timezone": "UTC"},
        argument_digest="digest_xyz",
        tool_fingerprint=tool1.fingerprint,
        policy_version=1,
        created_at=datetime.now(UTC),
        status="approved",
        dispatch_status="not_dispatched",
    )
    await store.create_approval(approval)
    await store.start_dispatch(app_id, tool1.tool_id, "digest_xyz")
    await store.complete_dispatch(app_id, "Sample summary")

    # Query ledger endpoint
    ledger_resp = await client.get("/api/v1/mcp/ledger?limit=10")
    assert ledger_resp.status_code == 200
    ledger_data = ledger_resp.json()
    assert ledger_data["total"] >= 1
    assert ledger_data["entries"][0]["approval_id"] == app_id
    assert ledger_data["entries"][0]["state"] == "completed"

    # Query approvals summary endpoint
    summary_resp = await client.get("/api/v1/mcp/approvals/summary")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_count"] >= 1


@pytest.mark.asyncio
async def test_no_arbitrary_tool_execution_endpoint_exists(admin_fixture):
    """Verify that no un-gated generic tool execution endpoint is exposed."""
    client = admin_fixture["client"]

    # POST /api/v1/mcp/execute or /api/v1/mcp/tools/execute must return 404/405
    resp = await client.post("/api/v1/mcp/execute", json={"cmd": "whoami"})
    assert resp.status_code in (404, 405)

    resp2 = await client.post("/api/v1/mcp/tools/time__get_current_time/execute", json={})
    assert resp2.status_code in (404, 405)


@pytest.mark.asyncio
async def test_e2e_test_mode_isolation(admin_fixture):
    """Verify that E2E test mode is disabled by default and visible in diagnostics."""
    client = admin_fixture["client"]

    # In default test setup, JAVED_E2E_TEST_MODE is not '1'
    os.environ.pop("JAVED_E2E_TEST_MODE", None)

    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["e2e_test_mode"] is False


# ---------------------------------------------------------------------------
# Phase 6B Focused Session Security & Host Validation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_session_bootstrap_does_not_leak_master_token(admin_fixture):
    """GET /auth/session without auth returns authenticated=false and never leaks master token."""
    client = admin_fixture["client"]
    owner_token = admin_fixture["owner_token"]

    resp = await client.get(
        "/api/v1/mcp/auth/session",
        headers={"Host": "127.0.0.1:8000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False
    assert owner_token not in str(data)
    assert "owner_token" not in data


@pytest.mark.asyncio
async def test_valid_owner_session_establishment_and_session_token_usage(admin_fixture):
    """POST /auth/session issues short-lived session token that authorizes mutations."""
    client = admin_fixture["client"]
    owner_token = admin_fixture["owner_token"]
    tool1 = admin_fixture["tool1"]

    # 1. Login with master owner token
    login_resp = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={
            "Origin": "http://localhost:5173",
            "Host": "localhost:8000",
        },
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    session_token = login_data["session_token"]

    # Master token must NOT be returned as the session token
    assert session_token != owner_token
    assert session_token.startswith("jvd_sess_")
    assert login_data["expires_in"] == 3600

    # 2. Check session status using session token
    status_resp = await client.get(
        "/api/v1/mcp/auth/session",
        headers={
            "X-Javed-Owner-Token": session_token,
            "Origin": "http://localhost:5173",
            "Host": "localhost:8000",
        },
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["authenticated"] is True

    # 3. Use session token for privileged permission mutation
    mut_resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "allowed_read_only",
            "expected_policy_version": 0,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers={
            "X-Javed-Owner-Token": session_token,
            "Origin": "http://localhost:5173",
            "Host": "localhost:8000",
        },
    )
    assert mut_resp.status_code == 200
    assert mut_resp.json()["tool"]["permission"] == "allowed_read_only"


@pytest.mark.asyncio
async def test_invalid_owner_token_login_rejected(admin_fixture):
    """POST /auth/session rejects invalid master owner token with 401."""
    client = admin_fixture["client"]

    resp = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": "wrong-secret-token"},
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
    )
    assert resp.status_code == 401
    assert "Invalid owner credentials" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_disallowed_host_header_rejected_against_dns_rebinding(admin_fixture):
    """Host header outside local loopback is rejected with 403 (anti-DNS-rebinding)."""
    client = admin_fixture["client"]
    owner_token = admin_fixture["owner_token"]

    resp = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={"Host": "attacker.com"},
    )
    assert resp.status_code == 403
    assert "forbidden" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cross_origin_session_requests_rejected(admin_fixture):
    """Cross-origin and Origin: null session requests are rejected with 403."""
    client = admin_fixture["client"]
    owner_token = admin_fixture["owner_token"]

    # Untrusted origin
    resp1 = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={"Origin": "http://malicious-site.com", "Host": "localhost:8000"},
    )
    assert resp1.status_code == 403

    # Origin: null
    resp2 = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={"Origin": "null", "Host": "localhost:8000"},
    )
    assert resp2.status_code == 403

    # Cross-site Sec-Fetch-Site
    resp3 = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={
            "Origin": "http://localhost:5173",
            "Sec-Fetch-Site": "cross-site",
            "Host": "localhost:8000",
        },
    )
    assert resp3.status_code == 403


@pytest.mark.asyncio
async def test_session_logout_revokes_token(admin_fixture):
    """POST /auth/logout immediately invalidates the issued session token."""
    client = admin_fixture["client"]
    owner_token = admin_fixture["owner_token"]
    tool1 = admin_fixture["tool1"]

    # 1. Login
    login_resp = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": owner_token},
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
    )
    session_token = login_resp.json()["session_token"]

    # 2. Logout
    logout_resp = await client.post(
        "/api/v1/mcp/auth/logout",
        headers={
            "X-Javed-Owner-Token": session_token,
            "Origin": "http://localhost:5173",
            "Host": "localhost:8000",
        },
    )
    assert logout_resp.status_code == 200

    # 3. Use revoked session token -> 401
    mut_resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "denied",
            "expected_policy_version": 0,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers={
            "X-Javed-Owner-Token": session_token,
            "Origin": "http://localhost:5173",
            "Host": "localhost:8000",
        },
    )
    assert mut_resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_owner_token_cannot_authorize_administration(admin_fixture):
    """When JAVED_OWNER_TOKEN is unset (None), all privileged operations fail closed."""
    app = admin_fixture["app"]
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]

    # Temporarily set owner_token to None on app settings
    original_token = app.state.settings.owner_token
    try:
        app.state.settings.owner_token = None

        # 1. Login attempt fails closed with 401
        login_resp = await client.post(
            "/api/v1/mcp/auth/session",
            json={"owner_token": "some-attempted-token"},
            headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
        )
        assert login_resp.status_code == 401
        assert "JAVED_OWNER_TOKEN is not configured" in login_resp.json()["detail"]

        # 2. Session check returns authenticated=false
        status_resp = await client.get(
            "/api/v1/mcp/auth/session",
            headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["authenticated"] is False

        # 3. Direct mutation attempt fails closed with 401
        mut_resp = await client.post(
            f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
            json={
                "permission": "allowed_read_only",
                "expected_policy_version": 0,
                "expected_fingerprint": tool1.fingerprint,
            },
            headers={
                "X-Javed-Owner-Token": "any-token",
                "Origin": "http://localhost:5173",
                "Host": "localhost:8000",
            },
        )
        assert mut_resp.status_code == 401
        assert "JAVED_OWNER_TOKEN is not configured" in mut_resp.json()["detail"]
    finally:
        app.state.settings.owner_token = original_token


def test_blank_owner_token_rejected_at_config():
    """Empty or whitespace JAVED_OWNER_TOKEN must be strictly rejected by Settings."""
    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        Settings(owner_token="")

    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        Settings(owner_token="   ")

    with pytest.raises(ValueError, match="cannot be empty or whitespace"):
        Settings(owner_token="\t\n")


def test_known_placeholder_token_rejected_at_config():
    """Known placeholder credentials (e.g. javed-local-owner-token) must be rejected."""
    for bad_token in [
        "javed-local-owner-token",
        "admin",
        "password",
        "secret",
        "token",
        "changeme",
        "12345678",
        "owner-token",
        "local-owner-token",
    ]:
        with pytest.raises(ValueError, match="cannot be a known weak placeholder"):
            Settings(owner_token=bad_token)


@pytest.mark.asyncio
async def test_test_mode_does_not_weaken_owner_authentication(admin_fixture):
    """Test mode must not weaken or bypass owner authentication checks."""
    client = admin_fixture["client"]
    tool1 = admin_fixture["tool1"]

    # Even in test mode, an unauthenticated mutation is strictly 401
    resp = await client.post(
        f"/api/v1/mcp/tools/{tool1.tool_id}/permission",
        json={
            "permission": "allowed_read_only",
            "expected_policy_version": 0,
            "expected_fingerprint": tool1.fingerprint,
        },
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
    )
    assert resp.status_code == 401
    assert "Local owner authorization token required" in resp.json()["detail"]

    # Even in test mode, bad credentials return 401
    bad_resp = await client.post(
        "/api/v1/mcp/auth/session",
        json={"owner_token": "definitely-wrong-secret-999"},
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8000"},
    )
    assert bad_resp.status_code == 401
    assert "Invalid owner credentials" in bad_resp.json()["detail"]
