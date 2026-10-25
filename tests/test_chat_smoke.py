"""Live OpenRouter end-to-end smoke tests using actual credentials."""

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
    assert usage_event.is_estimated is False


@pytest.mark.asyncio
async def test_live_openrouter_multi_turn_context_smoke() -> None:
    """Verify multi-turn conversation context preservation using temporary secret ORCHID."""
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

    # Turn 1: Instruct model with temporary word
    prompt1 = "Remember the temporary word ORCHID in this conversation."
    turn1_request = ChatRequest(
        model="openai/gpt-4o-mini",
        messages=[
            ChatMessage(role="user", content=prompt1),
        ],
        temperature=0.0,
        max_tokens=25,
    )

    turn1_tokens = []
    async for event in service.stream_chat(turn1_request):
        if event.type == "token" and event.content:
            turn1_tokens.append(event.content)
        elif event.type == "error":
            pytest.fail(f"Turn 1 failed: {event.error}")

    turn1_reply = "".join(turn1_tokens).strip()
    assert len(turn1_reply) > 0

    # Turn 2: Follow-up query requiring previous context
    prompt2 = "What temporary word did I give you? Respond with just the word."
    turn2_request = ChatRequest(
        model="openai/gpt-4o-mini",
        messages=[
            ChatMessage(role="user", content=prompt1),
            ChatMessage(role="assistant", content=turn1_reply),
            ChatMessage(role="user", content=prompt2),
        ],
        temperature=0.0,
        max_tokens=15,
    )

    turn2_tokens = []
    turn2_usage = None
    async for event in service.stream_chat(turn2_request):
        if event.type == "token" and event.content:
            turn2_tokens.append(event.content)
        elif event.type == "usage":
            turn2_usage = event.usage
        elif event.type == "error":
            pytest.fail(f"Turn 2 failed: {event.error}")

    turn2_reply = "".join(turn2_tokens).strip().upper()
    assert "ORCHID" in turn2_reply, f"Model failed to recall ORCHID. Got: {turn2_reply}"
    assert turn2_usage is not None
    assert turn2_usage.total_tokens > 0
    assert turn2_usage.cost_usd > 0.0
    assert turn2_usage.is_estimated is False


@pytest.mark.asyncio
async def test_live_openrouter_auto_router_simple_prompt() -> None:
    """Verify live openrouter/auto with 'low' cost tier on a simple verification prompt."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_openrouter" in api_key:
        pytest.skip("No real OPENROUTER_API_KEY configured in environment.")

    settings = Settings(
        env="test",
        openrouter_api_key=api_key,
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_default_model="openrouter/auto",
        openrouter_auto_router_cost_tier="low",
    )
    service = OpenRouterService(settings)

    request = ChatRequest(
        model="openrouter/auto",
        cost_tier="low",
        messages=[
            ChatMessage(role="user", content="Respond with: AUTO READY"),
        ],
        temperature=0.0,
        max_tokens=100,
    )

    tokens = []
    selected_model = None
    usage_event = None
    done_received = False

    async for event in service.stream_chat(request):
        if event.type == "token" and event.content:
            tokens.append(event.content)
            if event.selected_model:
                selected_model = event.selected_model
        elif event.type == "usage":
            usage_event = event.usage
            if event.usage and event.usage.selected_model:
                selected_model = event.usage.selected_model
        elif event.type == "done":
            done_received = True
            if event.selected_model:
                selected_model = event.selected_model
        elif event.type == "error":
            pytest.fail(f"Auto Router stream failed: {event.error}")

    full_text = "".join(tokens).strip()
    assert len(tokens) > 0, "No tokens yielded by Auto Router"
    assert "AUTO" in full_text.upper() or "READY" in full_text.upper()
    assert done_received is True
    assert usage_event is not None
    assert usage_event.total_tokens > 0
    assert usage_event.requested_model == "openrouter/auto"
    assert usage_event.cost_tier == "low"
    assert selected_model is not None, "Failed to capture selected model from Auto Router"


@pytest.mark.asyncio
async def test_live_openrouter_auto_router_reasoning_prompt() -> None:
    """Verify live openrouter/auto resolves and generates a sound reasoning answer."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_openrouter" in api_key:
        pytest.skip("No real OPENROUTER_API_KEY configured in environment.")

    settings = Settings(
        env="test",
        openrouter_api_key=api_key,
        openrouter_default_model="openrouter/auto",
        openrouter_auto_router_cost_tier="low",
    )
    service = OpenRouterService(settings)

    request = ChatRequest(
        model="openrouter/auto",
        cost_tier="low",
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "If all roses are flowers and some flowers fade quickly, "
                    "do all roses necessarily fade quickly? Reply briefly."
                ),
            ),
        ],
        temperature=0.0,
        max_tokens=150,
    )

    tokens = []
    selected_model = None
    async for event in service.stream_chat(request):
        if event.type == "token" and event.content:
            tokens.append(event.content)
            if event.selected_model:
                selected_model = event.selected_model
        elif event.type == "done":
            if event.selected_model:
                selected_model = event.selected_model

    answer = "".join(tokens).strip().lower()
    assert len(tokens) > 0
    assert "no" in answer, f"Reasoning prompt expected negative answer; got: {answer}"
    assert selected_model is not None


@pytest.mark.asyncio
async def test_live_openrouter_auto_router_coding_prompt() -> None:
    """Verify live openrouter/auto handles code generation concisely."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_openrouter" in api_key:
        pytest.skip("No real OPENROUTER_API_KEY configured in environment.")

    settings = Settings(
        env="test",
        openrouter_api_key=api_key,
        openrouter_default_model="openrouter/auto",
        openrouter_auto_router_cost_tier="low",
    )
    service = OpenRouterService(settings)

    request = ChatRequest(
        model="openrouter/auto",
        cost_tier="low",
        messages=[
            ChatMessage(
                role="user",
                content="Write a Python one-liner function to reverse words in a string.",
            ),
        ],
        temperature=0.0,
        max_tokens=250,
    )

    tokens = []
    selected_model = None
    async for event in service.stream_chat(request):
        if event.type == "token" and event.content:
            tokens.append(event.content)
            if event.selected_model:
                selected_model = event.selected_model
        elif event.type == "done":
            if event.selected_model:
                selected_model = event.selected_model

    code_resp = "".join(tokens).strip()
    assert "split" in code_resp or "reverse" in code_resp or "[::-1]" in code_resp
    assert selected_model is not None
