"""Tests for Model Tool-Calling Capability Discovery and Fallback Routing (BRICK-005 Phase 9).

Verifies:
1. OpenRouter catalog capability discovery accurately detects tool-calling support
2. Fallback to a verified tool-capable model occurs when an incompatible model is requested
3. Section 7 security guard strictly prohibits unauthorized OpenRouter-hosted server plugins
"""

from unittest.mock import MagicMock

import pytest

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.schemas.agent import AgentStreamRequest
from javed.schemas.chat import ModelInfo
from javed.services.openrouter import OpenRouterService


def test_openrouter_tool_support_discovery():
    """Verify tool support detection on curated and remote model catalogs."""
    settings = Settings(openrouter_api_key="test-key")
    service = OpenRouterService(settings=settings)

    # Known curated tool-capable models
    assert service.supports_tools("openai/gpt-4o-mini") is True
    assert service.supports_tools("google/gemini-2.5-flash") is True
    assert service.supports_tools("openrouter/auto") is True

    # Check model info parameters
    info = service.get_model_info("openai/gpt-4o-mini")
    assert info is not None
    assert info.supports_tools is True
    assert "tools" in info.supported_parameters


def test_openrouter_unsupported_model_detection():
    """Verify detection when model does not support tools."""
    settings = Settings(openrouter_api_key="test-key")
    service = OpenRouterService(settings=settings)
    # Inject a non-tool model into cached models
    service._models_cache = [
        ModelInfo(
            id="text-only/model-v1",
            name="Text Only Model",
            provider="custom",
            context_length=8192,
            pricing_prompt=0.0,
            pricing_completion=0.0,
            description="Text only model",
            supports_tools=False,
            supported_parameters=["temperature", "max_tokens"],
            cost_tier="free",
        )
    ]
    service._catalog_loaded = True

    assert service.supports_tools("text-only/model-v1") is False


def test_get_best_tool_capable_model():
    """Verify selection of optimal tool-capable model by cost tier."""
    settings = Settings(openrouter_api_key="test-key")
    service = OpenRouterService(settings=settings)
    # By default, gpt-4o-mini or gemini flash should be returned for low cost tier
    best_low = service.get_best_tool_capable_model("low")
    assert service.supports_tools(best_low) is True

    best_free = service.get_best_tool_capable_model("free")
    assert service.supports_tools(best_free) is True


def test_create_model_fallback_when_unsupported():
    """Verify AgentRuntimeManager falls back safely when tool-incompatible model requested."""
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_default_model="text-only/model-v1",
    )
    service = OpenRouterService(settings=settings)
    service._models_cache = [
        ModelInfo(
            id="text-only/model-v1",
            name="Text Only Model",
            provider="custom",
            context_length=8192,
            pricing_prompt=0.0,
            pricing_completion=0.0,
            description="Text only model",
            supports_tools=False,
            supported_parameters=["temperature"],
            cost_tier="free",
        ),
        ModelInfo(
            id="openai/gpt-4o-mini",
            name="GPT-4o Mini",
            provider="openai",
            context_length=128000,
            pricing_prompt=0.00015,
            pricing_completion=0.0006,
            description="GPT-4o Mini",
            supports_tools=True,
            supported_parameters=["tools", "tool_choice"],
            cost_tier="low",
        ),
    ]
    service._catalog_loaded = True

    mock_gateway = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "time__get_current_time"
    mock_gateway.get_executable_tools.return_value = [mock_tool]

    runtime = AgentRuntimeManager(
        settings=settings,
        openrouter_service=service,
        mcp_gateway=mock_gateway,
    )

    req = AgentStreamRequest(
        thread_id="test_thread_fallback",
        message="What is the time?",
        model="text-only/model-v1",
    )

    model = runtime.create_model(req)
    # The effective model should have fallen back to a tool-capable model
    assert model._effective_model_name != "text-only/model-v1"
    assert model._fallback_reason is not None
    assert "does not support tool calling" in model._fallback_reason


def test_section7_server_plugin_prohibition():
    """Verify OpenRouter-hosted server tools (web, code interpreter) are strictly prohibited."""
    settings = Settings(openrouter_api_key="test-key")
    runtime = AgentRuntimeManager(settings=settings)

    # Attempting to use a server-tool plugin like 'web' or 'code' must raise PermissionError
    req = AgentStreamRequest(
        thread_id="test_thread_prohibited",
        message="Search the web",
        model="openai/gpt-4o-mini",
        plugins=[{"id": "web"}],
    )

    with pytest.raises(PermissionError) as exc_info:
        runtime.create_model(req)

    assert "prohibited in BRICK-005" in str(exc_info.value)
    assert "Only user-defined local MCP gateway tools are authorized" in str(exc_info.value)
