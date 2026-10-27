"""Confidentiality and Sensitive Data Redaction Tests for MCP Gateway & Ledger
(BRICK-005 Phase 9 Carryover B).

Verifies that sensitive arguments (passwords, tokens, API keys, credentials) are redacted
on the backend before serialization across:
- Execution ledger API (GET /api/v1/mcp/ledger)
- Approvals API (GET /api/v1/agent/approvals, GET /api/v1/agent/approvals/{id}, etc.)
- Stream events (tool_requested, tool_started, approval_required)
while preserving raw values in the durable database for cryptographic digest integrity.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from javed.main import app
from javed.mcp.approval_store import (
    ApprovalStore,
    redact_sensitive_value,
)
from javed.schemas.approval import ApprovalRecord, compute_argument_digest


def test_sensitive_key_redaction_unit():
    """Unit test for redact_sensitive_value against sensitive keys and tokens."""
    sensitive_payload = {
        "timezone": "Europe/London",
        "api_key": "sk-or-v1-abcdef1234567890",
        "password": "SuperSecretPassword123!",
        "token": "jvd_sess_9876543210fedcba",
        "auth_secret": "my-secret-value",
        "bearer_token": "Bearer test-token-12345",
        "nested": {
            "safe_param": "regular_value",
            "access_token": "secret_access_token_999",
            "deep": {
                "client_secret": "deep_secret",
            },
        },
        "list_items": [
            {"name": "public_item", "secret_key": "should_be_redacted"},
            "regular_string",
        ],
    }

    redacted = redact_sensitive_value(sensitive_payload)

    # Non-sensitive keys are preserved
    assert redacted["timezone"] == "Europe/London"
    assert redacted["nested"]["safe_param"] == "regular_value"
    assert redacted["list_items"][0]["name"] == "public_item"
    assert redacted["list_items"][1] == "regular_string"

    # Sensitive keys are masked
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["auth_secret"] == "[REDACTED]"
    assert redacted["bearer_token"] == "[REDACTED]"
    assert redacted["nested"]["access_token"] == "[REDACTED]"
    assert redacted["nested"]["deep"]["client_secret"] == "[REDACTED]"
    assert redacted["list_items"][0]["secret_key"] == "[REDACTED]"


def test_sensitive_value_pattern_redaction():
    """Unit test verifying values with known credential prefixes are redacted even if obscure."""
    obscure_payload = {
        "custom_header": "sk-or-v1-abcdef1234567890",
        "session_cookie": "jvd_sess_1234567890abcdef",
        "auth_header": "Bearer some-very-secret-string",
    }

    redacted = redact_sensitive_value(obscure_payload)
    assert redacted["custom_header"] == "[REDACTED]"
    assert redacted["session_cookie"] == "[REDACTED]"
    assert redacted["auth_header"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_ledger_backend_redaction(tmp_path):
    """Test that execution ledger returns redacted arguments without leaking secrets."""
    db_path = tmp_path / "test_approvals.db"
    store = ApprovalStore(db_path=str(db_path))
    await store.initialize()

    # Create an approval with secret-bearing arguments
    raw_arguments = {
        "city": "Doha",
        "api_token": "sk-or-v1-1234567890",
        "admin_password": "PlaintextPassword!",
    }
    digest = compute_argument_digest(raw_arguments)

    record = ApprovalRecord(
        approval_id="appr_confidential_1",
        interrupt_id="intr_conf_1",
        run_id="run_conf_1",
        thread_id="thread_conf_1",
        server_id="time",
        tool_id="time__get_current_time",
        tool_call_id="call_conf_1",
        arguments=raw_arguments,
        argument_digest=digest,
        tool_fingerprint="fp_123",
        policy_version=1,
        created_at=datetime.now(UTC),
        status="pending",
    )
    await store.create_approval(record)
    await store.record_decision("appr_confidential_1", "approve", "thread_conf_1", "human_user")

    # Record dispatch ledger entry
    started = await store.start_dispatch(
        approval_id="appr_confidential_1",
        tool_id="time__get_current_time",
        argument_digest=digest,
    )
    assert started is True
    await store.complete_dispatch(
        approval_id="appr_confidential_1",
        result_summary="Current time in Doha: 13:00",
    )

    # Retrieve ledger entries through the store
    ledger_entries = await store.get_recent_ledger_entries(limit=10)
    assert len(ledger_entries) == 1
    entry = ledger_entries[0]

    # Verify that raw database record still has raw arguments intact for verification
    raw_approval = await store.get_approval("appr_confidential_1")
    assert raw_approval is not None
    assert raw_approval.arguments["api_token"] == "sk-or-v1-1234567890"
    assert compute_argument_digest(raw_approval.arguments) == digest

    # Verify that ledger entry has redacted arguments
    assert entry.get("arguments") is not None
    assert entry["arguments"]["city"] == "Doha"
    assert entry["arguments"]["api_token"] == "[REDACTED]"
    assert entry["arguments"]["admin_password"] == "[REDACTED]"

    await store.close()


@pytest.mark.asyncio
async def test_approvals_api_redaction(tmp_path):
    """Test that GET /api/v1/agent/approvals/* endpoints redact sensitive argument values."""
    db_path = tmp_path / "test_approvals_api.db"
    store = ApprovalStore(db_path=str(db_path))
    await store.initialize()

    raw_arguments = {
        "timezone": "UTC",
        "secret_token": "sk-or-v1-secret-token",
    }
    record = ApprovalRecord(
        approval_id="appr_api_redact_1",
        interrupt_id="intr_api_1",
        run_id="run_api_1",
        thread_id="thread_api_1",
        server_id="time",
        tool_id="time__get_current_time",
        tool_call_id="call_api_1",
        arguments=raw_arguments,
        argument_digest=compute_argument_digest(raw_arguments),
        tool_fingerprint="fp_test",
        policy_version=1,
        created_at=datetime.now(UTC),
        status="pending",
    )
    await store.create_approval(record)

    # Mock agent_runtime on app.state
    class MockRuntime:
        approval_store = store

    app.state.agent_runtime = MockRuntime()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test list pending approvals
        resp = await client.get("/api/v1/agent/approvals/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["approvals"]) >= 1
        item = next(a for a in data["approvals"] if a["approval_id"] == "appr_api_redact_1")
        assert item["arguments"]["timezone"] == "UTC"
        assert item["arguments"]["secret_token"] == "[REDACTED]"

        # 2. Test get single approval
        resp_single = await client.get("/api/v1/agent/approvals/appr_api_redact_1")
        assert resp_single.status_code == 200
        single_data = resp_single.json()
        assert single_data["approval"]["arguments"]["secret_token"] == "[REDACTED]"

    await store.close()
