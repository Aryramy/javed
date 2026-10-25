"""Tests for AgentRuntimeManager execution lifecycle, planning, and streaming events."""

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.schemas.agent import AgentStreamRequest


class MultiTurnPlanningModel(BaseChatModel):
    """Model that simulates generating planning tool calls followed by a textual response."""

    responses: list[AIMessage]
    _idx: int = 0

    @property
    def _llm_type(self) -> str:
        return "multi-turn-planning"

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        msg = self.responses[self._idx % len(self.responses)]
        self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


class TokenStreamingModel(BaseChatModel):
    """Model that simulates chunked token generation."""

    tokens: list[str]

    @property
    def _llm_type(self) -> str:
        return "token-streaming"

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _agenerate(self, messages: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _astream(self, messages: Any, **kwargs: Any):
        for tok in self.tokens:
            yield ChatGenerationChunk(message=AIMessageChunk(content=tok))

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


@pytest.mark.asyncio
async def test_agent_planning_lifecycle_events() -> None:
    """Verify structured planning event emission via write_todos."""
    cp_mgr = AgentCheckpointerManager(db_path=":memory:")
    call = {
        "name": "write_todos",
        "args": {
            "todos": [
                {"content": "Step 1: Ingest SharePoint Data", "status": "completed"},
                {"content": "Step 2: Build Star Schema", "status": "in_progress"},
                {"content": "Step 3: Define DAX Measures", "status": "pending"},
            ]
        },
        "id": "call_planning_1",
    }
    msg1 = AIMessage(content="", tool_calls=[call])
    msg2 = AIMessage(content="Implementation plan prepared successfully.")
    model = MultiTurnPlanningModel(responses=[msg1, msg2])

    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr, model_override=model)
    await runtime.initialize()

    req = AgentStreamRequest(
        thread_id="plan_thread_1",
        message="Create a 3-step Power BI plan",
    )

    events = [ev async for ev in runtime.stream_agent(req)]
    event_names = [e.event for e in events]

    assert "run_started" in event_names
    assert "planning" in event_names
    assert "plan_updated" in event_names
    assert "checkpoint_saved" in event_names
    assert "run_completed" in event_names

    planning_ev = next(e for e in events if e.event == "planning")
    assert len(planning_ev.data["todos"]) == 3
    assert planning_ev.data["todos"][0]["content"] == "Step 1: Ingest SharePoint Data"

    completed_ev = next(e for e in events if e.event == "run_completed")
    assert completed_ev.data["content"] == "Implementation plan prepared successfully."
    assert len(completed_ev.data["todos"]) == 3

    await runtime.close()


@pytest.mark.asyncio
async def test_agent_token_streaming_events() -> None:
    """Verify token streaming chunks are delivered with correct deltas."""
    cp_mgr = AgentCheckpointerManager(db_path=":memory:")
    model = TokenStreamingModel(tokens=["A ", "Power BI ", "measure ", "is dynamic."])
    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr, model_override=model)
    await runtime.initialize()

    req = AgentStreamRequest(
        thread_id="stream_thread_1",
        message="Explain what a Power BI measure is",
    )

    events = [ev async for ev in runtime.stream_agent(req)]
    stream_events = [e for e in events if e.event == "model_streaming"]
    assert len(stream_events) == 4
    deltas = [e.data["delta"] for e in stream_events]
    assert "".join(deltas) == "A Power BI measure is dynamic."

    await runtime.close()


@pytest.mark.asyncio
async def test_agent_runtime_status() -> None:
    """Verify get_status returns readiness, security profile, and tool boundaries."""
    cp_mgr = AgentCheckpointerManager(db_path=":memory:")
    runtime = AgentRuntimeManager(checkpointer_manager=cp_mgr)
    await runtime.initialize()

    status = await runtime.get_status()
    assert status.status == "ready"
    assert status.checkpointer == "sqlite"
    assert status.security_profile == "zero-trust-planning-only"
    assert status.allowed_tools == ["write_todos"]
    assert "execute" in status.excluded_tools
    assert "read_file" in status.excluded_tools

    await runtime.close()
