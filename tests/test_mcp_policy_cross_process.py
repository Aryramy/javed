"""Cross-process host policy persistence and restart safety test for BRICK-005 Phase 6B.

Demonstrates that host-approved MCP tool permissions:
1. Process A: Connects real Time MCP server, authenticates as local owner, grants
   time__get_current_time ALLOWED_READ_ONLY, persists to SQLite, and exits completely.
2. Process B: Starts in a completely independent Python OS process, connects to the same isolated
   database, restores persisted policies, verifies fingerprints, policy version, and confirms
   effective authorization through SecureMCPGateway.
3. Tests changed-schema drift: Tampers with approved fingerprint in SQLite, verifies that Process B
   invalidates the drifted policy and resets to DENIED.
4. Tests revocation persistence: Process B revokes time__get_current_time to DENIED, terminates,
   and Process C starts and confirms the tool remains DENIED across processes.
"""

import argparse
import asyncio
import os
import subprocess
import sys

import pytest

from javed.mcp.approval_store import ApprovalStore
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import TIME_SERVER_ID, create_time_server_config


async def run_process_a(approvals_db: str, checkpoints_db: str) -> None:
    """Process A: Connect Time server, grant ALLOWED_READ_ONLY, persist, and exit."""
    pid = os.getpid()
    print(f"[PROCESS_A_START] PID={pid}")

    store = ApprovalStore(approvals_db)
    await store.initialize()

    registry = DynamicMCPRegistry(approval_store=store)
    registry.register_server(create_time_server_config())

    # Connect and discover live tools from official Time server
    await registry.connect(TIME_SERVER_ID)
    discovered = await registry.discover_tools(TIME_SERVER_ID)
    assert len(discovered) == 2, f"Expected 2 tools from Time server, got {len(discovered)}"

    time_tool = registry.get_tool("time__get_current_time")
    assert time_tool is not None
    assert time_tool.permission == "denied", "New tool must default to DENIED"

    # Authenticate as host owner and grant ALLOWED_READ_ONLY
    updated = await registry.update_tool_permission_durable(
        tool_id="time__get_current_time",
        permission="allowed_read_only",
        enabled=True,
        approved_by="local_host_owner",
        expected_policy_version=0,
        expected_fingerprint=time_tool.fingerprint,
    )
    assert updated.permission == "allowed_read_only"
    assert registry.policy_version == 1

    # Verify SQLite row
    persisted = await store.get_host_tool_policy("time__get_current_time")
    assert persisted is not None
    assert persisted["permission"] == "allowed_read_only"
    assert persisted["approved_fingerprint"] == time_tool.fingerprint
    assert persisted["policy_version"] == 1

    await registry.disconnect_all()
    print(f"[PROCESS_A_SUCCESS] PID={pid} Policy persisted with version 1")


async def run_process_b(approvals_db: str, checkpoints_db: str) -> None:
    """Process B: Restore policy in new process, verify authorization, then test schema drift."""
    pid = os.getpid()
    print(f"[PROCESS_B_START] PID={pid}")

    store = ApprovalStore(approvals_db)
    await store.initialize()

    registry = DynamicMCPRegistry(approval_store=store)
    registry.register_server(create_time_server_config())

    # Step 1: Load persisted policies on startup before discovery
    await registry.load_persisted_policies()
    assert registry.policy_version == 1

    # Step 2: Connect and run discovery (which links discovered tools to restored policies)
    await registry.connect(TIME_SERVER_ID)
    discovered = await registry.discover_tools(TIME_SERVER_ID)
    assert len(discovered) == 2

    # Step 3: Verify restored policy
    restored_tool = registry.get_tool("time__get_current_time")
    assert restored_tool is not None
    assert restored_tool.permission == "allowed_read_only", (
        f"Expected ALLOWED_READ_ONLY restored, got {restored_tool.permission}"
    )
    assert restored_tool.enabled is True
    assert "time__get_current_time" in registry.get_allowed_read_only_mcp_tools()
    assert registry.is_tool_authorized_for_execution("time__get_current_time")
    assert restored_tool.fingerprint == registry.get_tool_metadata_fingerprint(
        "time__get_current_time"
    )

    # Step 4: Verify second tool (time__convert_time) remained DENIED
    convert_tool = registry.get_tool("time__convert_time")
    assert convert_tool is not None
    assert convert_tool.permission == "denied", "Unapproved tool must remain DENIED"

    # Step 5: Verify gateway execution allows time__get_current_time
    gateway = SecureMCPGateway(registry=registry)
    result = await gateway.execute_tool(
        tool_id="time__get_current_time",
        arguments={"timezone": "UTC"},
    )
    assert isinstance(result, str)
    assert len(result) > 0

    # Step 6: Test schema drift invalidation
    # Directly tamper with persisted fingerprint in SQLite to simulate remote schema drift
    await store.save_host_tool_policy(
        tool_id="time__get_current_time",
        server_id="time",
        permission="allowed_read_only",
        enabled=True,
        approved_fingerprint="drifted_tampered_fingerprint_000000000000000000000000000000000000",
        policy_version=2,
        updated_by="attacker",
    )

    # Disconnect registry adapter before connecting drift_registry
    # to avoid having two active adapters connected to the same server concurrently
    await registry.disconnect_all()

    # Re-instantiate registry and discover: drift must reset tool to DENIED
    drift_registry = DynamicMCPRegistry(approval_store=store)
    drift_registry.register_server(create_time_server_config())
    await drift_registry.load_persisted_policies()
    await drift_registry.connect(TIME_SERVER_ID)
    await drift_registry.discover_tools(TIME_SERVER_ID)

    drifted_tool = drift_registry.get_tool("time__get_current_time")
    assert drifted_tool is not None
    assert drifted_tool.permission == "denied", "Drifted fingerprint MUST invalidate to DENIED"
    assert "Schema drifted" in (drifted_tool.last_error or "")

    # Step 7: Revoke permission to DENIED and persist
    await drift_registry.update_tool_permission_durable(
        tool_id="time__get_current_time",
        permission="denied",
        enabled=False,
        approved_by="local_host_owner",
        expected_policy_version=drift_registry.policy_version,
        expected_fingerprint=drifted_tool.fingerprint,
    )
    await drift_registry.disconnect_all()
    print(f"[PROCESS_B_SUCCESS] PID={pid} Restoration and drift invalidation verified")


async def run_process_c(approvals_db: str, checkpoints_db: str) -> None:
    """Process C: Verify that explicit revocation is durably retained across processes."""
    pid = os.getpid()
    print(f"[PROCESS_C_START] PID={pid}")

    store = ApprovalStore(approvals_db)
    await store.initialize()

    registry = DynamicMCPRegistry(approval_store=store)
    registry.register_server(create_time_server_config())
    await registry.load_persisted_policies()
    await registry.connect(TIME_SERVER_ID)
    await registry.discover_tools(TIME_SERVER_ID)

    tool = registry.get_tool("time__get_current_time")
    assert tool is not None
    assert tool.permission == "denied", "Revoked permission must remain DENIED in Process C"
    await registry.disconnect_all()
    print(f"[PROCESS_C_SUCCESS] PID={pid} Revocation retention verified")


@pytest.mark.asyncio
async def test_cross_process_policy_persistence(tmp_path):
    """Orchestrate Process A -> Process B -> Process C in separate OS subprocesses."""
    checkpoints_db = str(tmp_path / "checkpoints.db")
    approvals_db = str(tmp_path / "approvals.db")

    test_script = os.path.abspath(__file__)
    python_exe = sys.executable

    # 1. Run Process A
    res_a = subprocess.run(
        [
            python_exe,
            test_script,
            "--role",
            "process_a",
            "--approvals-db",
            approvals_db,
            "--checkpoints-db",
            checkpoints_db,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("Process A stdout:\n", res_a.stdout)
    if res_a.returncode != 0:
        print("Process A stderr:\n", res_a.stderr)
    assert res_a.returncode == 0, f"Process A failed with code {res_a.returncode}"
    assert "[PROCESS_A_SUCCESS]" in res_a.stdout

    # 2. Run Process B
    res_b = subprocess.run(
        [
            python_exe,
            test_script,
            "--role",
            "process_b",
            "--approvals-db",
            approvals_db,
            "--checkpoints-db",
            checkpoints_db,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("Process B stdout:\n", res_b.stdout)
    if res_b.returncode != 0:
        print("Process B stderr:\n", res_b.stderr)
    assert res_b.returncode == 0, f"Process B failed with code {res_b.returncode}"
    assert "[PROCESS_B_SUCCESS]" in res_b.stdout

    # 3. Run Process C
    res_c = subprocess.run(
        [
            python_exe,
            test_script,
            "--role",
            "process_c",
            "--approvals-db",
            approvals_db,
            "--checkpoints-db",
            checkpoints_db,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("Process C stdout:\n", res_c.stdout)
    if res_c.returncode != 0:
        print("Process C stderr:\n", res_c.stderr)
    assert res_c.returncode == 0, f"Process C failed with code {res_c.returncode}"
    assert "[PROCESS_C_SUCCESS]" in res_c.stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["process_a", "process_b", "process_c"], required=True)
    parser.add_argument("--approvals-db", required=True)
    parser.add_argument("--checkpoints-db", required=True)
    args = parser.parse_args()

    if args.role == "process_a":
        asyncio.run(run_process_a(args.approvals_db, args.checkpoints_db))
    elif args.role == "process_b":
        asyncio.run(run_process_b(args.approvals_db, args.checkpoints_db))
    elif args.role == "process_c":
        asyncio.run(run_process_c(args.approvals_db, args.checkpoints_db))
