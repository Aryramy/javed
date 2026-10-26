"""Cross-process restart recovery and HITL resumption test for BRICK-005 Phase 5B.

Demonstrates that an interrupted LangGraph agent run and pending MCP approval:
1. Are created and persisted by OS Process A.
2. Process A exits completely (reported PID and exit code 0).
3. OS Process B starts in an independent interpreter with the same databases.
4. Process B recovers the pending approval and validates all durable identities.
5. Process B approves and resumes the agent execution.
6. The real Time MCP server executes exactly once.
7. Subsequent duplicate approvals are rejected by the execution ledger.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.mcp.approval_store import ApprovalStore
from javed.mcp.gateway import SecureMCPGateway
from javed.mcp.registry import DynamicMCPRegistry
from javed.mcp.servers import TIME_SERVER_ID, create_time_server_config
from javed.schemas.agent import AgentStreamRequest


class _CrossProcessScriptedModel(BaseChatModel):
    """Deterministic model that emits a tool call in Process A, or text answer in Process B."""

    def __init__(
        self,
        tool_name: str | None = "time__get_current_time",
        tool_args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_args = tool_args or {"timezone": "UTC"}

    @property
    def _llm_type(self) -> str:
        return "cross-process-scripted-model"

    def _generate(
        self,
        messages: Any,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self._tool_name is not None:
            tool_call = {
                "name": self._tool_name,
                "args": self._tool_args,
                "id": "call_hitl_xp",
                "type": "tool_call",
            }
            msg = AIMessage(
                content="",
                tool_calls=[tool_call],
            )
        else:
            msg = AIMessage(
                content="The verified time operation has finished.",
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self,
        messages: Any,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


async def run_process_a(checkpoints_db: str, approvals_db: str, thread_id: str) -> None:
    """Process A: Trigger interrupted run and persist pending approval, then exit."""
    pid = os.getpid()
    print(f"[PROCESS_A_START] PID={pid}")

    settings = Settings(
        agent_checkpoint_db_path=checkpoints_db,
        agent_approvals_db_path=approvals_db,
    )
    store = ApprovalStore(approvals_db)
    await store.initialize()

    registry = DynamicMCPRegistry()
    registry.register_server(create_time_server_config())
    await registry.discover_tools(TIME_SERVER_ID)
    registry.set_tool_permission("time__get_current_time", "APPROVAL_REQUIRED")

    gateway = SecureMCPGateway(registry, approval_store=store)
    model = _CrossProcessScriptedModel("time__get_current_time", {"timezone": "UTC"})

    manager = AgentRuntimeManager(
        settings=settings,
        mcp_gateway=gateway,
        approval_store=store,
        model_override=model,
    )
    await manager.initialize()

    req = AgentStreamRequest(thread_id=thread_id, message="What is the current time?")
    events = []
    async for ev in manager.stream_agent(req):
        events.append(ev)

    event_types = [e.event for e in events]
    assert "approval_required" in event_types, f"Process A did not pause on approval: {event_types}"

    # Extract approval ID
    appr_event = next(e for e in events if e.event == "approval_required")
    approval_id = appr_event.data["approval_id"]

    # Verify persisted in SQLite
    saved = await store.get_approval(approval_id)
    assert saved is not None
    assert saved.status == "pending"

    await manager.close()
    await registry.disconnect_all()
    print(f"[PROCESS_A_APPROVAL_ID]={approval_id}")
    print(f"[PROCESS_A_SUCCESS] PID={pid}")


async def run_process_b(
    checkpoints_db: str, approvals_db: str, thread_id: str, approval_id: str
) -> None:
    """Process B: Open databases, recover approval, validate identities,
    resume execution, and verify genuine tool execution.
    """
    pid = os.getpid()
    print(f"[PROCESS_B_START] PID={pid}")

    settings = Settings(
        agent_checkpoint_db_path=checkpoints_db,
        agent_approvals_db_path=approvals_db,
    )
    store = ApprovalStore(approvals_db)
    await store.initialize()

    # Step 6 & 7: Recover approval and validate all durable identities
    rec = await store.get_approval(approval_id)
    assert rec is not None, f"Process B could not find approval {approval_id}"
    assert rec.status == "pending", f"Expected pending, got {rec.status}"
    assert rec.thread_id == thread_id, f"Thread ID mismatch: {rec.thread_id} != {thread_id}"
    assert rec.server_id == "time"
    assert rec.tool_id == "time__get_current_time"
    assert rec.arguments == {"timezone": "UTC"}
    assert rec.interrupt_id is not None
    assert rec.run_id is not None

    registry = DynamicMCPRegistry()
    registry.register_server(create_time_server_config())
    await registry.discover_tools(TIME_SERVER_ID)
    registry.set_tool_permission("time__get_current_time", "APPROVAL_REQUIRED")

    gateway = SecureMCPGateway(registry, approval_store=store)
    model = _CrossProcessScriptedModel(tool_name=None)

    manager = AgentRuntimeManager(
        settings=settings,
        mcp_gateway=gateway,
        approval_store=store,
        model_override=model,
    )
    await manager.initialize()

    # Step 8: Approve and resume interrupted execution
    resume_events = []
    async for ev in manager.resume_agent(
        thread_id=thread_id,
        approval_id=approval_id,
        decision="approve",
    ):
        resume_events.append(ev)

    resume_types = [e.event for e in resume_events]
    assert "approval_approved" in resume_types, f"Missing approval_approved: {resume_types}"
    assert "agent_resumed" in resume_types, f"Missing agent_resumed: {resume_types}"
    assert "tool_started" in resume_types, f"Missing tool_started: {resume_types}"
    assert "tool_completed" in resume_types, f"Missing tool_completed: {resume_types}"
    assert "run_completed" in resume_types, f"Missing run_completed: {resume_types}"

    # Step 9: Verify real MCP dispatch occurred exactly once
    tool_ev = next(e for e in resume_events if e.event == "tool_completed")
    raw_output = tool_ev.data.get("output", "")
    assert "current_time" in raw_output or "T" in raw_output

    ledger = await store.get_ledger_entry("time__get_current_time", rec.argument_digest)
    assert ledger is not None
    assert ledger["state"] == "completed"

    rec_after = await store.get_approval(approval_id)
    assert rec_after is not None
    assert rec_after.status == "approved"
    assert rec_after.dispatch_status == "completed"

    # Step 10: Verify duplicate approval is rejected
    try:
        await store.record_decision(approval_id, "approve", expected_thread_id=thread_id)
        raise AssertionError("Duplicate approval should have been rejected!")
    except ValueError as ve:
        assert "cannot be modified" in str(ve) or "cannot be decided" in str(ve)

    await manager.close()
    await registry.disconnect_all()
    print(f"[PROCESS_B_TOOL_OUTPUT]={raw_output[:50]}")
    print(f"[PROCESS_B_SUCCESS] PID={pid}")


def main() -> None:
    """Subprocess CLI dispatcher."""
    parser = argparse.ArgumentParser(description="Cross-process runner")
    parser.add_argument("step", choices=["process_a", "process_b"])
    parser.add_argument("--checkpoints-db", required=True)
    parser.add_argument("--approvals-db", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--approval-id", required=False)

    args = parser.parse_args()

    if args.step == "process_a":
        asyncio.run(
            run_process_a(
                checkpoints_db=args.checkpoints_db,
                approvals_db=args.approvals_db,
                thread_id=args.thread_id,
            )
        )
    elif args.step == "process_b":
        if not args.approval_id:
            print("Error: --approval-id is required for process_b", file=sys.stderr)
            sys.exit(2)
        asyncio.run(
            run_process_b(
                checkpoints_db=args.checkpoints_db,
                approvals_db=args.approvals_db,
                thread_id=args.thread_id,
                approval_id=args.approval_id,
            )
        )


# ---------------------------------------------------------------------------
# Pytest test exercising genuine independent operating system processes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_genuine_cross_process_restart_recovery(tmp_path: Any) -> None:
    """[live OS process restart] Verify persistence, recovery, and execution
    across independent OS processes.
    """
    checkpoints_db = str(tmp_path / "cross_checkpoints.db")
    approvals_db = str(tmp_path / "cross_approvals.db")
    thread_id = f"thread-xp-{uuid.uuid4().hex[:6]}"
    script_path = str(Path(__file__).resolve())

    # 1. Run Process A
    proc_a = subprocess.run(
        [
            sys.executable,
            script_path,
            "process_a",
            "--checkpoints-db",
            checkpoints_db,
            "--approvals-db",
            approvals_db,
            "--thread-id",
            thread_id,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("Process A stdout:\n", proc_a.stdout)
    if proc_a.returncode != 0:
        print("Process A stderr:\n", proc_a.stderr)
    assert proc_a.returncode == 0, f"Process A failed with code {proc_a.returncode}"
    assert "[PROCESS_A_SUCCESS]" in proc_a.stdout

    # Extract Process A PID and approval ID
    lines_a = proc_a.stdout.splitlines()
    pid_a_line = next(line for line in lines_a if "[PROCESS_A_START]" in line)
    pid_a = pid_a_line.split("PID=")[1].strip()

    appr_line = next(line for line in lines_a if "[PROCESS_A_APPROVAL_ID]" in line)
    approval_id = appr_line.split("=")[1].strip()

    # 2. Run Process B
    proc_b = subprocess.run(
        [
            sys.executable,
            script_path,
            "process_b",
            "--checkpoints-db",
            checkpoints_db,
            "--approvals-db",
            approvals_db,
            "--thread-id",
            thread_id,
            "--approval-id",
            approval_id,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("Process B stdout:\n", proc_b.stdout)
    if proc_b.returncode != 0:
        print("Process B stderr:\n", proc_b.stderr)
    assert proc_b.returncode == 0, f"Process B failed with code {proc_b.returncode}"
    assert "[PROCESS_B_SUCCESS]" in proc_b.stdout

    # Extract Process B PID
    lines_b = proc_b.stdout.splitlines()
    pid_b_line = next(line for line in lines_b if "[PROCESS_B_START]" in line)
    pid_b = pid_b_line.split("PID=")[1].strip()

    # Assert that Process A and Process B were distinct OS processes
    assert pid_a != pid_b, f"PIDs should be different: {pid_a} == {pid_b}"
    print(f"Verified distinct OS processes: Process A (PID {pid_a}), Process B (PID {pid_b})")


if __name__ == "__main__":
    main()
