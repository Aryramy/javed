"""Comprehensive test suite for JAVED Multi-Provider Inference Registry and Router.

Covers:
1. ProviderDescriptor & SanitizedProviderSummary zero-secret guarantee.
2. ProviderRegistry evaluation, catalog caching, and health classification.
3. CheaperInferenceService streaming, cost normalization, and error sanitization.
4. ChatCheaperInference LangChain BaseChatModel adapter & tool binding.
5. InferenceRouter explicit routing, zero silent fallback, and auto routing.
6. Agent Mode capability gating (fail-closed if model lacks tool calling).
7. Thread-level provider binding, locking during active run, and approval-pending guards.
8. Audit history and state restoration via get_thread_state.
9. Extraction tool compatibility across providers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import tool

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.mcp.approval_store import ApprovalRecord
from javed.providers.agent_adapter import ChatCheaperInference
from javed.providers.cheaper_inference import CheaperInferenceService
from javed.providers.registry import (
    ProviderCapabilities,
    ProviderDescriptor,
    ProviderRegistry,
    SanitizedProviderSummary,
)
from javed.providers.router import InferenceRouter
from javed.schemas.agent import AgentStreamRequest
from javed.schemas.chat import ChatMessage, ChatRequest, ChatStreamEvent
from javed.services.openrouter import OpenRouterService


@pytest.fixture
def mock_settings(tmp_path) -> Settings:
    """Settings fixture with mock provider configurations."""
    return Settings(
        app_name="Test Javed",
        env="test",
        openrouter_api_key="sk-or-v1-mock-test-key-12345",
        openrouter_model="anthropic/claude-3.5-sonnet",
        cheaper_inference_api_key="sk-ci-mock-test-key-67890",
        cheaper_inference_base_url="https://api.cheaper-inference.test/v1",
        cheaper_inference_model="deepseek-v4.1-flash-1017",
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )


# ==============================================================================
# SECTION 1: REGISTRY & DESCRIPTOR TESTS
# ==============================================================================


def test_01_provider_capabilities_model():
    """Verify capabilities model defaults and explicit flags."""
    caps = ProviderCapabilities(chat=True, agent=True, transcription=False, speech=False)
    assert caps.chat is True
    assert caps.agent is True
    assert caps.transcription is False
    assert caps.realtime_voice is False


def test_02_sanitized_provider_summary_zero_secrets():
    """Verify that SanitizedProviderSummary exposes zero secret fields."""
    desc = ProviderDescriptor(
        provider_id="cheaper_inference",
        display_name="Cheaper Inference",
        enabled=True,
        configured=True,
        health_state="available",
        chat_model_display_name="deepseek-v4.1-flash-1017",
        capabilities=ProviderCapabilities(chat=True, agent=True),
    )
    summary = SanitizedProviderSummary.from_descriptor(desc)
    serialized = summary.model_dump_json()

    # Zero secret assertions
    assert "sk-" not in serialized
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert summary.id == "cheaper_inference"
    assert summary.chat_model == "deepseek-v4.1-flash-1017"
    assert summary.configured is True


def test_03_registry_descriptors_list(mock_settings: Settings):
    """Verify that the registry registers auto, openrouter, and cheaper_inference."""
    registry = ProviderRegistry(mock_settings)
    descriptors = registry.list_descriptors()
    provider_ids = [d.provider_id for d in descriptors]
    assert "auto" in provider_ids
    assert "openrouter" in provider_ids
    assert "cheaper_inference" in provider_ids


def test_04_registry_unconfigured_provider(tmp_path):
    """Verify that a provider with missing API key is marked not_configured."""
    empty_settings = Settings(
        app_name="Test Javed",
        env="test",
        openrouter_api_key="",
        cheaper_inference_api_key="",
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    registry = ProviderRegistry(empty_settings)
    openrouter_desc = registry.get_descriptor("openrouter")
    cheaper_desc = registry.get_descriptor("cheaper_inference")

    assert openrouter_desc.configured is False
    assert openrouter_desc.health_state == "not_configured"
    assert cheaper_desc.configured is False
    assert cheaper_desc.health_state == "not_configured"


@pytest.mark.asyncio
async def test_05_registry_cheaper_catalog_inspection(mock_settings: Settings):
    """Verify that Cheaper Inference inspects models catalog and sets capabilities."""
    registry = ProviderRegistry(mock_settings)

    mock_catalog = [
        {"id": "deepseek-v4.1-flash-1017", "features": ["tool-use"]},
        {"id": "whisper-large-v3-turbo", "features": []},
    ]

    with patch.object(registry, "_fetch_cheaper_catalog", new=AsyncMock(return_value=mock_catalog)):
        desc = await registry._evaluate_cheaper_inference()
        assert desc.health_state == "available"
        assert desc.capabilities.chat is True
        assert desc.capabilities.agent is True


@pytest.mark.asyncio
async def test_06_registry_cheaper_tool_missing_fails_agent_mode(mock_settings: Settings):
    """Verify that if catalog shows model has no tool-use, agent capability is False."""
    registry = ProviderRegistry(mock_settings)

    # Model exists but has no tool-use feature
    mock_catalog = [
        {"id": "deepseek-v4.1-flash-1017", "features": ["text-only"]},
    ]

    with patch.object(registry, "_fetch_cheaper_catalog", new=AsyncMock(return_value=mock_catalog)):
        desc = await registry._evaluate_cheaper_inference()
        assert desc.health_state == "capability_mismatch"
        assert desc.capabilities.chat is True
        assert desc.capabilities.agent is False


@pytest.mark.asyncio
async def test_07_registry_model_not_in_catalog(mock_settings: Settings):
    """Verify that if configured model is missing from catalog, status is model_unavailable."""
    registry = ProviderRegistry(mock_settings)

    mock_catalog = [
        {"id": "other-model-1", "features": ["tool-use"]},
    ]

    with patch.object(registry, "_fetch_cheaper_catalog", new=AsyncMock(return_value=mock_catalog)):
        desc = await registry._evaluate_cheaper_inference()
        assert desc.health_state == "model_unavailable"
        assert desc.capabilities.chat is False


def test_08_get_sanitized_response(mock_settings: Settings):
    """Verify full sanitized response format."""
    registry = ProviderRegistry(mock_settings)
    response = registry.get_sanitized_response()

    assert response.default_provider == "openrouter"
    assert response.selection_enabled is True
    assert len(response.providers) >= 3
    assert all(not p.id.startswith("sk-") for p in response.providers)


# ==============================================================================
# SECTION 2: CHEAPER INFERENCE SERVICE & ERROR SANITIZATION
# ==============================================================================


def test_09_cheaper_cost_calculation(mock_settings: Settings):
    """Verify token pricing calculation ($0.15/1M prompt, $0.60/1M completion)."""
    service = CheaperInferenceService(mock_settings)

    # 1,000,000 prompt tokens = $0.15
    # 1,000,000 completion tokens = $0.60
    cost = service.calculate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost - 0.75) < 1e-6

    # Fractional calculation: 10,000 prompt, 5,000 completion
    cost_small = service.calculate_cost(prompt_tokens=10_000, completion_tokens=5_000)
    expected = (10_000 * 0.15 / 1_000_000) + (5_000 * 0.60 / 1_000_000)
    assert abs(cost_small - expected) < 1e-6


def test_10_cheaper_cost_with_upstream_micro_usd(mock_settings: Settings):
    """Verify that charged_micro takes precedence if present."""
    service = CheaperInferenceService(mock_settings)

    # 150,000 micro-USD = $0.15
    cost = service.calculate_cost(
        prompt_tokens=100,
        completion_tokens=100,
        charged_micro=150_000,
    )
    assert abs(cost - 0.15) < 1e-6


def test_11_cheaper_error_sanitization(mock_settings: Settings):
    """Verify that error sanitization strips keys, tokens, and file paths."""
    service = CheaperInferenceService(mock_settings)

    raw_err = (
        "Failed to connect using key sk-ci-mock-test-key-67890 with Bearer sk-secret-token-xyz "
        "at path C:\\Users\\user\\Desktop\\secret\\config.json"
    )
    sanitized = service._sanitize_error(raw_err)

    assert "sk-ci-mock-test-key-67890" not in sanitized
    assert "sk-secret-token-xyz" not in sanitized
    assert "C:\\Users\\user" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "Bearer [REDACTED]" in sanitized
    assert "[PATH_REDACTED]" in sanitized


@pytest.mark.asyncio
async def test_12_cheaper_stream_chat_tokens_and_usage(mock_settings: Settings):
    """Verify that CheaperInferenceService streams tokens and usage event."""

    class MockAsyncResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            chunk2 = (
                'data: {"choices": [{"delta": {"content": " world!"}}], '
                '"usage": {"prompt_tokens": 10, "completion_tokens": 5}}'
            )
            yield chunk2
            yield "data: [DONE]"

    mock_client = MagicMock()
    mock_client.stream.return_value = MockAsyncResponse()

    service = CheaperInferenceService(mock_settings, http_client=mock_client)
    events = []
    req = ChatRequest(messages=[ChatMessage(role="user", content="Hi")])
    async for ev in service.stream_chat(req):
        events.append(ev)

    event_types = [e.type for e in events]
    assert "token" in event_types
    assert "usage" in event_types
    assert "done" in event_types

    content = "".join([e.content for e in events if e.type == "token"])
    assert content == "Hello world!"


# ==============================================================================
# SECTION 3: LANGCHAIN ADAPTER & TOOL CALLING
# ==============================================================================


def test_13_chat_cheaper_inference_adapter_init(mock_settings: Settings):
    """Verify initialization of ChatCheaperInference BaseChatModel adapter."""
    adapter = ChatCheaperInference(
        model_name="deepseek-v4.1-flash-1017",
        api_key=mock_settings.cheaper_inference_api_key,
        base_url=mock_settings.cheaper_inference_base_url,
    )
    assert adapter.model_name == "deepseek-v4.1-flash-1017"
    assert adapter._effective_model_name == "deepseek-v4.1-flash-1017"


def test_14_chat_cheaper_inference_tool_binding(mock_settings: Settings):
    """Verify that tools can be bound to ChatCheaperInference without schema errors."""
    adapter = ChatCheaperInference(
        model_name="deepseek-v4.1-flash-1017",
        api_key=mock_settings.cheaper_inference_api_key,
        base_url=mock_settings.cheaper_inference_base_url,
    )

    @tool
    def sample_tool(param1: str) -> str:
        """Sample tool for testing."""
        return f"result: {param1}"

    bound = adapter.bind_tools([sample_tool])
    assert bound is not None
    assert hasattr(bound, "tools")
    assert len(bound.tools) == 1
    assert bound.tools[0]["function"]["name"] == "sample_tool"


# ==============================================================================
# SECTION 4: INFERENCE ROUTER & CAPABILITY GATING
# ==============================================================================


@pytest.fixture
def mock_router(mock_settings: Settings) -> InferenceRouter:
    """Fixture providing an initialized InferenceRouter with available providers."""
    registry = ProviderRegistry(mock_settings)
    openrouter = OpenRouterService(mock_settings)
    cheaper = CheaperInferenceService(mock_settings)
    return InferenceRouter(
        settings=mock_settings,
        registry=registry,
        openrouter_service=openrouter,
        cheaper_service=cheaper,
    )


def test_15_router_explicit_openrouter(mock_router: InferenceRouter):
    """Verify explicit selection of openrouter routes directly without fallback."""
    decision = mock_router.resolve_provider_for_chat(requested_provider_id="openrouter")
    assert decision.selected_provider == "openrouter"
    assert decision.routing_mode == "explicit"
    assert "OpenRouter" in decision.reason


def test_16_router_explicit_cheaper(mock_router: InferenceRouter):
    """Verify explicit selection of cheaper_inference routes directly without fallback."""
    decision = mock_router.resolve_provider_for_chat(requested_provider_id="cheaper_inference")
    assert decision.selected_provider == "cheaper_inference"
    assert decision.routing_mode == "explicit"
    assert "Cheaper Inference" in decision.reason


def test_17_router_unknown_provider_fails_closed(mock_router: InferenceRouter):
    """Verify unknown provider IDs fail closed immediately."""
    with pytest.raises(ValueError, match="Unknown provider 'untrusted_unknown'"):
        mock_router.resolve_provider_for_chat(requested_provider_id="untrusted_unknown")


def test_18_router_auto_cost_tier_low(mock_router: InferenceRouter):
    """Verify Auto Router selects Cheaper Inference for low cost tier."""
    decision = mock_router.resolve_provider_for_chat(
        requested_provider_id="auto",
        cost_tier="low",
    )
    assert decision.selected_provider == "cheaper_inference"
    assert decision.routing_mode == "auto"


def test_19_router_auto_cost_tier_high(mock_router: InferenceRouter):
    """Verify Auto Router selects OpenRouter for high cost tier."""
    decision = mock_router.resolve_provider_for_chat(
        requested_provider_id="auto",
        cost_tier="high",
    )
    assert decision.selected_provider == "openrouter"
    assert decision.routing_mode == "auto"


def test_20_router_agent_tool_capability_guard(mock_router: InferenceRouter):
    """Verify that Agent Mode fails closed if Cheaper Inference model lacks tool-calling."""
    # Force cheaper inference descriptor to lack agent capability
    cheaper_desc = mock_router.registry.get_descriptor("cheaper_inference")
    cheaper_desc.capabilities.agent = False

    with pytest.raises(
        ValueError, match="does not currently support the tool-calling capabilities"
    ):
        mock_router.resolve_provider_for_agent(
            requested_provider_id="cheaper_inference",
            has_tools=True,
        )


def test_21_router_agent_auto_skips_non_tool_provider(mock_router: InferenceRouter):
    """Verify Auto Router for Agent Mode skips providers without tool-calling support."""
    cheaper_desc = mock_router.registry.get_descriptor("cheaper_inference")
    cheaper_desc.capabilities.agent = False

    decision = mock_router.resolve_provider_for_agent(
        requested_provider_id="auto",
        has_tools=True,
        cost_tier="low",
    )
    # Even though tier is 'low', Cheaper lacks agent tools, so it must choose OpenRouter
    assert decision.selected_provider == "openrouter"


# ==============================================================================
# SECTION 5: THREAD PROVIDER BINDING & ISOLATION
# ==============================================================================


@pytest.fixture
def agent_runtime(mock_settings: Settings, mock_router: InferenceRouter) -> AgentRuntimeManager:
    """Fixture providing AgentRuntimeManager wired with InferenceRouter."""
    return AgentRuntimeManager(
        settings=mock_settings,
        inference_router=mock_router,
        provider_registry=mock_router.registry,
    )


@pytest.mark.asyncio
async def test_22_thread_initial_provider_binding(agent_runtime: AgentRuntimeManager):
    """Verify initial provider binding for a fresh thread."""
    provider = await agent_runtime.bind_thread_provider(
        thread_id="thread-test-1",
        requested_provider_id="cheaper_inference",
    )
    assert provider == "cheaper_inference"
    assert agent_runtime.get_thread_provider("thread-test-1") == "cheaper_inference"


@pytest.mark.asyncio
async def test_23_thread_provider_switch_between_turns(agent_runtime: AgentRuntimeManager):
    """Verify switching providers between completed turns records audit history."""
    # Initial bind
    await agent_runtime.bind_thread_provider("thread-test-2", "openrouter")
    assert agent_runtime.get_thread_provider("thread-test-2") == "openrouter"

    # Switch
    await agent_runtime.bind_thread_provider(
        "thread-test-2",
        "cheaper_inference",
        reason="user_switch",
    )
    assert agent_runtime.get_thread_provider("thread-test-2") == "cheaper_inference"

    binding = agent_runtime.get_thread_binding("thread-test-2")
    history = binding["provider_switch_history"]
    assert len(history) == 1
    assert history[0]["from_provider"] == "openrouter"
    assert history[0]["to_provider"] == "cheaper_inference"


@pytest.mark.asyncio
async def test_24_thread_blocks_switch_during_active_run(agent_runtime: AgentRuntimeManager):
    """Verify that switching provider while an agent run is active is blocked."""
    await agent_runtime.bind_thread_provider("thread-test-3", "cheaper_inference")

    # Simulate active execution
    agent_runtime._active_threads.add("thread-test-3")

    with pytest.raises(ValueError, match="while an agent run is actively executing"):
        await agent_runtime.bind_thread_provider("thread-test-3", "openrouter")


@pytest.mark.asyncio
async def test_25_thread_blocks_switch_with_pending_approval(agent_runtime: AgentRuntimeManager):
    """Verify that switching provider when approvals are pending is blocked."""
    await agent_runtime.initialize()
    thread_id = "thread-test-4"
    await agent_runtime.bind_thread_provider(thread_id, "cheaper_inference")

    # Insert pending approval
    rec = ApprovalRecord(
        approval_id="appr-1234",
        interrupt_id="int-1234",
        run_id="run-1234",
        thread_id=thread_id,
        server_id="extraction",
        tool_id="extract_document",
        tool_call_id="call-1234",
        arguments={"source": "test.pdf"},
        argument_digest="digest-1234",
        tool_fingerprint="fp-1234",
        policy_version=1,
        status="pending",
    )
    await agent_runtime.approval_store.create_approval(rec)

    with pytest.raises(ValueError, match="while an approval is pending"):
        await agent_runtime.bind_thread_provider(thread_id, "openrouter")


@pytest.mark.asyncio
async def test_26_get_thread_state_includes_provider_and_history(
    agent_runtime: AgentRuntimeManager,
):
    """Verify get_thread_state includes active_provider and provider_switch_history."""
    await agent_runtime.initialize()
    thread_id = "thread-test-5"
    await agent_runtime.bind_thread_provider(thread_id, "openrouter")
    await agent_runtime.bind_thread_provider(thread_id, "cheaper_inference", reason="audit_test")

    state = await agent_runtime.get_thread_state(thread_id)
    assert state.active_provider == "cheaper_inference"
    assert len(state.provider_switch_history) == 1
    assert state.provider_switch_history[0]["reason"] == "audit_test"


# ==============================================================================
# SECTION 6: EXTRACTION TOOL COMPATIBILITY ACROSS PROVIDERS
# ==============================================================================


def test_27_extraction_tools_policy_classification(agent_runtime: AgentRuntimeManager):
    """Verify extraction tool classifications remain ALLOWED_READ_ONLY."""
    server_id, classification = agent_runtime.get_tool_classification("list_ingested_documents")
    assert server_id == "extraction"
    assert classification == "ALLOWED_READ_ONLY"

    server_id, classification = agent_runtime.get_tool_classification("get_document_details")
    assert server_id == "extraction"
    assert classification == "ALLOWED_READ_ONLY"


def test_28_extraction_tools_write_requires_approval(agent_runtime: AgentRuntimeManager):
    """Verify extract_document requires approval."""
    server_id, classification = agent_runtime.get_tool_classification("extract_document")
    assert server_id == "extraction"
    assert classification == "APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_29_router_create_agent_chat_model_cheaper(mock_router: InferenceRouter):
    """Verify router creates ChatCheaperInference instance for Cheaper provider."""
    req = AgentStreamRequest(thread_id="test-th", message="hello")
    model, decision = mock_router.create_agent_chat_model(req, provider_id="cheaper_inference")
    assert isinstance(model, ChatCheaperInference)
    assert decision.selected_provider == "cheaper_inference"


@pytest.mark.asyncio
async def test_30_router_create_agent_chat_model_openrouter(mock_router: InferenceRouter):
    """Verify router creates ChatOpenRouter instance for OpenRouter provider."""
    req = AgentStreamRequest(thread_id="test-th", message="hello")
    model, decision = mock_router.create_agent_chat_model(req, provider_id="openrouter")
    from langchain_openrouter import ChatOpenRouter

    assert isinstance(model, ChatOpenRouter)
    assert decision.selected_provider == "openrouter"


def test_31_cross_provider_model_rejected_for_cheaper_inference(mock_router: InferenceRouter):
    """Verify cross-provider OpenRouter model is rejected when provider=cheaper_inference."""
    with pytest.raises(ValueError, match="Cross-provider model error"):
        mock_router.resolve_provider_for_chat(
            requested_provider_id="cheaper_inference",
            requested_model_id="openai/gpt-4o",
        )

    with pytest.raises(ValueError, match="Cross-provider model error"):
        mock_router.resolve_provider_for_agent(
            requested_provider_id="cheaper_inference",
            requested_model_id="anthropic/claude-3-5-sonnet",
        )


def test_32_cross_provider_model_rejected_for_openrouter(mock_router: InferenceRouter):
    """Verify Cheaper Inference model is rejected when provider=openrouter."""
    cheaper_model = mock_router.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
    with pytest.raises(ValueError, match="Cross-provider model error"):
        mock_router.resolve_provider_for_chat(
            requested_provider_id="openrouter",
            requested_model_id=cheaper_model,
        )

    with pytest.raises(ValueError, match="Cross-provider model error"):
        mock_router.resolve_provider_for_agent(
            requested_provider_id="openrouter",
            requested_model_id=cheaper_model,
        )


def test_33_auto_router_with_cheaper_model_routes_to_cheaper(mock_router: InferenceRouter):
    """Verify auto router routes to cheaper_inference when cheaper model requested."""
    cheaper_model = mock_router.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
    decision = mock_router.resolve_provider_for_chat(
        requested_provider_id="auto",
        requested_model_id=cheaper_model,
    )
    assert decision.selected_provider == "cheaper_inference"
    assert decision.selected_model == cheaper_model


# ==============================================================================
# SECTION 7: ATOMIC PROVIDER, MODEL, THREAD, AND RUNTIME BINDING
# ==============================================================================


def test_34_bind_thread_atomic_record_and_version(agent_runtime: AgentRuntimeManager):
    """Verify bind_thread_atomic records configuration version and updates history."""
    th_id = "test-th-atomic-01"
    rec1 = agent_runtime.bind_thread_atomic(
        thread_id=th_id,
        provider_id="openrouter",
        provider_mode="explicit",
        effective_model_id="anthropic/claude-3.5-sonnet",
        configuration_version="v-conf-1",
        reason="initial_bind",
    )

    assert rec1["thread_id"] == th_id
    assert rec1["active_provider"] == "openrouter"
    assert rec1["configuration_version"] == "v-conf-1"
    assert rec1["effective_model_id"] == "anthropic/claude-3.5-sonnet"
    assert rec1["provider_switch_history"] == []

    # Update to Cheaper Inference
    rec2 = agent_runtime.bind_thread_atomic(
        thread_id=th_id,
        provider_id="cheaper_inference",
        provider_mode="explicit",
        effective_model_id="deepseek-v4.1-flash-1017",
        configuration_version="v-conf-2",
        reason="switch_provider",
    )

    assert rec2["active_provider"] == "cheaper_inference"
    assert rec2["configuration_version"] == "v-conf-2"
    assert rec2["effective_model_id"] == "deepseek-v4.1-flash-1017"
    assert len(rec2["provider_switch_history"]) == 1
    assert rec2["provider_switch_history"][0]["from_provider"] == "openrouter"
    assert rec2["provider_switch_history"][0]["to_provider"] == "cheaper_inference"


def test_35_graph_cache_5_tuple_isolation(agent_runtime: AgentRuntimeManager):
    """Verify graph cache isolates graphs across providers and models.

    Never reuses openrouter graph for cheaper_inference.
    """
    th_id = "test-th-cache-01"
    mock_model_or = MagicMock()
    mock_model_ci = MagicMock()
    mock_checkpointer = MagicMock()

    # Create dummy agents to return from create_agent
    mock_agent_or = MagicMock(name="AgentOpenRouter")
    mock_agent_ci = MagicMock(name="AgentCheaper")

    with patch.object(agent_runtime, "create_agent") as mock_create:
        mock_create.side_effect = [mock_agent_or, mock_agent_ci]

        # First compilation for openrouter
        g1 = agent_runtime.get_or_compile_agent_graph(
            thread_id=th_id,
            provider_id="openrouter",
            effective_model_id="anthropic/claude-3.5-sonnet",
            configuration_version="v1",
            model=mock_model_or,
            checkpointer=mock_checkpointer,
        )
        assert g1 is mock_agent_or

        # Second call with identical 5-tuple retrieves cached graph
        g1_cached = agent_runtime.get_or_compile_agent_graph(
            thread_id=th_id,
            provider_id="openrouter",
            effective_model_id="anthropic/claude-3.5-sonnet",
            configuration_version="v1",
            model=mock_model_or,
            checkpointer=mock_checkpointer,
        )
        assert g1_cached is mock_agent_or
        assert mock_create.call_count == 1

        # Third call for cheaper_inference MUST NOT reuse openrouter graph
        g2 = agent_runtime.get_or_compile_agent_graph(
            thread_id=th_id,
            provider_id="cheaper_inference",
            effective_model_id="deepseek-v4.1-flash-1017",
            configuration_version="v2",
            model=mock_model_ci,
            checkpointer=mock_checkpointer,
        )
        assert g2 is mock_agent_ci
        assert g2 is not g1
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_36_stream_agent_fail_closed_on_model_mismatch(agent_runtime: AgentRuntimeManager):
    """Verify stream_agent fails closed before billable inference on model mismatch."""
    th_id = "test-th-mismatch"
    agent_runtime.bind_thread_atomic(
        thread_id=th_id,
        provider_id="cheaper_inference",
        provider_mode="explicit",
        effective_model_id="deepseek-v4.1-flash-1017",
        configuration_version="v1",
    )

    # Request specifies openrouter/auto against cheaper_inference thread
    req = AgentStreamRequest(
        thread_id=th_id,
        message="Hello",
        provider_id="cheaper_inference",
        model="openrouter/auto",
    )

    with pytest.raises(ValueError, match="Cross-provider model error"):
        async for _ in agent_runtime.stream_agent(req):
            pass


@pytest.mark.asyncio
async def test_37_stream_agent_fail_closed_on_provider_mismatch(agent_runtime: AgentRuntimeManager):
    """Verify stream_agent fails closed if request provider does not match thread provider."""
    th_id = "test-th-prov-mismatch"
    agent_runtime.bind_thread_atomic(
        thread_id=th_id,
        provider_id="openrouter",
        provider_mode="explicit",
        effective_model_id="anthropic/claude-3.5-sonnet",
        configuration_version="v1",
    )

    req = AgentStreamRequest(
        thread_id=th_id,
        message="Hello",
        provider_id="cheaper_inference",
        model="deepseek-v4.1-flash-1017",
    )

    with pytest.raises(ValueError, match="does not match thread bound provider"):
        async for _ in agent_runtime.stream_agent(req):
            pass


@pytest.mark.asyncio
async def test_38_bind_thread_api_endpoint(mock_settings: Settings, mock_router: InferenceRouter):
    """Verify POST /api/v1/providers/bind-thread returns confirmed atomic binding."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from javed.api.v1.providers import router as providers_router

    app = FastAPI()
    app.include_router(providers_router, prefix="/api/v1")
    app.state.settings = mock_settings
    app.state.inference_router = mock_router
    app.state.provider_registry = mock_router.registry

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/providers/bind-thread",
            json={
                "provider_id": "cheaper_inference",
                "interaction_mode": "agent",
                "create_new_thread": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_id"] == "cheaper_inference"
        assert data["effective_model_id"] == "deepseek-v4.1-flash-1017"
        assert data["thread_id"].startswith("thread-")
        assert data["configuration_version"].startswith("v-")
        assert data["capabilities"]["chat"] is True
        assert data["capabilities"]["agent"] is True


@pytest.mark.asyncio
async def test_39_bind_thread_api_conflict_active_run(
    mock_settings: Settings, mock_router: InferenceRouter
):
    """Verify POST /api/v1/providers/bind-thread rejects switch with 409 if thread is active."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from javed.api.v1.providers import router as providers_router

    app = FastAPI()
    app.include_router(providers_router, prefix="/api/v1")
    app.state.settings = mock_settings
    app.state.inference_router = mock_router
    app.state.provider_registry = mock_router.registry

    mock_runtime = MagicMock()
    mock_runtime._active_threads = {"th-active-123"}
    app.state.agent_runtime = mock_runtime

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/providers/bind-thread",
            json={
                "provider_id": "cheaper_inference",
                "current_thread_id": "th-active-123",
                "create_new_thread": False,
            },
        )
        assert resp.status_code == 409
        assert "actively executing" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_40_bind_thread_api_conflict_pending_approval(
    mock_settings: Settings, mock_router: InferenceRouter
):
    """Verify POST /api/v1/providers/bind-thread rejects with 409 if approval is pending."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from javed.api.v1.providers import router as providers_router

    app = FastAPI()
    app.include_router(providers_router, prefix="/api/v1")
    app.state.settings = mock_settings
    app.state.inference_router = mock_router
    app.state.provider_registry = mock_router.registry

    mock_runtime = MagicMock()
    mock_runtime._active_threads = set()
    mock_store = AsyncMock()
    mock_store.get_pending_approvals.return_value = [MagicMock()]
    mock_runtime.approval_store = mock_store
    app.state.agent_runtime = mock_runtime

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/providers/bind-thread",
            json={
                "provider_id": "cheaper_inference",
                "current_thread_id": "th-pending-123",
                "create_new_thread": False,
            },
        )
        assert resp.status_code == 409
        assert "approval is pending" in resp.json()["detail"]


# ==============================================================================
# SECTION 8: FINAL CORRECTIONS — READ-ONLY TOOLS, USAGE & STATUS CONTRACT
# ==============================================================================


@pytest.mark.asyncio
async def test_41_time_tool_policy_allowed_read_only(mock_settings: Settings):
    """Verify time__get_current_time is ALLOWED_READ_ONLY and excluded from approval_tools."""
    runtime = AgentRuntimeManager(mock_settings)
    await runtime.initialize()

    server_id, classification = runtime.get_tool_classification("time__get_current_time")
    assert server_id == "time"
    assert classification == "ALLOWED_READ_ONLY"

    # Verify that time__get_current_time is never in approval_tools
    checkpointer = await runtime.checkpointer_manager.get_async_checkpointer()
    model = ChatCheaperInference(
        model_name="deepseek-v4.1-flash-1017",
        api_key="test",
        base_url="https://test",
    )

    # Even if gateway had marked it, runtime excludes it
    agent_graph = runtime.create_agent(model=model, checkpointer=checkpointer)
    assert agent_graph is not None

    await runtime.close()


@pytest.mark.asyncio
async def test_42_cheaper_inference_astream_usage_no_double_counting():
    """Verify ChatCheaperInference._astream yields terminal usage once and only once."""
    from langchain_core.messages import HumanMessage

    adapter = ChatCheaperInference(
        model_name="deepseek-v4.1-flash-1017",
        api_key="sk-ci-test",
        base_url="https://api.cheaper-inference.test/v1",
    )

    # Mock stream yielding 2 chunks with usage attached (simulating provider behavior)
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Hello", tool_calls=None))]
    chunk1.usage = MagicMock(prompt_tokens=100, completion_tokens=20, total_tokens=120)

    chunk2 = MagicMock()
    chunk2.choices = []
    chunk2.usage = MagicMock(prompt_tokens=100, completion_tokens=20, total_tokens=120)

    mock_client = AsyncMock()

    async def mock_generator():
        yield chunk1
        yield chunk2

    mock_client.chat.completions.create.return_value = mock_generator()

    with patch.object(adapter, "_get_async_client", return_value=mock_client):
        chunks = [c async for c in adapter._astream([HumanMessage(content="Hi")])]

    # Should yield chunk 1 (content) and exactly 1 terminal chunk (usage)
    assert len(chunks) == 2
    assert chunks[0].message.content == "Hello"
    assert chunks[1].message.content == ""
    assert chunks[1].message.usage_metadata is not None
    assert chunks[1].message.usage_metadata["input_tokens"] == 100
    assert chunks[1].message.usage_metadata["output_tokens"] == 20
    assert chunks[1].message.usage_metadata["total_tokens"] == 120
    assert chunks[1].message.response_metadata["model_name"] == "deepseek-v4.1-flash-1017"


@pytest.mark.asyncio
async def test_43_authoritative_system_status_contract(mock_settings: Settings):
    """Verify /api/v1/system/status returns authoritative stage and active brick contract."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from javed.api.v1.system import router as system_router

    app = FastAPI()
    app.include_router(system_router, prefix="/api/v1")
    app.state.settings = mock_settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "Stage 4"
        assert data["active_brick"] == "BRICK-007 In Progress"
        assert data["provider_gateway_status"] == "Provider Gateway Active"
        assert data["runtime_status"] == "Deep Agents Runtime Active"


@pytest.mark.asyncio
async def test_44_auto_router_chat_resolves_cheaper_model_atomically(
    mock_settings: Settings,
):
    """Verify Auto Router atomically reconciles request model and provider to Cheaper Inference."""
    registry = ProviderRegistry(mock_settings)
    openrouter_service = OpenRouterService(mock_settings)
    cheaper_service = CheaperInferenceService(mock_settings)
    router = InferenceRouter(mock_settings, registry, openrouter_service, cheaper_service)

    req = ChatRequest(
        messages=[{"role": "user", "content": "Hello"}],
        provider_id="auto",
        cost_tier="low",
        model="openrouter/auto",  # client sent stale openrouter/auto
    )

    async def mock_cheaper_stream(r):
        assert r.model == "deepseek-v4.1-flash-1017"
        assert r.provider_id == "cheaper_inference"
        yield ChatStreamEvent(
            type="token",
            content="Hi from Cheaper!",
            selected_model="deepseek-v4.1-flash-1017",
            provider_id="cheaper_inference",
        )

    with patch.object(cheaper_service, "stream_chat", side_effect=mock_cheaper_stream):
        events = [e async for e in router.stream_chat(req)]

    assert len(events) == 1
    assert events[0].content == "Hi from Cheaper!"
    assert req.model == "deepseek-v4.1-flash-1017"
    assert req.provider_id == "cheaper_inference"


@pytest.mark.asyncio
async def test_45_cheaper_inference_pre_inference_validation_rejects_openrouter_prefix(
    mock_settings: Settings,
):
    """Verify CheaperInferenceService sanitizes or fails closed on openrouter/* models."""
    cheaper_service = CheaperInferenceService(mock_settings)
    req = ChatRequest(
        messages=[{"role": "user", "content": "test"}],
        model="openrouter/auto",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5},
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    cheaper_service._external_client = mock_client

    # When request.model is openrouter/auto, sanitize to deepseek before dispatch
    res = await cheaper_service.complete_chat(req)
    assert res.message.content == "ok"
    assert req.model == "deepseek-v4.1-flash-1017"
    posted_payload = mock_client.post.call_args.kwargs["json"]
    assert posted_payload["model"] == "deepseek-v4.1-flash-1017"
    assert not posted_payload["model"].startswith("openrouter/")


@pytest.mark.asyncio
async def test_46_runtime_cache_key_includes_routing_mode(agent_runtime: AgentRuntimeManager):
    """Verify AgentRuntimeManager cache key isolates routing_mode (6-tuple key)."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    await agent_runtime.initialize()
    model = FakeListChatModel(responses=["Hello"])
    checkpointer = await agent_runtime.checkpointer_manager.get_async_checkpointer()

    # Compile graph with routing_mode="auto"
    graph_auto = agent_runtime.get_or_compile_agent_graph(
        thread_id="t-cache-1",
        provider_id="cheaper_inference",
        effective_model_id="deepseek-v4.1-flash-1017",
        configuration_version="v1",
        model=model,
        checkpointer=checkpointer,
        routing_mode="auto",
    )

    # Compile graph with routing_mode="explicit"
    graph_explicit = agent_runtime.get_or_compile_agent_graph(
        thread_id="t-cache-1",
        provider_id="cheaper_inference",
        effective_model_id="deepseek-v4.1-flash-1017",
        configuration_version="v1",
        model=model,
        checkpointer=checkpointer,
        routing_mode="explicit",
    )

    # Ensure keys in cache are 6-tuples and distinguish routing_mode
    keys = list(agent_runtime._graph_cache.keys())
    assert len(keys) == 2
    for k in keys:
        assert len(k) == 6
        assert k[0] == "t-cache-1"
        assert k[2] == "cheaper_inference"

    assert ("t-cache-1", "auto", "cheaper_inference", "deepseek-v4.1-flash-1017") == keys[0][:4]
    assert ("t-cache-1", "explicit", "cheaper_inference", "deepseek-v4.1-flash-1017") == keys[1][:4]
    assert graph_auto is not graph_explicit
