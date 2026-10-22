"""Live OpenRouter end-to-end smoke test using actual credentials."""

import os

import pytest
from dotenv import load_dotenv

from javed.config import Settings
from javed.schemas.chat import ChatMessage, ChatRequest
from javed.services.openrouter import OpenRouterService

load_dotenv()


@pytest.mark.asyncio
async def test_live_openrouter_streaming_smoke() -> None:
    """Perform real network streaming call to OpenRouter and verify token yield."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_openrouter" in api_key:
        pytest.skip("No real OPENROUTER_API_KEY configured in environment.")

    settings = Settings(
        env="test",
        openrouter_api_key=api_key,
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_default_model=os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4o-mini"),
    )
    service = OpenRouterService(settings)

    request = ChatRequest(
        model="openai/gpt-4o-mini",
        messages=[
            ChatMessage(role="user", content="Respond with exactly two words: 'Javed Ready'"),
        ],
        temperature=0.0,
        max_tokens=10,
    )

    tokens = []
    usage_event = None
    done_received = False

    async for event in service.stream_chat(request):
        if event.type == "token" and event.content:
            tokens.append(event.content)
        elif event.type == "usage":
            usage_event = event.usage
        elif event.type == "done":
            done_received = True
        elif event.type == "error":
            pytest.fail(f"Live OpenRouter stream emitted error: {event.error}")

    full_response = "".join(tokens).strip()
    assert len(tokens) > 0, "No tokens yielded by OpenRouter live stream"
    assert "Javed" in full_response or "Ready" in full_response
    assert done_received is True, "Stream did not emit done event"
    assert usage_event is not None, "Stream did not emit usage telemetry"
    assert usage_event.total_tokens > 0
    assert usage_event.cost_usd >= 0.0
