"""OpenRouter LLM service adapter with dynamic discovery, streaming, and cost tracking."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from javed.config import Settings
from javed.schemas.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    ModelCatalogResponse,
    ModelInfo,
    StreamUsage,
)

logger = logging.getLogger("javed.services.openrouter")

AUTO_ROUTER_MODEL_ID = "openrouter/auto"
SUPPORTED_COST_TIERS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

DEFAULT_SYSTEM_PROMPT: str = (
    "You are Javed, a helpful AI assistant operating within Project Javed. "
    "Current Stage: Stage 2 (BRICK-003: Core Conversational Intelligence). "
    "Crucial Information & Verification Boundary: "
    "You do not currently possess live web browsing, real-time search, or external "
    "financial/news data feeds in this stage (browser and search tools are scheduled "
    "for future bricks). When answering time-sensitive inquiries (such as current events, "
    "today's news, real-time sports results, live market/cryptocurrency prices, or recent "
    "events occurring after your pre-training knowledge cutoff): "
    "1. You MUST clearly disclose upfront that you do not have access to live real-time "
    "tools or a verified current information source. "
    "2. You MUST NOT present outdated model knowledge, assumptions, or speculation as "
    "verified current facts. "
    "3. If providing general or historical context, explicitly identify your knowledge boundary."
)

# Pinned default favorites for quick selection (Auto Router prioritized)
DEFAULT_FAVORITE_MODEL_IDS: list[str] = [
    AUTO_ROUTER_MODEL_ID,
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-flash",
    "deepseek/deepseek-chat",
]

# Curated fallback models when offline or in isolated unit test environments
CURATED_MODELS: list[dict[str, Any]] = [
    {
        "id": AUTO_ROUTER_MODEL_ID,
        "name": "OpenRouter Auto Router",
        "provider": "OpenRouter",
        "context_length": 128000,
        "pricing_prompt": 0.15,
        "pricing_completion": 0.60,
        "description": "Dynamic auto-router with cost tiers (low, medium, high, xhigh, max).",
        "is_default": True,
        "is_favorite": True,
        "is_router": True,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI GPT-4o Mini",
        "provider": "OpenAI",
        "context_length": 128000,
        "pricing_prompt": 0.15,  # $0.15 per 1M tokens
        "pricing_completion": 0.60,  # $0.60 per 1M tokens
        "description": "Fast, economical frontier model ideal for daily tasks.",
        "is_default": False,
        "is_favorite": True,
        "is_router": False,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
    {
        "id": "openai/gpt-4o",
        "name": "OpenAI GPT-4o",
        "provider": "OpenAI",
        "context_length": 128000,
        "pricing_prompt": 2.50,
        "pricing_completion": 10.00,
        "description": "Flagship multimodal intelligence for high-complexity analysis.",
        "is_default": False,
        "is_favorite": True,
        "is_router": False,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "name": "Claude Sonnet 4.5",
        "provider": "Anthropic",
        "context_length": 1000000,
        "pricing_prompt": 3.00,
        "pricing_completion": 15.00,
        "description": "Deep reasoning, nuanced code architecture, and high-fidelity output.",
        "is_default": False,
        "is_favorite": True,
        "is_router": False,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "provider": "Google",
        "context_length": 1048576,
        "pricing_prompt": 0.30,
        "pricing_completion": 2.50,
        "description": "High-velocity inference with massive 1M token context window.",
        "is_default": False,
        "is_favorite": True,
        "is_router": False,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek Chat V3",
        "provider": "DeepSeek",
        "context_length": 163840,
        "pricing_prompt": 0.2574,
        "pricing_completion": 1.0287,
        "description": "High-efficiency open-weights architecture with strong reasoning.",
        "is_default": False,
        "is_favorite": True,
        "is_router": False,
        "supports_tools": True,
        "supported_parameters": ["tools", "tool_choice", "temperature", "max_tokens"],
    },
]


class OpenRouterService:
    """Async adapter service for OpenRouter API."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.default_model = settings.openrouter_default_model
        self.timeout = settings.openrouter_timeout_seconds
        self.app_name = settings.app_name
        self.app_url = settings.app_url
        self._external_client = client

        # Dynamic model cache state
        self.favorite_model_ids: list[str] = list(DEFAULT_FAVORITE_MODEL_IDS)
        self._cached_models: list[ModelInfo] | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 3600.0  # 1 hour cache TTL

    def _get_headers(self) -> dict[str, str]:
        """Construct standard OpenRouter authentication and identification headers."""
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def calculate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        upstream_cost: float | None = None,
        selected_model: str | None = None,
    ) -> float:
        """Calculate total USD cost for a completion using rate card or upstream metric."""
        if upstream_cost is not None and upstream_cost > 0.0:
            return float(upstream_cost)

        target_model = (
            selected_model if (model_id == AUTO_ROUTER_MODEL_ID and selected_model) else model_id
        )
        p_prompt, p_comp = 1.0, 3.0  # Default conservative fallback
        matched = False

        # 1. Check in cached dynamic models
        if self._cached_models:
            for m in self._cached_models:
                if m.id == target_model:
                    p_prompt = m.pricing_prompt
                    p_comp = m.pricing_completion
                    matched = True
                    break

        # 2. Check in curated static fallback list
        if not matched:
            model_entry = next((m for m in CURATED_MODELS if m["id"] == target_model), None)
            if model_entry:
                p_prompt = model_entry["pricing_prompt"]
                p_comp = model_entry["pricing_completion"]

        prompt_cost = (prompt_tokens * p_prompt) / 1_000_000.0
        comp_cost = (completion_tokens * p_comp) / 1_000_000.0
        return round(prompt_cost + comp_cost, 8)

    async def fetch_models(
        self,
        search: str | None = None,
        favorites_only: bool = False,
        force_refresh: bool = False,
    ) -> tuple[list[ModelInfo], int, bool]:
        """Fetch and cache dynamic model catalog from OpenRouter with text compatibility filter.

        Returns (filtered_models, total_models_count, is_dynamic).
        """
        now = time.time()
        needs_refresh = (
            force_refresh
            or self._cached_models is None
            or (now - self._cache_timestamp > self._cache_ttl_seconds)
        )

        is_dynamic = True
        if needs_refresh:
            try:
                url = f"{self.base_url}/models"
                client = self._external_client or httpx.AsyncClient(timeout=10.0)
                should_close = self._external_client is None
                try:
                    resp = await client.get(url, headers=self._get_headers())
                    if resp.status_code == 200:
                        data = resp.json().get("data", [])
                        parsed_models: list[ModelInfo] = []
                        for m in data:
                            mid = m.get("id", "")
                            if not mid:
                                continue

                            # Filter for text-generation compatibility
                            arch = m.get("architecture") or {}
                            out_mods = arch.get("output_modalities") or []
                            modality = arch.get("modality", "")
                            if out_mods and "text" not in out_mods:
                                continue
                            if modality and "image" in modality and "text" not in modality:
                                continue

                            curated_names = {c["id"]: c["name"] for c in CURATED_MODELS}
                            name = curated_names.get(mid, m.get("name") or mid)
                            provider = (
                                mid.split("/")[0].capitalize() if "/" in mid else "OpenRouter"
                            )
                            ctx = int(m.get("context_length") or 0)
                            pricing = m.get("pricing") or {}
                            try:
                                p_prompt = float(pricing.get("prompt") or 0.0) * 1_000_000.0
                            except (ValueError, TypeError):
                                p_prompt = 0.0
                            try:
                                p_comp = float(pricing.get("completion") or 0.0) * 1_000_000.0
                            except (ValueError, TypeError):
                                p_comp = 0.0

                            desc = m.get("description") or f"Model provided by {provider}."
                            is_fav = mid in self.favorite_model_ids
                            is_def = mid == self.default_model
                            is_router = mid == AUTO_ROUTER_MODEL_ID
                            supported_params = m.get("supported_parameters") or []
                            if not isinstance(supported_params, list):
                                supported_params = []
                            supports_tools = (
                                "tools" in supported_params or "tool_choice" in supported_params
                            )

                            parsed_models.append(
                                ModelInfo(
                                    id=mid,
                                    name=name,
                                    provider=provider,
                                    context_length=ctx,
                                    pricing_prompt=round(p_prompt, 4),
                                    pricing_completion=round(p_comp, 4),
                                    description=desc,
                                    is_default=is_def,
                                    is_favorite=is_fav,
                                    is_router=is_router,
                                    cost_tier=(
                                        self.settings.openrouter_auto_router_cost_tier or "low"
                                        if is_router
                                        else None
                                    ),
                                    supports_tools=supports_tools,
                                    supported_parameters=supported_params,
                                )
                            )

                        if parsed_models:
                            # Guarantee openrouter/auto is present
                            has_auto = any(m.id == AUTO_ROUTER_MODEL_ID for m in parsed_models)
                            tier_def = self.settings.openrouter_auto_router_cost_tier or "low"
                            if not has_auto:
                                parsed_models.append(
                                    ModelInfo(
                                        id=AUTO_ROUTER_MODEL_ID,
                                        name="OpenRouter Auto Router",
                                        provider="OpenRouter",
                                        context_length=128000,
                                        pricing_prompt=0.15,
                                        pricing_completion=0.60,
                                        description=(
                                            "Dynamic auto-router with cost tiers "
                                            "(low, medium, high, xhigh, max)."
                                        ),
                                        is_default=(AUTO_ROUTER_MODEL_ID == self.default_model),
                                        is_favorite=True,
                                        is_router=True,
                                        cost_tier=tier_def,
                                        supports_tools=True,
                                        supported_parameters=[
                                            "tools",
                                            "tool_choice",
                                            "temperature",
                                            "max_tokens",
                                        ],
                                    )
                                )
                            else:
                                for m in parsed_models:
                                    if m.id == AUTO_ROUTER_MODEL_ID:
                                        m.is_router = True
                                        m.is_favorite = True
                                        m.cost_tier = tier_def
                                        m.supports_tools = True
                                        m.supported_parameters = [
                                            "tools",
                                            "tool_choice",
                                            "temperature",
                                            "max_tokens",
                                        ]

                            # Sort: Auto Router first, favorites next, then by name
                            parsed_models.sort(
                                key=lambda item: (
                                    item.id != AUTO_ROUTER_MODEL_ID,
                                    not item.is_favorite,
                                    item.name.lower(),
                                )
                            )
                            self._cached_models = parsed_models
                            self._cache_timestamp = now
                    else:
                        logger.warning(
                            f"OpenRouter /models returned HTTP {resp.status_code}; "
                            "using fallback catalog."
                        )
                finally:
                    if should_close:
                        await client.aclose()
            except Exception as e:
                logger.warning(
                    f"Could not dynamically retrieve OpenRouter models ({e}); "
                    "using fallback catalog."
                )

        if not self._cached_models:
            # Fallback to curated catalog
            is_dynamic = False
            self._cached_models = [
                ModelInfo(
                    id=m["id"],
                    name=m["name"],
                    provider=m["provider"],
                    context_length=m["context_length"],
                    pricing_prompt=m["pricing_prompt"],
                    pricing_completion=m["pricing_completion"],
                    description=m["description"],
                    is_default=(m["id"] == self.default_model),
                    is_favorite=(m["id"] in self.favorite_model_ids),
                    is_router=m.get("is_router", False),
                    cost_tier=(
                        self.settings.openrouter_auto_router_cost_tier or "low"
                        if m.get("is_router")
                        else None
                    ),
                    supports_tools=m.get("supports_tools", True),
                    supported_parameters=m.get(
                        "supported_parameters",
                        ["tools", "tool_choice", "temperature", "max_tokens"],
                    ),
                )
                for m in CURATED_MODELS
            ]

        total_count = len(self._cached_models)
        results = self._cached_models

        if favorites_only:
            results = [m for m in results if m.is_favorite]

        if search:
            s = search.strip().lower()
            results = [
                m
                for m in results
                if s in m.id.lower() or s in m.name.lower() or s in m.provider.lower()
            ]

        return results, total_count, is_dynamic

    async def get_models(
        self,
        search: str | None = None,
        favorites_only: bool = False,
        force_refresh: bool = False,
    ) -> ModelCatalogResponse:
        """Return dynamic model catalog and live account credit status."""
        quota_remaining: float | None = None
        authenticated = bool(self.api_key)

        if self.api_key:
            try:
                account_info = await self.get_account_status()
                if account_info and "data" in account_info:
                    data = account_info["data"]
                    quota_remaining = data.get("limit_remaining")
                    if quota_remaining is None and "effective_budget" in data:
                        quota_remaining = data["effective_budget"].get("remaining_usd")
            except Exception as e:
                logger.warning(f"Could not retrieve OpenRouter account telemetry: {e}")

        models, total_count, is_dynamic = await self.fetch_models(
            search=search,
            favorites_only=favorites_only,
            force_refresh=force_refresh,
        )

        return ModelCatalogResponse(
            models=models,
            default_model=self.default_model,
            authenticated=authenticated,
            quota_remaining_usd=round(quota_remaining, 4) if quota_remaining is not None else None,
            daily_budget_usd=self.settings.openrouter_daily_budget_usd,
            total_models=total_count,
            is_dynamic=is_dynamic,
        )

    def get_model_info(self, model_id: str) -> ModelInfo | None:
        """Retrieve model metadata by model ID from cached or curated catalog."""
        if self._cached_models:
            for m in self._cached_models:
                if m.id == model_id:
                    return m
        for c in CURATED_MODELS:
            if c["id"] == model_id:
                return ModelInfo(
                    id=c["id"],
                    name=c["name"],
                    provider=c["provider"],
                    context_length=c["context_length"],
                    pricing_prompt=c["pricing_prompt"],
                    pricing_completion=c["pricing_completion"],
                    description=c["description"],
                    is_default=(c["id"] == self.default_model),
                    is_favorite=(c["id"] in self.favorite_model_ids),
                    is_router=c.get("is_router", False),
                    cost_tier=self.settings.openrouter_auto_router_cost_tier or "low",
                    supports_tools=c.get("supports_tools", True),
                    supported_parameters=c.get(
                        "supported_parameters",
                        ["tools", "tool_choice", "temperature", "max_tokens"],
                    ),
                )
        return None

    def supports_tools(self, model_id: str) -> bool:
        """Check whether a specific model supports structured tool / function calling."""
        if model_id == AUTO_ROUTER_MODEL_ID:
            return True
        info = self.get_model_info(model_id)
        if info is not None:
            return info.supports_tools
        return False

    def get_best_tool_capable_model(self, cost_tier: str | None = None) -> str:
        """Dynamically discover lowest-cost verified tool-capable model from catalog."""
        candidates = [
            m for m in (self._cached_models or []) if m.supports_tools and not m.is_router
        ]
        if candidates:
            candidates.sort(key=lambda m: m.pricing_prompt + m.pricing_completion)
            return candidates[0].id
        return "openai/gpt-4o-mini"

    async def get_account_status(self) -> dict[str, Any] | None:
        """Query OpenRouter key status for balance and quota telemetry.

        Uses the modern documented GET /key endpoint, falling back to /auth/key.
        Credentials and raw account secrets are never exposed to the client.
        """
        if not self.api_key:
            return None

        headers = self._get_headers()
        endpoints = [f"{self.base_url}/key", f"{self.base_url}/auth/key"]

        client = self._external_client or httpx.AsyncClient(timeout=10.0)
        should_close = self._external_client is None

        try:
            for url in endpoints:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return resp.json()
                except Exception as e:
                    logger.debug(f"OpenRouter endpoint {url} failed: {e}")
                    continue
            return None
        except Exception as e:
            logger.warning(f"Error querying OpenRouter key status: {e}")
            return None
        finally:
            if should_close:
                await client.aclose()

    def _prepare_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        """Prepare outgoing messages, prepending system prompt if absent."""
        has_system = any(m.role == "system" for m in messages)
        formatted: list[dict[str, str]] = []
        if not has_system:
            system_prompt = self.settings.openrouter_system_prompt or DEFAULT_SYSTEM_PROMPT
            formatted.append({"role": "system", "content": system_prompt})
        for m in messages:
            formatted.append({"role": m.role, "content": m.content})
        return formatted

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        """Stream chat tokens and usage events from OpenRouter via Server-Sent Events."""
        if not self.api_key:
            yield ChatStreamEvent(
                type="error",
                error="OpenRouter API key is not configured. Set OPENROUTER_API_KEY in .env.",
            )
            return

        model_id = request.model or self.default_model
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": self._prepare_messages(request.messages),
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        # Configure official OpenRouter auto-router plugin if openrouter/auto requested
        effective_cost_tier: str | None = None
        if model_id == AUTO_ROUTER_MODEL_ID:
            effective_cost_tier = (
                request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
            )
            if effective_cost_tier not in SUPPORTED_COST_TIERS:
                effective_cost_tier = "low"
            plugin_cfg: dict[str, Any] = {
                "id": "auto-router",
                "cost_tier": effective_cost_tier,
            }
            payload["plugins"] = [plugin_cfg]

        # Top-level session_id for OpenRouter session stickiness / prompt caching
        if request.session_id:
            payload["session_id"] = request.session_id

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        accumulated_text: list[str] = []
        accumulated_reasoning: list[str] = []
        reported_usage: StreamUsage | None = None
        selected_model: str | None = None
        inside_think = False

        try:
            client = self._external_client or httpx.AsyncClient(timeout=self.timeout)
            should_close = self._external_client is None

            try:
                async with client.stream(
                    "POST", url, headers=headers, json=payload, timeout=self.timeout
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        raw_str = error_body.decode("utf-8", errors="replace")
                        error_msg = f"OpenRouter API error (HTTP {response.status_code}): {raw_str}"
                        logger.error(error_msg)
                        try:
                            parsed_err = json.loads(error_body)
                            error_msg = parsed_err.get("error", {}).get("message", error_msg)
                        except Exception:
                            pass
                        yield ChatStreamEvent(type="error", error=error_msg)
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue

                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # Capture the underlying model selected by OpenRouter
                        chunk_model = chunk.get("model")
                        if chunk_model and not selected_model:
                            selected_model = str(chunk_model)

                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})

                            # Preserve model reasoning traces separately
                            reasoning_delta = delta.get("reasoning") or delta.get(
                                "reasoning_content"
                            )
                            if reasoning_delta:
                                accumulated_reasoning.append(reasoning_delta)
                                yield ChatStreamEvent(
                                    type="reasoning",
                                    reasoning=reasoning_delta,
                                    selected_model=selected_model,
                                    requested_model=model_id,
                                    cost_tier=effective_cost_tier,
                                    session_id=request.session_id,
                                )

                            token = delta.get("content")
                            if token:
                                if "<think>" in token and "</think>" in token:
                                    import re

                                    think_part = re.search(
                                        r"<think>(.*?)</think>", token, re.DOTALL
                                    )
                                    clean_tok = re.sub(
                                        r"<think>.*?</think>", "", token, flags=re.DOTALL
                                    )
                                    if think_part:
                                        r_text = think_part.group(1)
                                        accumulated_reasoning.append(r_text)
                                        yield ChatStreamEvent(
                                            type="reasoning",
                                            reasoning=r_text,
                                            selected_model=selected_model,
                                            requested_model=model_id,
                                            cost_tier=effective_cost_tier,
                                            session_id=request.session_id,
                                        )
                                    if clean_tok:
                                        accumulated_text.append(clean_tok)
                                        yield ChatStreamEvent(
                                            type="token",
                                            content=clean_tok,
                                            selected_model=selected_model,
                                            requested_model=model_id,
                                            cost_tier=effective_cost_tier,
                                            session_id=request.session_id,
                                        )
                                elif not inside_think and "<think>" in token:
                                    parts = token.split("<think>", 1)
                                    if parts[0]:
                                        accumulated_text.append(parts[0])
                                        yield ChatStreamEvent(
                                            type="token",
                                            content=parts[0],
                                            selected_model=selected_model,
                                            requested_model=model_id,
                                            cost_tier=effective_cost_tier,
                                            session_id=request.session_id,
                                        )
                                    if parts[1]:
                                        accumulated_reasoning.append(parts[1])
                                        yield ChatStreamEvent(
                                            type="reasoning",
                                            reasoning=parts[1],
                                            selected_model=selected_model,
                                            requested_model=model_id,
                                            cost_tier=effective_cost_tier,
                                            session_id=request.session_id,
                                        )
                                    inside_think = True
                                elif inside_think:
                                    if "</think>" in token:
                                        parts = token.split("</think>", 1)
                                        if parts[0]:
                                            accumulated_reasoning.append(parts[0])
                                            yield ChatStreamEvent(
                                                type="reasoning",
                                                reasoning=parts[0],
                                                selected_model=selected_model,
                                                requested_model=model_id,
                                                cost_tier=effective_cost_tier,
                                                session_id=request.session_id,
                                            )
                                        inside_think = False
                                        if parts[1]:
                                            accumulated_text.append(parts[1])
                                            yield ChatStreamEvent(
                                                type="token",
                                                content=parts[1],
                                                selected_model=selected_model,
                                                requested_model=model_id,
                                                cost_tier=effective_cost_tier,
                                                session_id=request.session_id,
                                            )
                                    else:
                                        accumulated_reasoning.append(token)
                                        yield ChatStreamEvent(
                                            type="reasoning",
                                            reasoning=token,
                                            selected_model=selected_model,
                                            requested_model=model_id,
                                            cost_tier=effective_cost_tier,
                                            session_id=request.session_id,
                                        )
                                else:
                                    accumulated_text.append(token)
                                    yield ChatStreamEvent(
                                        type="token",
                                        content=token,
                                        selected_model=selected_model,
                                        requested_model=model_id,
                                        cost_tier=effective_cost_tier,
                                        session_id=request.session_id,
                                    )

                        # Process terminal or intermediate usage chunk
                        raw_usage = chunk.get("usage")
                        if raw_usage:
                            prompt_tok = int(raw_usage.get("prompt_tokens", 0))
                            comp_tok = int(raw_usage.get("completion_tokens", 0))
                            total_tok = int(raw_usage.get("total_tokens", prompt_tok + comp_tok))
                            upstream_cost = raw_usage.get("cost")
                            usage_model = raw_usage.get("model") or chunk_model
                            if usage_model:
                                selected_model = str(usage_model)

                            if upstream_cost is not None and float(upstream_cost) > 0.0:
                                cost = float(upstream_cost)
                                cost_src = "upstream"
                            else:
                                cost = self.calculate_cost(
                                    model_id=model_id,
                                    prompt_tokens=prompt_tok,
                                    completion_tokens=comp_tok,
                                    selected_model=selected_model,
                                )
                                cost_src = "rate_card"

                            up_cost_float = (
                                float(upstream_cost) if upstream_cost is not None else None
                            )
                            reported_usage = StreamUsage(
                                prompt_tokens=prompt_tok,
                                completion_tokens=comp_tok,
                                total_tokens=total_tok,
                                cost_usd=cost,
                                upstream_cost=up_cost_float,
                                is_estimated=False,
                                cost_source=cost_src,
                                selected_model=selected_model or model_id,
                                requested_model=model_id,
                                cost_tier=effective_cost_tier,
                                session_id=request.session_id,
                            )
            finally:
                if should_close:
                    await client.aclose()

            # If upstream did not deliver a usage chunk, calculate character-based fallback estimate
            if not reported_usage:
                prompt_chars = sum(len(m.content) for m in request.messages)
                comp_chars = sum(len(t) for t in accumulated_text)
                est_prompt_tokens = max(1, prompt_chars // 4)
                est_comp_tokens = max(1, comp_chars // 4)
                cost = self.calculate_cost(
                    model_id=model_id,
                    prompt_tokens=est_prompt_tokens,
                    completion_tokens=est_comp_tokens,
                    selected_model=selected_model,
                )
                reported_usage = StreamUsage(
                    prompt_tokens=est_prompt_tokens,
                    completion_tokens=est_comp_tokens,
                    total_tokens=est_prompt_tokens + est_comp_tokens,
                    cost_usd=cost,
                    upstream_cost=None,
                    is_estimated=True,
                    cost_source="character_estimate",
                    selected_model=selected_model or model_id,
                    requested_model=model_id,
                    cost_tier=effective_cost_tier,
                    session_id=request.session_id,
                )

            yield ChatStreamEvent(
                type="usage",
                usage=reported_usage,
                selected_model=selected_model,
                requested_model=model_id,
                cost_tier=effective_cost_tier,
                session_id=request.session_id,
            )
            yield ChatStreamEvent(
                type="done",
                selected_model=selected_model,
                requested_model=model_id,
                cost_tier=effective_cost_tier,
                session_id=request.session_id,
            )

        except asyncio.CancelledError:
            logger.info("Chat stream was cancelled by client abort.")
            raise
        except httpx.TimeoutException:
            logger.error("OpenRouter request timed out.")
            yield ChatStreamEvent(
                type="error",
                error=f"Inference timed out after {self.timeout}s waiting for OpenRouter response.",
            )
        except Exception as e:
            logger.exception(f"Unexpected error in OpenRouter stream: {e}")
            yield ChatStreamEvent(type="error", error=f"Internal streaming error: {e!s}")

    async def complete_chat(self, request: ChatRequest) -> ChatResponse:
        """Perform a synchronous (non-streaming) completion request."""
        if not self.api_key:
            raise ValueError("OpenRouter API key is not configured.")

        model_id = request.model or self.default_model
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": self._prepare_messages(request.messages),
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        effective_cost_tier: str | None = None
        if model_id == AUTO_ROUTER_MODEL_ID:
            effective_cost_tier = (
                request.cost_tier or self.settings.openrouter_auto_router_cost_tier or "low"
            )
            if effective_cost_tier not in SUPPORTED_COST_TIERS:
                effective_cost_tier = "low"
            plugin_cfg: dict[str, Any] = {
                "id": "auto-router",
                "cost_tier": effective_cost_tier,
            }
            payload["plugins"] = [plugin_cfg]

        # Top-level session_id for session stickiness and prompt caching
        if request.session_id:
            payload["session_id"] = request.session_id

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        client = self._external_client or httpx.AsyncClient(timeout=self.timeout)
        should_close = self._external_client is None

        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            choice = data.get("choices", [{}])[0]
            choice_msg = choice.get("message", {})
            content = choice_msg.get("content", "")
            reasoning = choice_msg.get("reasoning") or choice_msg.get("reasoning_content")

            # Isolate inline <think> tags if model emits them in content
            if not reasoning and "<think>" in content and "</think>" in content:
                import re

                think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
                if think_match:
                    reasoning = think_match.group(1).strip()
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            finish_reason = choice.get("finish_reason")
            selected_model = data.get("model") or model_id

            raw_usage = data.get("usage", {})
            prompt_tok = int(raw_usage.get("prompt_tokens", 0))
            comp_tok = int(raw_usage.get("completion_tokens", 0))
            total_tok = int(raw_usage.get("total_tokens", prompt_tok + comp_tok))
            upstream_cost = raw_usage.get("cost")

            if upstream_cost is not None and float(upstream_cost) > 0.0:
                cost = float(upstream_cost)
                cost_src = "upstream"
            else:
                cost = self.calculate_cost(
                    model_id=model_id,
                    prompt_tokens=prompt_tok,
                    completion_tokens=comp_tok,
                    selected_model=selected_model,
                )
                cost_src = "rate_card"

            usage = StreamUsage(
                prompt_tokens=prompt_tok,
                completion_tokens=comp_tok,
                total_tokens=total_tok,
                cost_usd=cost,
                upstream_cost=float(upstream_cost) if upstream_cost is not None else None,
                is_estimated=False,
                cost_source=cost_src,
                selected_model=selected_model,
                requested_model=model_id,
                cost_tier=effective_cost_tier,
                session_id=request.session_id,
            )

            return ChatResponse(
                id=data.get("id", "comp-default"),
                model=model_id,
                selected_model=selected_model,
                requested_model=model_id,
                cost_tier=effective_cost_tier,
                session_id=request.session_id,
                reasoning=reasoning,
                message=ChatMessage(
                    role="assistant",
                    content=content,
                    reasoning=reasoning,
                ),
                usage=usage,
                finish_reason=finish_reason,
            )
        finally:
            if should_close:
                await client.aclose()
