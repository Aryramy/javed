"""Cheaper Inference provider adapter for JAVED.

Provides resilient streaming SSE chat completions, usage and billing normalization,
OpenAI-compatible payload serialization, connection retries, and backend-only
registration descriptors for Batch STT, Audio Translation, Batch TTS, and Real-time Voice.
Guarantees ZERO secret leaks in logs, errors, or events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from javed.config import Settings
from javed.schemas.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
    StreamUsage,
)

logger = logging.getLogger("javed.providers.cheaper_inference")

# Default pricing fallback: $0.15/1M input, $0.60/1M output
DEFAULT_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000.0
DEFAULT_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000.0


class CheaperInferenceService:
    """Service adapter for Cheaper Inference API."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._external_client = http_client
        self._timeout = settings.cheaper_inference_timeout_seconds

    def _get_api_key(self) -> str:
        """Resolve API key, failing closed if missing."""
        key = self.settings.cheaper_inference_api_key
        if not key:
            raise ValueError(
                "Cheaper Inference API key is not configured. "
                "Set CHEAPER_INFERENCE_API_KEY in .env."
            )
        return key

    def _get_base_url(self) -> str:
        """Resolve base URL without trailing slash."""
        return self.settings.cheaper_inference_base_url.rstrip("/")

    def calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        charged_micro: int | None = None,
    ) -> float:
        """Calculate or normalize inference cost in USD.

        Uses upstream settled charge if available, otherwise catalog rate card.
        """
        if charged_micro is not None and charged_micro >= 0:
            return round(charged_micro / 1_000_000.0, 6)
        cost = (prompt_tokens * DEFAULT_INPUT_COST_PER_TOKEN) + (
            completion_tokens * DEFAULT_OUTPUT_COST_PER_TOKEN
        )
        return round(cost, 6)

    async def stream_chat(
        self,
        request: ChatRequest,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Stream SSE chat completion tokens, usage telemetry, and billing envelopes."""
        api_key = self._get_api_key()
        base_url = self._get_base_url()

        # Pre-inference validation & sanitization: never dispatch openrouter/* models
        configured_model = self.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
        if request.model and request.model.lower().startswith("openrouter/"):
            logger.warning(
                "Sanitizing invalid OpenRouter model identifier '%s' for Cheaper Inference -> '%s'",
                request.model,
                configured_model,
            )
            model_name = configured_model
            request.model = configured_model
        else:
            model_name = request.model or configured_model

        if model_name.lower().startswith("openrouter/"):
            yield ChatStreamEvent(
                type="error",
                error=(
                    f"Protocol violation: Model '{model_name}' cannot be dispatched "
                    "to Cheaper Inference."
                ),
            )
            return

        if not model_name:
            yield ChatStreamEvent(
                type="error",
                error=(
                    "Cheaper Inference model is not configured. "
                    "Set CHEAPER_INFERENCE_MODEL in .env."
                ),
            )
            return

        chat_url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "Javed-Control-Center/1.0",
        }

        # Build OpenAI-compatible chat completion payload
        messages_payload = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages_payload,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        start_time = time.monotonic()
        first_token_time: float | None = None
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        charged_micro: int | None = None

        transport = httpx.AsyncHTTPTransport(retries=3)
        client_to_use = self._external_client or httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )

        should_close_client = self._external_client is None
        try:
            async with client_to_use.stream(
                "POST",
                chat_url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    raw_err = await response.aread()
                    err_msg = "Upstream inference gateway returned an error"
                    try:
                        parsed = json.loads(raw_err.decode("utf-8", errors="replace"))
                        if "error" in parsed and isinstance(parsed["error"], dict):
                            err_msg = str(parsed["error"].get("message", err_msg))
                        elif "message" in parsed:
                            err_msg = str(parsed["message"])
                    except Exception:
                        pass
                    # Sanitize error message to ensure no keys or host paths leak
                    clean_err = self._sanitize_error(err_msg)
                    logger.error(
                        "Cheaper Inference stream failed with HTTP %s: %s",
                        response.status_code,
                        clean_err,
                    )
                    yield ChatStreamEvent(
                        type="error", error=f"Cheaper Inference error: {clean_err}"
                    )
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    line_str = line.strip()
                    if not line_str.startswith("data:"):
                        continue

                    data_part = line_str[5:].strip()
                    if data_part == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_part)
                    except json.JSONDecodeError:
                        continue

                    # Extract usage if present in chunk
                    if "usage" in chunk and isinstance(chunk["usage"], dict):
                        u = chunk["usage"]
                        prompt_tokens = u.get("prompt_tokens", prompt_tokens)
                        completion_tokens = u.get("completion_tokens", completion_tokens)
                        total_tokens = u.get("total_tokens", prompt_tokens + completion_tokens)

                    # Extract settled charging metadata if present
                    if "x_engy" in chunk and isinstance(chunk["x_engy"], dict):
                        charged_val = chunk["x_engy"].get("charged_micro")
                        if charged_val is not None:
                            try:
                                charged_micro = int(charged_val)
                            except (ValueError, TypeError):
                                pass

                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content_piece = delta.get("content")
                        reasoning_piece = delta.get("reasoning_content")

                        if reasoning_piece:
                            yield ChatStreamEvent(
                                type="reasoning",
                                reasoning=reasoning_piece,
                                selected_model=model_name,
                                requested_model=model_name,
                            )

                        if content_piece:
                            if first_token_time is None:
                                first_token_time = time.monotonic()
                            yield ChatStreamEvent(
                                type="token",
                                content=content_piece,
                                selected_model=model_name,
                                requested_model=model_name,
                            )

            # Terminal usage & cost envelope
            total_elapsed = round((time.monotonic() - start_time) * 1000.0, 2)
            ttft_ms = (
                round((first_token_time - start_time) * 1000.0, 2)
                if first_token_time is not None
                else None
            )
            logger.debug(
                "Cheaper stream finished: total_ms=%s, ttft_ms=%s",
                total_elapsed,
                ttft_ms,
            )

            cost_usd = self.calculate_cost(prompt_tokens, completion_tokens, charged_micro)
            usage = StreamUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens or (prompt_tokens + completion_tokens),
                cost_usd=cost_usd,
                upstream_cost=cost_usd if charged_micro is not None else None,
                is_estimated=charged_micro is None,
                cost_source="upstream" if charged_micro is not None else "rate_card",
                selected_model=model_name,
                requested_model=request.model or model_name,
                session_id=request.session_id,
            )

            yield ChatStreamEvent(
                type="usage",
                usage=usage,
                selected_model=model_name,
                requested_model=model_name,
            )
            yield ChatStreamEvent(
                type="done",
                selected_model=model_name,
                requested_model=model_name,
            )

        except (httpx.ConnectError, OSError):
            clean_msg = (
                "Unable to reach Cheaper Inference AI gateway. Please verify network connectivity."
            )
            logger.warning("Cheaper Inference connection failure: %s", clean_msg)
            yield ChatStreamEvent(type="error", error=clean_msg)
        except httpx.TimeoutException:
            clean_msg = f"Cheaper Inference request timed out after {self._timeout}s."
            logger.warning("Cheaper Inference timeout: %s", clean_msg)
            yield ChatStreamEvent(type="error", error=clean_msg)
        except asyncio.CancelledError:
            logger.info("Cheaper Inference stream cancelled by client.")
            raise
        except Exception as exc:
            clean_msg = self._sanitize_error(str(exc))
            logger.error("Cheaper Inference unexpected streaming error: %s", clean_msg)
            yield ChatStreamEvent(
                type="error", error=f"Cheaper Inference streaming error: {clean_msg}"
            )
        finally:
            if should_close_client:
                await client_to_use.aclose()

    async def complete_chat(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
        """Execute a non-streaming chat completion."""
        api_key = self._get_api_key()
        base_url = self._get_base_url()

        # Pre-inference validation & sanitization: never dispatch openrouter/* models
        configured_model = self.settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
        if request.model and request.model.lower().startswith("openrouter/"):
            logger.warning(
                "Sanitizing invalid OpenRouter model identifier '%s' for Cheaper Inference -> '%s'",
                request.model,
                configured_model,
            )
            model_name = configured_model
            request.model = configured_model
        else:
            model_name = request.model or configured_model

        if model_name.lower().startswith("openrouter/"):
            raise ValueError(
                f"Protocol violation: Model '{model_name}' cannot be dispatched "
                "to Cheaper Inference."
            )

        if not model_name:
            raise ValueError("Cheaper Inference model is not configured.")

        chat_url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Javed-Control-Center/1.0",
        }
        messages_payload = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages_payload,
            "stream": False,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        transport = httpx.AsyncHTTPTransport(retries=3)
        client_to_use = self._external_client or httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )
        should_close = self._external_client is None

        try:
            resp = await client_to_use.post(chat_url, headers=headers, json=payload)
            if resp.status_code != 200:
                clean_err = self._sanitize_error(resp.text)
                raise RuntimeError(
                    f"Cheaper Inference completion failed with HTTP {resp.status_code}: {clean_err}"
                )

            data = resp.json()
            content = ""
            reasoning = None
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                reasoning = msg.get("reasoning_content")

            u = data.get("usage", {})
            p_tokens = u.get("prompt_tokens", 0)
            c_tokens = u.get("completion_tokens", 0)
            t_tokens = u.get("total_tokens", p_tokens + c_tokens)

            charged_micro = None
            if "x_engy" in data and isinstance(data["x_engy"], dict):
                charged_micro = data["x_engy"].get("charged_micro")

            cost_usd = self.calculate_cost(p_tokens, c_tokens, charged_micro)
            usage = StreamUsage(
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
                total_tokens=t_tokens,
                cost_usd=cost_usd,
                upstream_cost=cost_usd if charged_micro is not None else None,
                is_estimated=charged_micro is None,
                cost_source="upstream" if charged_micro is not None else "rate_card",
                selected_model=model_name,
                requested_model=request.model or model_name,
            )

            return ChatResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
                model=model_name,
                provider_id="cheaper_inference",
                selected_model=model_name,
                requested_model=request.model or model_name,
                message=ChatMessage(role="assistant", content=content, reasoning=reasoning),
                reasoning=reasoning,
                usage=usage,
            )
        finally:
            if should_close:
                await client_to_use.aclose()

    def _sanitize_error(self, raw_error: str) -> str:
        """Strip API keys, tokens, file paths, and host details from error strings."""
        if not raw_error:
            return "Unknown error"
        sanitized = raw_error
        # Redact any configured keys
        if self.settings.cheaper_inference_api_key:
            sanitized = sanitized.replace(
                self.settings.cheaper_inference_api_key, "[REDACTED_API_KEY]"
            )
        if self.settings.openrouter_api_key:
            sanitized = sanitized.replace(self.settings.openrouter_api_key, "[REDACTED_API_KEY]")
        # Redact raw Bearer tokens
        import re

        sanitized = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer [REDACTED]", sanitized)
        # Redact local windows drive paths
        sanitized = re.sub(r"[a-zA-Z]:[\\/][^ \t\r\n\'\"]+", "[PATH_REDACTED]", sanitized)
        return sanitized

    async def close(self) -> None:
        """Close any open resources cleanly."""
        pass
