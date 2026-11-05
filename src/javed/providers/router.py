"""Inference router and provider dispatcher for JAVED.

Manages deterministic routing across Auto Router, OpenRouter, and Cheaper Inference.
Enforces strict capability gating between Chat Mode and Agent Mode, thread binding,
and guarantees that explicit provider selections NEVER silently fall back.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter

from javed.config import Settings
from javed.providers.agent_adapter import ChatCheaperInference
from javed.providers.cheaper_inference import CheaperInferenceService
from javed.providers.registry import ProviderRegistry
from javed.schemas.agent import AgentStreamRequest
from javed.schemas.chat import ChatRequest, ChatResponse, ChatStreamEvent
from javed.services.openrouter import AUTO_ROUTER_MODEL_ID, OpenRouterService

logger = logging.getLogger("javed.providers.router")

VALID_PROVIDERS: set[str] = {"auto", "openrouter", "cheaper_inference"}


class RoutingDecision:
    """Deterministic routing decision for an inference request."""

    def __init__(
        self,
        requested_provider: str,
        selected_provider: str,
        selected_model: str,
        routing_mode: Literal["auto", "explicit"],
        reason: str,
        routing_decision_id: str | None = None,
        configuration_version: str | None = None,
    ) -> None:
        self.requested_provider = requested_provider
        self.selected_provider = selected_provider
        self.selected_model = selected_model
        self.routing_mode = routing_mode
        self.reason = reason
        self.routing_decision_id = routing_decision_id or f"rd-{uuid.uuid4().hex[:8]}"
        self.configuration_version = configuration_version


class InferenceRouter:
    """Central router managing provider selection, dispatch, and capability validation."""

    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
        openrouter_service: OpenRouterService,
        cheaper_service: CheaperInferenceService,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.openrouter_service = openrouter_service
        self.cheaper_service = cheaper_service

    def resolve_provider_for_chat(
        self,
        requested_provider_id: str | None,
        cost_tier: str | None = None,
        requested_model_id: str | None = None,
    ) -> RoutingDecision:
        """Resolve concrete chat provider based on user selection or Auto Router policy."""
        provider_id = (requested_provider_id or "auto").strip().lower()

        # Fail closed on unknown provider identifiers
        if provider_id not in VALID_PROVIDERS:
            valid_list = sorted(list(VALID_PROVIDERS))
            raise ValueError(
                f"Unknown provider '{provider_id}'. Supported providers are: {valid_list}"
            )

        openrouter_desc = self.registry.get_descriptor("openrouter")
        cheaper_desc = self.registry.get_descriptor("cheaper_inference")
        configured_cheaper_model = (
            self.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
        )

        req_model = (requested_model_id or "").strip()

        if provider_id == "openrouter":
            if not openrouter_desc or not openrouter_desc.configured:
                raise ValueError(
                    "OpenRouter is not configured. Set OPENROUTER_API_KEY in backend environment."
                )
            if openrouter_desc.health_state not in ("available", "degraded"):
                raise ValueError(
                    f"OpenRouter is currently unavailable (status: {openrouter_desc.health_state})."
                )

            # Cross-provider model validation
            if req_model and req_model.lower() == configured_cheaper_model.lower():
                raise ValueError(
                    f"Cross-provider model error: Model '{req_model}' belongs to Cheaper Inference "
                    "and cannot be used with OpenRouter."
                )

            model_name = (
                req_model
                or self.settings.openrouter_model
                or self.settings.openrouter_default_model
                or "openrouter/auto"
            )
            return RoutingDecision(
                requested_provider="openrouter",
                selected_provider="openrouter",
                selected_model=model_name,
                routing_mode="explicit",
                reason="Explicit user selection: OpenRouter",
            )

        elif provider_id == "cheaper_inference":
            if not cheaper_desc or not cheaper_desc.configured:
                raise ValueError(
                    "Cheaper Inference is not configured. "
                    "Set CHEAPER_INFERENCE_API_KEY in backend environment."
                )
            if cheaper_desc.health_state not in ("available", "degraded"):
                raise ValueError(
                    "Cheaper Inference is currently unavailable "
                    f"(status: {cheaper_desc.health_state})."
                )

            # Backend-controlled model enforcement for Cheaper Inference
            if req_model and req_model.lower() != configured_cheaper_model.lower():
                raise ValueError(
                    f"Cross-provider model error: Model '{req_model}' is not supported by "
                    f"Cheaper Inference. Cheaper Inference is backend-controlled and uses "
                    f"'{configured_cheaper_model}'."
                )

            model_name = configured_cheaper_model
            return RoutingDecision(
                requested_provider="cheaper_inference",
                selected_provider="cheaper_inference",
                selected_model=model_name,
                routing_mode="explicit",
                reason="Explicit user selection: Cheaper Inference",
            )

        else:
            # Auto Router mode: select best eligible available provider
            if req_model and req_model.lower() == configured_cheaper_model.lower():
                if (
                    cheaper_desc
                    and cheaper_desc.configured
                    and cheaper_desc.health_state in ("available", "degraded")
                ):
                    return RoutingDecision(
                        requested_provider="auto",
                        selected_provider="cheaper_inference",
                        selected_model=configured_cheaper_model,
                        routing_mode="auto",
                        reason="Auto Router routed to Cheaper Inference based on requested model",
                    )

            tier = (cost_tier or self.settings.openrouter_auto_router_cost_tier or "low").lower()

            cheaper_available = bool(
                cheaper_desc
                and cheaper_desc.configured
                and cheaper_desc.health_state in ("available", "degraded")
                and cheaper_desc.capabilities.chat
            )
            openrouter_available = bool(
                openrouter_desc
                and openrouter_desc.configured
                and openrouter_desc.health_state in ("available", "degraded")
                and openrouter_desc.capabilities.chat
            )

            if not cheaper_available and not openrouter_available:
                raise ValueError(
                    "Auto Router error: No configured inference providers are currently available."
                )

            # For cost tiers 'low' or 'medium', if Cheaper Inference is available,
            # route to Cheaper Inference
            if tier in ("low", "medium") and cheaper_available:
                model_name = configured_cheaper_model
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="cheaper_inference",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason=(
                        "Auto Router selected Cheaper Inference for optimal efficiency in "
                        f"'{tier}' cost tier"
                    ),
                )
            elif openrouter_available:
                model_name = (
                    req_model
                    if (
                        req_model
                        and req_model.lower() != configured_cheaper_model.lower()
                        and req_model != "openrouter/auto"
                    )
                    else (
                        self.settings.openrouter_model
                        or self.settings.openrouter_default_model
                        or "openrouter/auto"
                    )
                )
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="openrouter",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason=f"Auto Router selected OpenRouter for '{tier}' cost tier",
                )
            else:
                model_name = configured_cheaper_model
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="cheaper_inference",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason="Auto Router selected Cheaper Inference as available healthy provider",
                )

    def resolve_provider_for_agent(
        self,
        requested_provider_id: str | None,
        has_tools: bool = True,
        cost_tier: str | None = None,
        requested_model_id: str | None = None,
    ) -> RoutingDecision:
        """Resolve concrete provider for Agent Mode, enforcing tool-calling capability gating."""
        provider_id = (requested_provider_id or "auto").strip().lower()

        if provider_id not in VALID_PROVIDERS:
            valid_list = sorted(list(VALID_PROVIDERS))
            raise ValueError(
                f"Unknown provider '{provider_id}'. Supported providers are: {valid_list}"
            )

        openrouter_desc = self.registry.get_descriptor("openrouter")
        cheaper_desc = self.registry.get_descriptor("cheaper_inference")
        configured_cheaper_model = (
            self.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
        )
        req_model = (requested_model_id or "").strip()

        if provider_id == "openrouter":
            if not openrouter_desc or not openrouter_desc.configured:
                raise ValueError(
                    "OpenRouter is not configured. Set OPENROUTER_API_KEY in backend environment."
                )
            if openrouter_desc.health_state not in ("available", "degraded"):
                raise ValueError(
                    f"OpenRouter is currently unavailable (status: {openrouter_desc.health_state})."
                )

            # Cross-provider model validation
            if req_model and req_model.lower() == configured_cheaper_model.lower():
                raise ValueError(
                    f"Cross-provider model error: Model '{req_model}' belongs to Cheaper Inference "
                    "and cannot be used with OpenRouter."
                )

            model_name = (
                req_model
                or self.settings.openrouter_model
                or self.settings.openrouter_default_model
                or "openrouter/auto"
            )
            return RoutingDecision(
                requested_provider="openrouter",
                selected_provider="openrouter",
                selected_model=model_name,
                routing_mode="explicit",
                reason="Explicit user selection: OpenRouter Agent",
            )

        elif provider_id == "cheaper_inference":
            if not cheaper_desc or not cheaper_desc.configured:
                raise ValueError(
                    "Cheaper Inference is not configured. "
                    "Set CHEAPER_INFERENCE_API_KEY in backend environment."
                )
            if cheaper_desc.health_state not in ("available", "degraded"):
                raise ValueError(
                    "Cheaper Inference is currently unavailable "
                    f"(status: {cheaper_desc.health_state})."
                )

            # Strict Agent Mode capability check: must support tool calling
            if has_tools and not cheaper_desc.capabilities.agent:
                raise ValueError(
                    "Cheaper Inference is configured for chat, but the selected backend model "
                    "does not currently support the tool-calling capabilities required by "
                    "Agent Mode."
                )

            # Backend-controlled model enforcement for Cheaper Inference
            if req_model and req_model.lower() != configured_cheaper_model.lower():
                raise ValueError(
                    f"Cross-provider model error: Model '{req_model}' is not supported by "
                    f"Cheaper Inference. Cheaper Inference is backend-controlled and uses "
                    f"'{configured_cheaper_model}'."
                )

            model_name = configured_cheaper_model
            return RoutingDecision(
                requested_provider="cheaper_inference",
                selected_provider="cheaper_inference",
                selected_model=model_name,
                routing_mode="explicit",
                reason="Explicit user selection: Cheaper Inference Agent",
            )

        else:
            # Auto Router mode for Agent: must satisfy tool calling requirements
            if req_model and req_model.lower() == configured_cheaper_model.lower():
                if (
                    cheaper_desc
                    and cheaper_desc.configured
                    and cheaper_desc.health_state in ("available", "degraded")
                    and (not has_tools or cheaper_desc.capabilities.agent)
                ):
                    return RoutingDecision(
                        requested_provider="auto",
                        selected_provider="cheaper_inference",
                        selected_model=configured_cheaper_model,
                        routing_mode="auto",
                        reason="Auto Router routed to Cheaper Inference for Agent Mode",
                    )

            openrouter_agent_ok = bool(
                openrouter_desc
                and openrouter_desc.configured
                and openrouter_desc.health_state in ("available", "degraded")
                and openrouter_desc.capabilities.agent
            )
            cheaper_agent_ok = bool(
                cheaper_desc
                and cheaper_desc.configured
                and cheaper_desc.health_state in ("available", "degraded")
                and cheaper_desc.capabilities.agent
            )

            if not openrouter_agent_ok and not cheaper_agent_ok:
                raise ValueError(
                    "Auto Router error: No configured providers support tool-calling "
                    "required for Agent Mode."
                )

            tier = (cost_tier or self.settings.openrouter_auto_router_cost_tier or "low").lower()
            if tier in ("low", "medium") and cheaper_agent_ok:
                model_name = configured_cheaper_model
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="cheaper_inference",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason="Auto Router selected Cheaper Inference for Agent Mode in low-cost tier",
                )
            elif openrouter_agent_ok:
                model_name = (
                    req_model
                    if (
                        req_model
                        and req_model.lower() != configured_cheaper_model.lower()
                        and req_model != "openrouter/auto"
                    )
                    else (
                        self.settings.openrouter_model
                        or self.settings.openrouter_default_model
                        or "openrouter/auto"
                    )
                )
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="openrouter",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason="Auto Router selected OpenRouter for Agent Mode",
                )
            else:
                model_name = configured_cheaper_model
                return RoutingDecision(
                    requested_provider="auto",
                    selected_provider="cheaper_inference",
                    selected_model=model_name,
                    routing_mode="auto",
                    reason="Auto Router selected Cheaper Inference for Agent Mode",
                )

    async def stream_chat(
        self,
        request: ChatRequest,
        provider_id: str | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Dispatch chat streaming to the resolved provider."""
        decision = self.resolve_provider_for_chat(
            requested_provider_id=provider_id,
            cost_tier=request.cost_tier,
            requested_model_id=request.model,
        )

        logger.info(
            "Routing chat request: provider=%s (requested=%s), model=%s, reason=%s",
            decision.selected_provider,
            decision.requested_provider,
            decision.selected_model,
            decision.reason,
        )

        # Reconcile request model and provider before dispatch
        request.model = decision.selected_model
        request.provider_id = decision.selected_provider

        # Dispatch
        if decision.selected_provider == "cheaper_inference":
            async for ev in self.cheaper_service.stream_chat(request):
                yield ev
        else:
            async for ev in self.openrouter_service.stream_chat(request):
                yield ev

    async def complete_chat(
        self,
        request: ChatRequest,
        provider_id: str | None = None,
    ) -> ChatResponse:
        """Dispatch synchronous chat completion to the resolved provider."""
        decision = self.resolve_provider_for_chat(
            requested_provider_id=provider_id,
            cost_tier=request.cost_tier,
            requested_model_id=request.model,
        )

        # Reconcile request model and provider before dispatch
        request.model = decision.selected_model
        request.provider_id = decision.selected_provider

        if decision.selected_provider == "cheaper_inference":
            return await self.cheaper_service.complete_chat(request)
        else:
            return await self.openrouter_service.complete_chat(request)

    def create_agent_chat_model(
        self,
        request: AgentStreamRequest,
        provider_id: str | None = None,
        has_tools: bool = True,
    ) -> tuple[BaseChatModel, RoutingDecision]:
        """Construct the LangChain BaseChatModel for the resolved Agent Mode provider."""
        req_model_val = getattr(request, "model", None) or getattr(request, "model_name", None)
        decision = self.resolve_provider_for_agent(
            requested_provider_id=provider_id,
            has_tools=has_tools,
            cost_tier=request.cost_tier,
            requested_model_id=req_model_val,
        )

        # Reconcile incoming request model and provider atomically
        if hasattr(request, "model"):
            request.model = decision.selected_model
        if hasattr(request, "provider_id"):
            request.provider_id = decision.selected_provider

        logger.info(
            "Constructing Agent Model: provider=%s, model=%s, reason=%s",
            decision.selected_provider,
            decision.selected_model,
            decision.reason,
        )

        if decision.selected_provider == "cheaper_inference":
            api_key = self.settings.cheaper_inference_api_key
            if not api_key:
                raise ValueError("Cheaper Inference API key is not configured.")
            model = ChatCheaperInference(
                model_name=decision.selected_model,
                api_key=api_key,
                base_url=self.settings.cheaper_inference_base_url,
                temperature=0.2,
                timeout=self.settings.cheaper_inference_timeout_seconds,
            )
            model._effective_model_name = decision.selected_model
            model._fallback_reason = None
            return model, decision
        else:
            api_key = self.settings.openrouter_api_key
            if not api_key:
                raise ValueError("OpenRouter API key is not configured.")
            session_id = request.session_id or request.thread_id
            plugins: list[dict[str, Any]] | None = None
            if decision.selected_model == AUTO_ROUTER_MODEL_ID:
                effective_tier = (
                    request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
                )
                plugins = [{"id": "auto-router", "cost": effective_tier}]

            model = ChatOpenRouter(
                model_name=decision.selected_model,
                openrouter_api_key=api_key,
                openrouter_api_base=self.settings.openrouter_base_url,
                app_url=self.settings.app_url,
                app_title=self.settings.app_name,
                session_id=session_id,
                plugins=plugins,
                stream_usage=True,
                streaming=True,
                temperature=0.2,
            )
            model._effective_model_name = decision.selected_model
            model._fallback_reason = None
            return model, decision
