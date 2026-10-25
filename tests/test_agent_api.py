"""Tests for FastAPI Agent API endpoints: streaming, thread state, and runtime status."""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.main import create_app


class ApiMockModel(BaseChatModel):
    """Deterministic mock model for API testing."""

    responses: list[AIMessage]
    _idx: int = 0

    @property
    def _llm_type(self) -> str:
        return "api-mock"

    def _generate(self, messages: Any, **kwargs: Any) -> ChatResult:
        msg = self.responses[self._idx % len(self.responses)]
        self._idx += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages: Any, **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


@pytest.fixture
def test_app():
    settings = Settings(
        env="test",
        openrouter_api_key="sk-or-v1-mock-test-key",
        agent_checkpoint_db_path=":memory:",
    )
    app = create_app(settings)

    # Inject mock model into agent runtime
    call = {
        "name": "write_todos",
        "args": {
            "todos": [
                {"content": "Step 1: Check data", "status": "completed"},
                {"content": "Step 2: Implement", "status": "in_progress"},
            ]
        },
        "id": "c1",
    }
    m1 = AIMessage(content="", tool_calls=[call])
    m2 = AIMessage(content="API response completed.")
    mock_model = ApiMockModel(responses=[m1, m2])

    cp_mgr = AgentCheckpointerManager(db_path=":memory:")
    runtime = AgentRuntimeManager(
        settings=settings,
        checkpointer_manager=cp_mgr,
        model_override=mock_model,
    )
    app.state.agent_runtime = runtime
    return app


@pytest.mark.asyncio
async def test_get_agent_status(test_app) -> None:
    """Verify GET /api/v1/agent/status returns readiness and tool security boundaries."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agent/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checkpointer"] == "sqlite"
        assert data["security_profile"] == "zero-trust-planning-only"
        assert data["allowed_tools"] == ["write_todos"]
        assert "execute" in data["excluded_tools"]
        assert "ls" in data["excluded_tools"]


@pytest.mark.asyncio
async def test_post_agent_stream(test_app) -> None:
    """Verify POST /api/v1/agent/stream yields SSE events with planning and run lifecycle."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "thread_id": "api_test_thread_1",
            "message": "Please formulate a 2-step plan",
        }
        resp = await client.post("/api/v1/agent/stream", json=payload)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        lines = [line.strip() for line in body.split("\n") if line.strip()]

        events = []
        for line in lines:
            if line.startswith("data: "):
                data_str = line[6:]
                event_obj = json.loads(data_str)
                events.append(event_obj)

        event_types = [e["event"] for e in events]
        assert "run_started" in event_types
        assert "planning" in event_types
        assert "plan_updated" in event_types
        assert "checkpoint_saved" in event_types
        assert "run_completed" in event_types

        completed_ev = next(e for e in events if e["event"] == "run_completed")
        assert completed_ev["data"]["content"] == "API response completed."
        assert len(completed_ev["data"]["todos"]) == 2


@pytest.mark.asyncio
async def test_get_thread_state_endpoint(test_app) -> None:
    """Verify GET /api/v1/agent/threads/{thread_id} retrieves persisted thread state."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent thread returns exists=False
        resp_404 = await client.get("/api/v1/agent/threads/non_existent_thread")
        assert resp_404.status_code == 200
        assert resp_404.json()["exists"] is False

        # Execute stream to commit checkpoint
        payload = {
            "thread_id": "thread_persisted_api",
            "message": "Create task list",
        }
        stream_resp = await client.post("/api/v1/agent/stream", json=payload)
        assert stream_resp.status_code == 200

        # Retrieve state for populated thread
        resp = await client.get("/api/v1/agent/threads/thread_persisted_api")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert len(data["messages"]) >= 2
        assert len(data["todos"]) == 2
        assert data["todos"][0]["content"] == "Step 1: Check data"
