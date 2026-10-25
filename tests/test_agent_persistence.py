"""Tests for LangGraph SQLite checkpointer persistence.

Covers thread isolation, concurrency serialization, and cross-process recovery.
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.schemas.agent import AgentStreamRequest


class PersistentMockChatModel(BaseChatModel):
    """Deterministic mock model that records conversational turns."""

    reply: Any = "Default reply"

    @property
    def _llm_type(self) -> str:
        return "persistent-mock"

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])

    async def _agenerate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


@pytest.mark.asyncio
async def test_sqlite_persistence_and_restart_recovery(tmp_path: Path) -> None:
    """Demonstrate real SQLite-backed persistence across process/session restarts."""
    db_file = str(tmp_path / "test_checkpoints.db")

    # Session 1: Create thread_a and record "Project Orchid"
    cp_mgr_1 = AgentCheckpointerManager(db_path=db_file)
    model_1 = PersistentMockChatModel(
        reply="Understood. The sample project is called Project Orchid."
    )
    runtime_1 = AgentRuntimeManager(checkpointer_manager=cp_mgr_1, model_override=model_1)
    await runtime_1.initialize()

    req_1 = AgentStreamRequest(
        thread_id="thread_orchid",
        message="For this conversation, remember that our sample project is called Project Orchid.",
    )
    events_1 = [ev async for ev in runtime_1.stream_agent(req_1)]
    assert any(e.event == "checkpoint_saved" for e in events_1)
    assert any(e.event == "run_completed" for e in events_1)

    # Clean shutdown of Session 1
    await runtime_1.close()

    # Verify SQLite file exists on disk
    assert Path(db_file).exists()
    assert Path(db_file).stat().st_size > 0

    # Session 2: Reconstruct runtime from scratch pointing to the same SQLite database file
    cp_mgr_2 = AgentCheckpointerManager(db_path=db_file)
    model_2 = PersistentMockChatModel(reply="The sample project is Project Orchid.")
    runtime_2 = AgentRuntimeManager(checkpointer_manager=cp_mgr_2, model_override=model_2)
    await runtime_2.initialize()

    # Retrieve restored thread_a state
    restored_state = await runtime_2.get_thread_state("thread_orchid")
    assert restored_state.exists is True
    assert len(restored_state.messages) >= 2
    assert "Project Orchid" in restored_state.messages[0].content

    # Query the persistent context in the second turn
    req_2 = AgentStreamRequest(
        thread_id="thread_orchid",
        message="What is the sample project called?",
    )
    events_2 = [ev async for ev in runtime_2.stream_agent(req_2)]
    completed_ev = next(e for e in events_2 if e.event == "run_completed")
    assert completed_ev.data["content"] == "The sample project is Project Orchid."

    # Verify thread list
    threads = await cp_mgr_2.list_threads()
    assert "thread_orchid" in threads
    assert await cp_mgr_2.thread_exists("thread_orchid") is True

    await runtime_2.close()


@pytest.mark.asyncio
async def test_thread_context_isolation(tmp_path: Path) -> None:
    """Verify that thread B cannot access or inherit private context from thread A."""
    db_file = str(tmp_path / "isolation_checkpoints.db")
    cp_mgr = AgentCheckpointerManager(db_path=db_file)
    model = PersistentMockChatModel(reply="Context acknowledged.")
    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr, model_override=model)
    await runtime.initialize()

    # Populate Thread A
    req_a = AgentStreamRequest(thread_id="thread_alpha", message="Alpha Secret Code: 42")
    _ = [ev async for ev in runtime.stream_agent(req_a)]

    # Inspect Thread A
    state_a = await runtime.get_thread_state("thread_alpha")
    assert state_a.exists is True
    assert any("Alpha Secret Code" in m.content for m in state_a.messages)

    # Inspect Thread B before running (must not exist)
    state_b_init = await runtime.get_thread_state("thread_beta")
    assert state_b_init.exists is False
    assert len(state_b_init.messages) == 0

    # Populate Thread B
    req_b = AgentStreamRequest(thread_id="thread_beta", message="Beta public message")
    _ = [ev async for ev in runtime.stream_agent(req_b)]

    state_b = await runtime.get_thread_state("thread_beta")
    assert state_b.exists is True
    # Thread B must have zero alpha content
    for msg in state_b.messages:
        assert "Alpha Secret Code" not in msg.content
        assert "42" not in msg.content

    await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_same_thread_runs_are_serialized(tmp_path: Path) -> None:
    """Verify that concurrent requests on same thread ID are safely serialized by lock."""
    db_file = str(tmp_path / "concurrent_checkpoints.db")
    cp_mgr = AgentCheckpointerManager(db_path=db_file)
    model = PersistentMockChatModel(reply="Serialized response.")
    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr, model_override=model)
    await runtime.initialize()

    req_1 = AgentStreamRequest(thread_id="thread_shared", message="Message 1")
    req_2 = AgentStreamRequest(thread_id="thread_shared", message="Message 2")

    # Run both concurrently
    async def run_req(r: AgentStreamRequest) -> list[Any]:
        return [ev async for ev in runtime.stream_agent(r)]

    results = await asyncio.gather(run_req(req_1), run_req(req_2))
    assert len(results) == 2
    for events in results:
        assert any(e.event == "run_completed" for e in events)

    # State must reflect both messages cleanly without database corruption
    state = await runtime.get_thread_state("thread_shared")
    assert state.exists is True
    assert len(state.messages) >= 4  # 2 user messages + 2 assistant messages

    await runtime.close()


@pytest.mark.asyncio
async def test_multipart_message_content_restoration(tmp_path: Path) -> None:
    """Verify multipart content blocks (list of dicts) are properly restored into clean text."""
    db_file = str(tmp_path / "multipart_checkpoints.db")
    cp_mgr = AgentCheckpointerManager(db_path=db_file)
    multipart_content = [
        {"type": "text", "text": "Implementation Step 1. "},
        {"type": "text", "text": "Validation Step 2."},
    ]
    model = PersistentMockChatModel(reply=multipart_content)
    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr, model_override=model)
    await runtime.initialize()

    req = AgentStreamRequest(thread_id="thread_multipart", message="Generate steps")
    _ = [ev async for ev in runtime.stream_agent(req)]

    state = await runtime.get_thread_state("thread_multipart")
    assert state.exists is True
    assistant_msgs = [m for m in state.messages if m.role == "assistant"]
    assert len(assistant_msgs) >= 1
    assert assistant_msgs[0].content == "Implementation Step 1. Validation Step 2."

    await runtime.close()


def test_cross_process_sqlite_recovery(tmp_path: Path) -> None:
    """Demonstrate genuine cross-process durability using two separate OS subprocesses."""
    db_file = str(tmp_path / "cross_process.db")
    secret_marker = "PROJECT_ORCHID_PROC_RECOVERY_9941"

    # Process 1: Write a checkpoint using Python subprocess
    proc1_code = """
import asyncio
import sys
from pathlib import Path
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.schemas.agent import AgentStreamRequest

db_path = sys.argv[1]
secret = sys.argv[2]

class Model(BaseChatModel):
    def _generate(self, messages, **kwargs):
        gen = ChatGeneration(message=AIMessage(content=f'Acknowledged {secret}'))
        return ChatResult(generations=[gen])
    def bind_tools(self, tools, **kwargs): return self
    @property
    def _llm_type(self): return 'proc-mock'

async def run():
    mgr = AgentCheckpointerManager(db_path)
    runtime = AgentRuntimeManager(checkpointer_manager=mgr, model_override=Model())
    await runtime.initialize()
    req = AgentStreamRequest(thread_id='thread_proc', message=f'Remember {secret}')
    async for _ in runtime.stream_agent(req): pass
    await runtime.close()

asyncio.run(run())
"""
    result1 = subprocess.run(
        [sys.executable, "-c", proc1_code, db_file, secret_marker],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result1.returncode == 0, f"Process 1 failed: {result1.stderr}"
    assert Path(db_file).exists()

    # Process 2: Read state from the database in a completely separate process
    proc2_code = """
import asyncio
import sys
from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager

db_path = sys.argv[1]
secret = sys.argv[2]

async def run():
    mgr = AgentCheckpointerManager(db_path)
    runtime = AgentRuntimeManager(checkpointer_manager=mgr)
    await runtime.initialize()
    state = await runtime.get_thread_state('thread_proc')
    assert state.exists is True
    found = any(secret in m.content for m in state.messages)
    assert found, 'Secret marker not found in restored messages'
    await runtime.close()
    print('SUCCESS')

asyncio.run(run())
"""
    result2 = subprocess.run(
        [sys.executable, "-c", proc2_code, db_file, secret_marker],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result2.returncode == 0, f"Process 2 failed: {result2.stderr}"
    assert "SUCCESS" in result2.stdout
