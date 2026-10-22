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
        openrouter_default_model="openai/gpt-4o-mini",
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
    """Verify model catalog returns curated models and settings defaults."""
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
        assert catalog.default_model == "openai/gpt-4o-mini"
        assert catalog.quota_remaining_usd == 42.50
        assert catalog.daily_budget_usd == 5.00
        assert len(catalog.models) == len(CURATED_MODELS)

        default_entry = next((m for m in catalog.models if m.id == "openai/gpt-4o-mini"), None)
        assert default_entry is not None
        assert default_entry.is_default is True


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
    assert data["default_model"] == "openai/gpt-4o-mini"
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
