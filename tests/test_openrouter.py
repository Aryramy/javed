"""Unit tests for OpenRouter adapter service, rate calculation, and chat endpoints."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from javed.config import Settings
from javed.main import create_app
from javed.schemas.chat import ChatMessage, ChatRequest
from javed.services.openrouter import CURATED_MODELS, OpenRouterService


@pytest.fixture
def mock_settings() -> Settings:
    """Settings fixture with mock OpenRouter configuration."""
    return Settings(
        env="test",
        openrouter_api_key="sk-or-v1-mock-test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_default_model="openrouter/auto",
        openrouter_daily_budget_usd=5.00,
    )


def test_rate_card_cost_calculation(mock_settings: Settings) -> None:
    """Verify rate card pricing calculations for known and fallback models."""
    service = OpenRouterService(mock_settings)

    # gpt-4o-mini: $0.15/1M prompt, $0.60/1M completion
    cost_mini = service.calculate_cost(
        "openai/gpt-4o-mini",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    assert cost_mini == 0.75

    cost_small = service.calculate_cost(
        "openai/gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    expected_small = (1000 * 0.15 / 1_000_000) + (500 * 0.60 / 1_000_000)
    assert abs(cost_small - expected_small) < 1e-9

    # Upstream cost should take precedence if > 0
    upstream_res = service.calculate_cost("openai/gpt-4o-mini", 100, 100, upstream_cost=0.000123)
    assert upstream_res == 0.000123

    # Unknown model fallback pricing ($1.00 / $3.00)
    fallback_cost = service.calculate_cost("unknown/model-xyz", 1_000_000, 1_000_000)
    assert fallback_cost == 4.00


@pytest.mark.asyncio
async def test_get_models_catalog(mock_settings: Settings) -> None:
    """Verify model catalog returns models, search filters, and settings defaults."""
    service = OpenRouterService(mock_settings)
    with patch.object(service, "get_account_status", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = {
            "data": {
                "limit_remaining": 42.50,
                "usage_daily": 0.15,
            }
        }
        catalog = await service.get_models()

        assert catalog.authenticated is True
        assert catalog.default_model == "openrouter/auto"
        assert catalog.quota_remaining_usd == 42.50
        assert catalog.daily_budget_usd == 5.00
        assert len(catalog.models) >= len(CURATED_MODELS)
        assert catalog.is_dynamic is True

        default_entry = next((m for m in catalog.models if m.id == "openrouter/auto"), None)
        assert default_entry is not None
        assert default_entry.is_default is True
        assert default_entry.is_favorite is True

        # Test favorites filtering (Auto Router + 5 curated frontier models)
        fav_catalog = await service.get_models(favorites_only=True)
        assert len(fav_catalog.models) == 6
        assert all(m.is_favorite for m in fav_catalog.models)
        auto_entry = next((m for m in fav_catalog.models if m.id == "openrouter/auto"), None)
        assert auto_entry is not None
        assert auto_entry.is_router is True
        assert auto_entry.cost_tier == "low"

        # Test search filtering
        search_catalog = await service.get_models(search="gpt-4o-mini")
        assert any(m.id == "openai/gpt-4o-mini" for m in search_catalog.models)


@pytest.mark.asyncio
async def test_stream_chat_missing_api_key() -> None:
    """Verify stream_chat emits error event when API key is missing."""
    settings = Settings(env="test", openrouter_api_key=None)
    service = OpenRouterService(settings)
    request = ChatRequest(messages=[ChatMessage(role="user", content="Hi")])

    events = [event async for event in service.stream_chat(request)]
    assert len(events) == 1
    assert events[0].type == "error"
    assert "OpenRouter API key is not configured" in events[0].error


@pytest.mark.asyncio
async def test_stream_chat_mock_success(mock_settings: Settings) -> None:
    """Verify streaming token assembly and usage event handling."""
    mock_chunks = [
        'data: {"choices":[{"delta":{"content":"Javed"}}]}',
        'data: {"choices":[{"delta":{"content":" online"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":2,"cost":0.000003}}',
        "data: [DONE]",
    ]

    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for chunk in mock_chunks:
                yield chunk

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.stream.return_value = FakeStreamResponse()

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(messages=[ChatMessage(role="user", content="Status?")])

    events = [event async for event in service.stream_chat(request)]

    token_texts = [e.content for e in events if e.type == "token"]
    assert token_texts == ["Javed", " online"]

    usage_events = [e.usage for e in events if e.type == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].prompt_tokens == 12
    assert usage_events[0].completion_tokens == 2
    assert usage_events[0].cost_usd == 0.000003

    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_stream_chat_upstream_error(mock_settings: Settings) -> None:
    """Verify upstream HTTP error yields clean error envelope."""
    class FakeErrorResponse:
        status_code = 401

        async def aread(self):
            return json.dumps({"error": {"message": "Invalid API key"}}).encode("utf-8")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.stream.return_value = FakeErrorResponse()

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(messages=[ChatMessage(role="user", content="Ping")])

    events = [event async for event in service.stream_chat(request)]
    assert len(events) == 1
    assert events[0].type == "error"
    assert "Invalid API key" in events[0].error


def test_api_models_endpoint(mock_settings: Settings) -> None:
    """Test GET /api/v1/models returns 200 and matches schema."""
    app = create_app(mock_settings)
    client = TestClient(app)

    response = client.get("/api/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "default_model" in data
    assert data["default_model"] == "openrouter/auto"
    assert data["authenticated"] is True


def test_api_chat_stream_endpoint(mock_settings: Settings) -> None:
    """Test POST /api/v1/chat/stream returns text/event-stream."""
    app = create_app(mock_settings)

    # Mock openrouter_service on app.state
    async def fake_stream(_request):
        from javed.schemas.chat import ChatStreamEvent, StreamUsage
        yield ChatStreamEvent(type="token", content="Test")
        usage = StreamUsage(
            prompt_tokens=5,
            completion_tokens=1,
            total_tokens=6,
            cost_usd=0.0001,
        )
        yield ChatStreamEvent(type="usage", usage=usage)
        yield ChatStreamEvent(type="done")

    app.state.openrouter_service.stream_chat = fake_stream

    client = TestClient(app)
    response = client.post(
        "/api/v1/chat/stream",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "openai/gpt-4o-mini",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    body = response.text
    assert 'data: {"type":"token","content":"Test"' in body
    assert 'data: {"type":"usage"' in body
    assert 'data: {"type":"done"' in body


@pytest.mark.asyncio
async def test_auto_router_request_payload_and_plugins(mock_settings: Settings) -> None:
    """Verify openrouter/auto injects official auto-router plugin and cost_tier."""
    captured_payload: dict = {}

    class FakeAutoStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            chunk1 = json.dumps({
                "model": "anthropic/claude-3.5-sonnet",
                "choices": [{"delta": {"content": "Hi"}}],
            })
            chunk2 = json.dumps({
                "model": "anthropic/claude-3.5-sonnet",
                "choices": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "cost": 0.00002},
            })
            yield f"data: {chunk1}"
            yield f"data: {chunk2}"
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return FakeAutoStreamResponse()

    mock_client.stream.side_effect = fake_stream

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(
        model="openrouter/auto",
        cost_tier="high",
        messages=[ChatMessage(role="user", content="Hello")],
    )

    events = [event async for event in service.stream_chat(request)]

    # Verify Auto Router plugin configuration in outgoing payload
    assert captured_payload["model"] == "openrouter/auto"
    assert "plugins" in captured_payload
    assert len(captured_payload["plugins"]) == 1
    plugin = captured_payload["plugins"][0]
    assert plugin["id"] == "auto-router"
    assert plugin["cost_tier"] == "high"
    assert "costTier" not in plugin

    # Verify selected model extraction
    token_events = [e for e in events if e.type == "token"]
    assert len(token_events) == 1
    assert token_events[0].selected_model == "anthropic/claude-3.5-sonnet"
    assert token_events[0].requested_model == "openrouter/auto"

    usage_events = [e for e in events if e.type == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].usage.selected_model == "anthropic/claude-3.5-sonnet"
    assert usage_events[0].usage.requested_model == "openrouter/auto"
    assert usage_events[0].usage.cost_tier == "high"


@pytest.mark.asyncio
async def test_auto_router_cost_tier_default_fallback(mock_settings: Settings) -> None:
    """Verify invalid or omitted cost_tier cleanly defaults to economical 'low' tier."""
    captured_payload: dict = {}

    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"model":"openai/gpt-4o-mini","choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return FakeStreamResponse()

    mock_client.stream.side_effect = fake_stream

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(
        model="openrouter/auto",
        messages=[ChatMessage(role="user", content="Test")],
    )

    events = [event async for event in service.stream_chat(request)]

    assert captured_payload["plugins"][0]["cost_tier"] == "low"
    assert "costTier" not in captured_payload["plugins"][0]
    assert events[0].selected_model == "openai/gpt-4o-mini"
    assert events[0].requested_model == "openrouter/auto"


@pytest.mark.asyncio
async def test_auto_router_all_five_cost_tiers_request_serialization(mock_settings: Settings) -> None:
    """Validate all five cost tiers at request serialization without live calls."""
    tiers = ["low", "medium", "high", "xhigh", "max"]
    for tier in tiers:
        captured_payload: dict = {}

        class FakeStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                yield 'data: {"model":"openai/gpt-4o-mini","choices":[{"delta":{"content":"ok"}}]}'
                yield "data: [DONE]"

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        def fake_stream(method, url, headers=None, json=None, timeout=None):
            nonlocal captured_payload
            captured_payload = json
            return FakeStreamResponse()

        mock_client.stream.side_effect = fake_stream

        service = OpenRouterService(mock_settings, client=mock_client)
        request = ChatRequest(
            model="openrouter/auto",
            cost_tier=tier,
            messages=[ChatMessage(role="user", content="Tier test")],
        )

        events = [event async for event in service.stream_chat(request)]
        assert len(events) >= 1
        assert captured_payload["model"] == "openrouter/auto"
        assert "plugins" in captured_payload
        assert len(captured_payload["plugins"]) == 1
        plugin = captured_payload["plugins"][0]
        assert plugin["id"] == "auto-router"
        assert plugin["cost_tier"] == tier
        assert "costTier" not in plugin


@pytest.mark.asyncio
async def test_auto_router_session_id_multi_turn_stickiness(mock_settings: Settings) -> None:
    """Verify session_id is serialized in plugin and payload for Auto Router stickiness."""
    captured_payload: dict = {}

    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"model":"anthropic/claude-3.5-sonnet","choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return FakeStreamResponse()

    mock_client.stream.side_effect = fake_stream

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(
        model="openrouter/auto",
        cost_tier="medium",
        session_id="session-user-turn-12345",
        messages=[ChatMessage(role="user", content="Turn 1")],
    )

    events = [event async for event in service.stream_chat(request)]
    assert captured_payload["session_id"] == "session-user-turn-12345"
    assert captured_payload["plugins"][0]["session_id"] == "session-user-turn-12345"
    assert captured_payload["plugins"][0]["cost_tier"] == "medium"
    assert "costTier" not in captured_payload["plugins"][0]

    # Events should also reflect session_id
    done_event = next((e for e in events if e.type == "done"), None)
    assert done_event is not None
    assert done_event.session_id == "session-user-turn-12345"


@pytest.mark.asyncio
async def test_model_reasoning_trace_isolated_from_assistant_content(mock_settings: Settings) -> None:
    """Ensure reasoning traces are emitted as separate reasoning events, never as ordinary content."""
    class FakeReasoningStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            chunk1 = json.dumps({
                "model": "deepseek/deepseek-r1",
                "choices": [{"delta": {"reasoning": "Analyzing problem step 1..."}}],
            })
            chunk2 = json.dumps({
                "model": "deepseek/deepseek-r1",
                "choices": [{"delta": {"content": "The answer is 42."}}],
            })
            yield f"data: {chunk1}"
            yield f"data: {chunk2}"
            yield "data: [DONE]"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.stream.return_value = FakeReasoningStreamResponse()

    service = OpenRouterService(mock_settings, client=mock_client)
    request = ChatRequest(
        model="deepseek/deepseek-r1",
        messages=[ChatMessage(role="user", content="Calculate")],
    )

    events = [event async for event in service.stream_chat(request)]

    reasoning_events = [e for e in events if e.type == "reasoning"]
    token_events = [e for e in events if e.type == "token"]

    assert len(reasoning_events) == 1
    assert reasoning_events[0].reasoning == "Analyzing problem step 1..."
    assert reasoning_events[0].content is None

    assert len(token_events) == 1
    assert token_events[0].content == "The answer is 42."
    assert token_events[0].reasoning is None
