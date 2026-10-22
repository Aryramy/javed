"""OpenRouter LLM service adapter with streaming, rate cards, and cost tracking."""

import asyncio
import json
import logging
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

# Curated high-performance models available on OpenRouter
CURATED_MODELS: list[dict[str, Any]] = [
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI GPT-4o Mini",
        "provider": "OpenAI",
        "context_length": 128000,
        "pricing_prompt": 0.15,      # $0.15 per 1M tokens
        "pricing_completion": 0.60,  # $0.60 per 1M tokens
        "description": "Fast, economical frontier model ideal for daily tasks.",
        "is_default": True,
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
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "name": "Claude Sonnet 4.5",
        "provider": "Anthropic",
        "context_length": 200000,
        "pricing_prompt": 3.00,
        "pricing_completion": 15.00,
        "description": "Deep reasoning, nuanced code architecture, and high-fidelity output.",
        "is_default": False,
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
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek Chat V3",
        "provider": "DeepSeek",
        "context_length": 64000,
        "pricing_prompt": 0.26,
        "pricing_completion": 1.03,
        "description": "High-efficiency open-weights architecture with strong reasoning.",
        "is_default": False,
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
    ) -> float:
        """Calculate total USD cost for a completion using rate card or upstream metric."""
        if upstream_cost is not None and upstream_cost > 0.0:
            return float(upstream_cost)

        # Lookup model in curated list
        model_entry = next((m for m in CURATED_MODELS if m["id"] == model_id), None)
        if model_entry:
            prompt_cost = (prompt_tokens * model_entry["pricing_prompt"]) / 1_000_000.0
            comp_cost = (completion_tokens * model_entry["pricing_completion"]) / 1_000_000.0
            return round(prompt_cost + comp_cost, 8)

        # Default fallback pricing ($1.00 / 1M prompt, $3.00 / 1M completion)
        return round((prompt_tokens * 1.0 + completion_tokens * 3.0) / 1_000_000.0, 8)

    async def get_models(self) -> ModelCatalogResponse:
        """Return the curated model catalog and live account credit status."""
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

        models = [
            ModelInfo(
                id=m["id"],
                name=m["name"],
                provider=m["provider"],
                context_length=m["context_length"],
                pricing_prompt=m["pricing_prompt"],
                pricing_completion=m["pricing_completion"],
                description=m["description"],
                is_default=(m["id"] == self.default_model),
            )
            for m in CURATED_MODELS
        ]

        return ModelCatalogResponse(
            models=models,
            default_model=self.default_model,
            authenticated=authenticated,
            quota_remaining_usd=round(quota_remaining, 4) if quota_remaining is not None else None,
            daily_budget_usd=self.settings.openrouter_daily_budget_usd,
        )

    async def get_account_status(self) -> dict[str, Any] | None:
        """Query OpenRouter key auth status for balance and quota telemetry."""
        if not self.api_key:
            return None

        url = f"{self.base_url}/auth/key"
        headers = self._get_headers()

        if self._external_client:
            resp = await self._external_client.get(url, headers=headers, timeout=10.0)
            return resp.json() if resp.status_code == 200 else None

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            return resp.json() if resp.status_code == 200 else None

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
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        accumulated_text = []
        reported_usage: StreamUsage | None = None

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

                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            token = delta.get("content")
                            if token:
                                accumulated_text.append(token)
                                yield ChatStreamEvent(type="token", content=token)

                        raw_usage = chunk.get("usage")
                        if raw_usage:
                            prompt_tok = int(raw_usage.get("prompt_tokens", 0))
                            comp_tok = int(raw_usage.get("completion_tokens", 0))
                            total_tok = int(raw_usage.get("total_tokens", prompt_tok + comp_tok))
                            upstream_cost = raw_usage.get("cost")
                            cost = self.calculate_cost(
                                model_id=model_id,
                                prompt_tokens=prompt_tok,
                                completion_tokens=comp_tok,
                                upstream_cost=upstream_cost,
                            )
                            up_cost_float = (
                                float(upstream_cost) if upstream_cost is not None else None
                            )
                            reported_usage = StreamUsage(
                                prompt_tokens=prompt_tok,
                                completion_tokens=comp_tok,
                                total_tokens=total_tok,
                                cost_usd=cost,
                                upstream_cost=up_cost_float,
                            )
            finally:
                if should_close:
                    await client.aclose()

            # If upstream did not provide usage chunk, calculate fallback estimation
            if not reported_usage:
                prompt_chars = sum(len(m.content) for m in request.messages)
                comp_chars = sum(len(t) for t in accumulated_text)
                est_prompt_tokens = max(1, prompt_chars // 4)
                est_comp_tokens = max(1, comp_chars // 4)
                cost = self.calculate_cost(model_id, est_prompt_tokens, est_comp_tokens)
                reported_usage = StreamUsage(
                    prompt_tokens=est_prompt_tokens,
                    completion_tokens=est_comp_tokens,
                    total_tokens=est_prompt_tokens + est_comp_tokens,
                    cost_usd=cost,
                    upstream_cost=None,
                )

            yield ChatStreamEvent(type="usage", usage=reported_usage)
            yield ChatStreamEvent(type="done")

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
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

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
            content = choice.get("message", {}).get("content", "")
            finish_reason = choice.get("finish_reason")

            raw_usage = data.get("usage", {})
            prompt_tok = int(raw_usage.get("prompt_tokens", 0))
            comp_tok = int(raw_usage.get("completion_tokens", 0))
            total_tok = int(raw_usage.get("total_tokens", prompt_tok + comp_tok))
            upstream_cost = raw_usage.get("cost")

            cost = self.calculate_cost(model_id, prompt_tok, comp_tok, upstream_cost)
            usage = StreamUsage(
                prompt_tokens=prompt_tok,
                completion_tokens=comp_tok,
                total_tokens=total_tok,
                cost_usd=cost,
                upstream_cost=float(upstream_cost) if upstream_cost is not None else None,
            )

            return ChatResponse(
                id=data.get("id", "comp-default"),
                model=model_id,
                message=ChatMessage(role="assistant", content=content),
                usage=usage,
                finish_reason=finish_reason,
            )
        finally:
            if should_close:
                await client.aclose()
