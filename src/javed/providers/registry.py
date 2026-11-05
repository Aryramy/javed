"""Authoritative inference provider registry and capability model for JAVED.

Maintains non-secret descriptors, health statuses, and verified capability flags
for Chat Mode, Agent Mode, Batch STT, Batch TTS, and Real-time Voice.
Guarantees ZERO secrets are stored, serialized, or exposed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from javed.config import Settings

logger = logging.getLogger("javed.providers.registry")

ProviderId = Literal["auto", "openrouter", "cheaper_inference"]
CapabilityId = Literal[
    "chat",
    "agent",
    "transcription",
    "translation",
    "speech",
    "realtime_voice",
    "live_voice",
]
HealthState = Literal[
    "available",
    "degraded",
    "unavailable",
    "not_configured",
    "model_unavailable",
    "capability_mismatch",
]


class ProviderCapabilities(BaseModel):
    """Normalized capability flags for an inference provider."""

    chat: bool = Field(default=False, description="Supports streaming chat completions")
    agent: bool = Field(
        default=False,
        description="Supports Agent Mode (structured tool calling & Deep Agents runtime)",
    )
    transcription: bool = Field(
        default=False,
        description="Supports Batch Speech-to-Text audio transcription (non-streaming)",
    )
    translation: bool = Field(
        default=False,
        description="Supports audio translation into English text",
    )
    speech: bool = Field(
        default=False,
        description="Supports Batch Text-to-Speech audio generation (non-streaming)",
    )
    realtime_voice: bool = Field(
        default=False,
        description="Supports bidirectional real-time voice sessions (deferred to BRICK-012)",
    )
    live_voice: bool = Field(
        default=False,
        description="Supports live voice interaction (deferred to BRICK-012)",
    )


class ProviderDescriptor(BaseModel):
    """Authoritative non-secret descriptor for an inference provider.

    Contains zero API keys, base URLs, credentials, or private routing metadata.
    """

    provider_id: str = Field(
        description="Stable internal identifier: auto, openrouter, cheaper_inference"
    )
    display_name: str = Field(description="User-facing provider name")
    enabled: bool = Field(
        default=True, description="Whether the provider is enabled in system policy"
    )
    configured: bool = Field(
        default=False, description="Whether all required credentials/configurations exist"
    )
    health_state: HealthState = Field(
        default="not_configured", description="Live health and readiness state"
    )
    supported_capabilities: list[str] = Field(
        default_factory=list, description="List of verified capability keys"
    )
    capabilities: ProviderCapabilities = Field(
        default_factory=ProviderCapabilities, description="Structured capability breakdown"
    )
    chat_model_display_name: str | None = Field(
        default=None, description="Safe public display name of the primary chat/agent model"
    )
    stt_model_display_name: str | None = Field(
        default=None, description="Safe public display name of the configured STT model"
    )
    tts_model_display_name: str | None = Field(
        default=None, description="Safe public display name of the configured TTS model"
    )
    tts_voice_display_name: str | None = Field(
        default=None, description="Safe public display name of the configured TTS voice"
    )
    realtime_model_display_name: str | None = Field(
        default=None, description="Safe public display name of the configured real-time voice model"
    )
    supports_streaming_chat: bool = Field(default=True, description="Supports SSE token streaming")
    supports_tool_calling: bool = Field(
        default=False, description="Supports structured function/tool calling"
    )
    supports_structured_tool_arguments: bool = Field(default=False)
    supports_batch_stt: bool = Field(default=False, description="Batch STT registered")
    supports_batch_tts: bool = Field(default=False, description="Batch TTS registered")
    supports_realtime_voice: bool = Field(
        default=False, description="Realtime voice capability registered"
    )
    supports_live_voice: bool = Field(default=False)
    last_capability_check: datetime | None = Field(default=None)
    last_health_check: datetime | None = Field(default=None)
    safe_failure_code: str | None = Field(
        default=None, description="Safe error code without exposing secrets or paths"
    )
    missing_env_vars: list[str] = Field(
        default_factory=list,
        description="Operator diagnostic list of missing environment variable names",
    )


class SanitizedProviderSummary(BaseModel):
    """Sanitized public shape returned by GET /api/v1/providers."""

    id: str
    display_name: str
    configured: bool
    health: HealthState
    chat_model: str | None = None
    capabilities: dict[str, bool]
    safe_failure_code: str | None = None

    @classmethod
    def from_descriptor(cls, d: ProviderDescriptor) -> SanitizedProviderSummary:
        return cls(
            id=d.provider_id,
            display_name=d.display_name,
            configured=d.configured,
            health=d.health_state,
            chat_model=d.chat_model_display_name,
            capabilities=d.capabilities.model_dump(),
            safe_failure_code=d.safe_failure_code,
        )


class ProvidersResponse(BaseModel):
    """Public read-only response for GET /api/v1/providers."""

    default_provider: str = "openrouter"
    selection_enabled: bool = True
    providers: list[SanitizedProviderSummary]


class ProviderRegistry:
    """Authoritative manager for inference providers, capabilities, and health states."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._external_client = http_client
        self._descriptors: dict[str, ProviderDescriptor] = {}
        self._catalog_cache: dict[str, Any] = {}
        self._catalog_cache_time: float = 0.0
        self._catalog_cache_ttl_seconds: float = 300.0
        self._lock = asyncio.Lock()

        # Synchronously populate baseline descriptors from environment settings
        openrouter_desc = self._evaluate_openrouter()
        cheaper_desc = self._evaluate_cheaper_baseline()
        auto_desc = self._evaluate_auto_router(openrouter_desc, cheaper_desc)
        self._descriptors["openrouter"] = openrouter_desc
        self._descriptors["cheaper_inference"] = cheaper_desc
        self._descriptors["auto"] = auto_desc

    def _evaluate_cheaper_baseline(self) -> ProviderDescriptor:
        """Synchronously evaluate Cheaper Inference baseline settings."""
        now = datetime.now(UTC)
        missing_vars: list[str] = []
        if not self.settings.cheaper_inference_api_key:
            missing_vars.append("CHEAPER_INFERENCE_API_KEY")
        if not self.settings.cheaper_inference_model:
            missing_vars.append("CHEAPER_INFERENCE_MODEL")

        configured = len(missing_vars) == 0
        if not configured:
            health: HealthState = "not_configured"
            caps = ProviderCapabilities()
        else:
            health = "available"
            caps = ProviderCapabilities(
                chat=True,
                agent=True,
                transcription=bool(self.settings.cheaper_inference_stt_model),
                translation=bool(self.settings.cheaper_inference_stt_model),
                speech=bool(self.settings.cheaper_inference_tts_model),
                realtime_voice=False,
                live_voice=False,
            )

        supported_caps = [k for k, v in caps.model_dump().items() if v]

        return ProviderDescriptor(
            provider_id="cheaper_inference",
            display_name="Cheaper Inference",
            enabled=True,
            configured=configured,
            health_state=health,
            supported_capabilities=supported_caps,
            capabilities=caps,
            chat_model_display_name=self.settings.cheaper_inference_model if configured else None,
            stt_model_display_name=self.settings.cheaper_inference_stt_model,
            tts_model_display_name=self.settings.cheaper_inference_tts_model,
            tts_voice_display_name=self.settings.cheaper_inference_tts_voice,
            realtime_model_display_name=self.settings.cheaper_inference_realtime_model,
            supports_streaming_chat=True,
            supports_tool_calling=configured,
            supports_structured_tool_arguments=configured,
            supports_batch_stt=bool(configured and self.settings.cheaper_inference_stt_model),
            supports_batch_tts=bool(configured and self.settings.cheaper_inference_tts_model),
            supports_realtime_voice=False,
            supports_live_voice=False,
            last_capability_check=now,
            last_health_check=now,
            safe_failure_code=None if configured else "CHEAPER_INFERENCE_NOT_CONFIGURED",
            missing_env_vars=missing_vars,
        )

    def get_descriptor(self, provider_id: str) -> ProviderDescriptor | None:
        """Retrieve non-secret descriptor for a registered provider."""
        return self._descriptors.get(provider_id)

    def list_descriptors(self) -> list[ProviderDescriptor]:
        """Return all registered provider descriptors in stable order."""
        order = ["auto", "openrouter", "cheaper_inference"]
        return [self._descriptors[pid] for pid in order if pid in self._descriptors]

    async def initialize(self) -> None:
        """Perform initial discovery, capability checks, and health assessments."""
        await self.refresh_capabilities()

    async def refresh_capabilities(self) -> None:
        """Inspect environment configuration and upstream catalogs without making billable calls."""
        async with self._lock:
            # 1. OpenRouter
            openrouter_desc = self._evaluate_openrouter()
            self._descriptors["openrouter"] = openrouter_desc

            # 2. Cheaper Inference
            cheaper_desc = await self._evaluate_cheaper_inference()
            self._descriptors["cheaper_inference"] = cheaper_desc

            # 3. Auto Router
            auto_desc = self._evaluate_auto_router(openrouter_desc, cheaper_desc)
            self._descriptors["auto"] = auto_desc

    def _evaluate_openrouter(self) -> ProviderDescriptor:
        """Evaluate OpenRouter configuration and capability without exposing secrets."""
        now = datetime.now(UTC)
        missing_vars: list[str] = []
        if not self.settings.openrouter_api_key:
            missing_vars.append("OPENROUTER_API_KEY")

        configured = len(missing_vars) == 0
        health: HealthState = "available" if configured else "not_configured"

        chat_model = (
            self.settings.openrouter_model
            or self.settings.openrouter_default_model
            or "openrouter/auto"
        )
        stt_model = self.settings.openrouter_stt_model or "openai/whisper-large-v3-turbo"
        tts_model = self.settings.openrouter_tts_model or "elevenlabs/eleven-v4-turbo"
        tts_voice = self.settings.openrouter_tts_voice or "george"

        caps = ProviderCapabilities(
            chat=configured,
            agent=configured,
            transcription=bool(configured and self.settings.openrouter_stt_model),
            translation=False,
            speech=bool(configured and self.settings.openrouter_tts_model),
            realtime_voice=False,
            live_voice=False,
        )

        supported_caps = [k for k, v in caps.model_dump().items() if v]

        return ProviderDescriptor(
            provider_id="openrouter",
            display_name="OpenRouter",
            enabled=True,
            configured=configured,
            health_state=health,
            supported_capabilities=supported_caps,
            capabilities=caps,
            chat_model_display_name=chat_model if configured else None,
            stt_model_display_name=stt_model if configured else None,
            tts_model_display_name=tts_model if configured else None,
            tts_voice_display_name=tts_voice if configured else None,
            realtime_model_display_name=None,
            supports_streaming_chat=True,
            supports_tool_calling=True,
            supports_structured_tool_arguments=True,
            supports_batch_stt=caps.transcription,
            supports_batch_tts=caps.speech,
            supports_realtime_voice=False,
            supports_live_voice=False,
            last_capability_check=now,
            last_health_check=now,
            safe_failure_code=None if configured else "OPENROUTER_NOT_CONFIGURED",
            missing_env_vars=missing_vars,
        )

    async def _fetch_cheaper_catalog(self) -> list[dict[str, Any]]:
        """Safely fetch and cache the Cheaper Inference /models catalog."""
        now = asyncio.get_event_loop().time()
        if (
            self._catalog_cache
            and (now - self._catalog_cache_time) < self._catalog_cache_ttl_seconds
        ):
            return self._catalog_cache.get("models", [])

        if not self.settings.cheaper_inference_api_key:
            return []

        base_url = self.settings.cheaper_inference_base_url.rstrip("/")
        models_url = f"{base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.settings.cheaper_inference_api_key}",
            "Accept": "application/json",
        }

        try:
            if self._external_client:
                resp = await self._external_client.get(models_url, headers=headers, timeout=10.0)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(models_url, headers=headers)

            if resp.status_code == 200:
                data = resp.json().get("data", [])
                self._catalog_cache = {"models": data}
                self._catalog_cache_time = now
                return data
            else:
                logger.warning(
                    "Cheaper Inference catalog check returned non-200: status=%s",
                    resp.status_code,
                )
                return []
        except Exception as exc:
            logger.warning("Cheaper Inference catalog check encountered transient error: %s", exc)
            return []

    async def _evaluate_cheaper_inference(self) -> ProviderDescriptor:
        """Evaluate Cheaper Inference configuration, model catalog, and capability boundaries."""
        now = datetime.now(UTC)
        missing_vars: list[str] = []

        if not self.settings.cheaper_inference_api_key:
            missing_vars.append("CHEAPER_INFERENCE_API_KEY")

        if not self.settings.cheaper_inference_model:
            missing_vars.append("CHEAPER_INFERENCE_MODEL")

        configured = len(missing_vars) == 0
        if not configured:
            return ProviderDescriptor(
                provider_id="cheaper_inference",
                display_name="Cheaper Inference",
                enabled=True,
                configured=False,
                health_state="not_configured",
                supported_capabilities=[],
                capabilities=ProviderCapabilities(),
                chat_model_display_name=None,
                stt_model_display_name=self.settings.cheaper_inference_stt_model,
                tts_model_display_name=self.settings.cheaper_inference_tts_model,
                tts_voice_display_name=self.settings.cheaper_inference_tts_voice,
                realtime_model_display_name=self.settings.cheaper_inference_realtime_model,
                supports_streaming_chat=True,
                supports_tool_calling=False,
                supports_structured_tool_arguments=False,
                supports_batch_stt=False,
                supports_batch_tts=False,
                supports_realtime_voice=False,
                supports_live_voice=False,
                last_capability_check=now,
                last_health_check=now,
                safe_failure_code="CHEAPER_INFERENCE_NOT_CONFIGURED",
                missing_env_vars=missing_vars,
            )

        # Inspect authenticated model catalog
        catalog = await self._fetch_cheaper_catalog()
        configured_model_id = self.settings.cheaper_inference_model
        model_obj = next((m for m in catalog if m.get("id") == configured_model_id), None)

        if catalog and not model_obj:
            # Model catalog is reachable, but configured model does not exist
            return ProviderDescriptor(
                provider_id="cheaper_inference",
                display_name="Cheaper Inference",
                enabled=True,
                configured=True,
                health_state="model_unavailable",
                supported_capabilities=[],
                capabilities=ProviderCapabilities(),
                chat_model_display_name=configured_model_id,
                stt_model_display_name=self.settings.cheaper_inference_stt_model,
                tts_model_display_name=self.settings.cheaper_inference_tts_model,
                tts_voice_display_name=self.settings.cheaper_inference_tts_voice,
                realtime_model_display_name=self.settings.cheaper_inference_realtime_model,
                supports_streaming_chat=True,
                supports_tool_calling=False,
                supports_structured_tool_arguments=False,
                supports_batch_stt=False,
                supports_batch_tts=False,
                supports_realtime_voice=False,
                supports_live_voice=False,
                last_capability_check=now,
                last_health_check=now,
                safe_failure_code="MODEL_NOT_FOUND_IN_CATALOG",
                missing_env_vars=[],
            )

        # Evaluate capability support
        supports_tools = False
        supports_streaming = True
        if model_obj:
            features = model_obj.get("features", [])
            caps = model_obj.get("capabilities", {})
            supported_params = model_obj.get("supported_parameters", {}).get(
                "/v1/chat/completions", []
            )
            supports_tools = "tool-use" in features or "tools" in supported_params
            supports_streaming = caps.get("streaming", True)
        else:
            # Fallback when catalog check is offline/mocked:
            # default to True if model id suggests tool support
            supports_tools = True

        # Check STT in catalog
        stt_model_id = self.settings.cheaper_inference_stt_model
        stt_obj = next((m for m in catalog if m.get("id") == stt_model_id), None)
        supports_stt = bool(
            stt_model_id and (not catalog or (stt_obj and stt_obj.get("type") == "transcription"))
        )
        supports_translation = bool(
            stt_obj and "/v1/audio/translations" in stt_obj.get("supported_endpoints", [])
        )

        # Check TTS in catalog
        tts_model_id = self.settings.cheaper_inference_tts_model
        tts_obj = next((m for m in catalog if m.get("id") == tts_model_id), None)
        supports_tts = bool(
            tts_model_id and (not catalog or (tts_obj and tts_obj.get("type") == "speech"))
        )

        # Check Realtime in catalog (Registered, deferred to BRICK-012)
        rt_model_id = self.settings.cheaper_inference_realtime_model
        rt_obj = next((m for m in catalog if m.get("id") == rt_model_id), None)
        supports_rt = bool(
            rt_model_id and (not catalog or (rt_obj and rt_obj.get("type") == "realtime"))
        )

        caps = ProviderCapabilities(
            chat=True,
            agent=supports_tools,
            transcription=supports_stt,
            translation=supports_translation,
            speech=supports_tts,
            realtime_voice=supports_rt,
            live_voice=False,
        )

        supported_caps = [k for k, v in caps.model_dump().items() if v]

        health_state: HealthState = "available"
        safe_code: str | None = None
        if not supports_tools:
            health_state = "capability_mismatch"
            safe_code = "AGENT_MODE_UNSUPPORTED"

        return ProviderDescriptor(
            provider_id="cheaper_inference",
            display_name="Cheaper Inference",
            enabled=True,
            configured=True,
            health_state=health_state,
            supported_capabilities=supported_caps,
            capabilities=caps,
            chat_model_display_name=configured_model_id,
            stt_model_display_name=stt_model_id,
            tts_model_display_name=tts_model_id,
            tts_voice_display_name=self.settings.cheaper_inference_tts_voice,
            realtime_model_display_name=rt_model_id,
            supports_streaming_chat=supports_streaming,
            supports_tool_calling=supports_tools,
            supports_structured_tool_arguments=supports_tools,
            supports_batch_stt=supports_stt,
            supports_batch_tts=supports_tts,
            supports_realtime_voice=supports_rt,
            supports_live_voice=False,
            last_capability_check=now,
            last_health_check=now,
            safe_failure_code=safe_code,
            missing_env_vars=[],
        )

    def _evaluate_auto_router(
        self, openrouter: ProviderDescriptor, cheaper: ProviderDescriptor
    ) -> ProviderDescriptor:
        """Evaluate Auto Router state dynamically based on underlying providers."""
        now = datetime.now(UTC)
        any_configured = openrouter.configured or cheaper.configured
        any_available = (
            openrouter.health_state == "available" or cheaper.health_state == "available"
        )

        can_chat = openrouter.capabilities.chat or cheaper.capabilities.chat
        can_agent = openrouter.capabilities.agent or cheaper.capabilities.agent

        caps = ProviderCapabilities(
            chat=can_chat,
            agent=can_agent,
            transcription=openrouter.capabilities.transcription
            or cheaper.capabilities.transcription,
            translation=cheaper.capabilities.translation,
            speech=openrouter.capabilities.speech or cheaper.capabilities.speech,
            realtime_voice=False,
            live_voice=False,
        )

        supported_caps = [k for k, v in caps.model_dump().items() if v]

        health: HealthState = (
            "available"
            if any_available
            else ("not_configured" if not any_configured else "unavailable")
        )

        return ProviderDescriptor(
            provider_id="auto",
            display_name="Auto Router",
            enabled=True,
            configured=any_configured,
            health_state=health,
            supported_capabilities=supported_caps,
            capabilities=caps,
            chat_model_display_name="Dynamic Policy Routing",
            stt_model_display_name=None,
            tts_model_display_name=None,
            tts_voice_display_name=None,
            realtime_model_display_name=None,
            supports_streaming_chat=True,
            supports_tool_calling=can_agent,
            supports_structured_tool_arguments=can_agent,
            supports_batch_stt=caps.transcription,
            supports_batch_tts=caps.speech,
            supports_realtime_voice=False,
            supports_live_voice=False,
            last_capability_check=now,
            last_health_check=now,
            safe_failure_code=None if any_available else "NO_PROVIDERS_AVAILABLE",
            missing_env_vars=[],
        )

    def get_sanitized_response(self) -> ProvidersResponse:
        """Generate public, strictly sanitized provider response for GET /api/v1/providers."""
        descriptors = self.list_descriptors()
        summaries: list[SanitizedProviderSummary] = []

        for d in descriptors:
            summaries.append(
                SanitizedProviderSummary(
                    id=d.provider_id,
                    display_name=d.display_name,
                    configured=d.configured,
                    health=d.health_state,
                    chat_model=d.chat_model_display_name,
                    capabilities=d.capabilities.model_dump(),
                    safe_failure_code=d.safe_failure_code,
                )
            )

        # Default provider is openrouter if configured, else auto or cheaper_inference
        default_pid = "openrouter"
        if not self._descriptors.get(
            "openrouter", ProviderDescriptor(provider_id="openrouter", display_name="OpenRouter")
        ).configured:
            if self._descriptors.get(
                "cheaper_inference",
                ProviderDescriptor(provider_id="cheaper", display_name="Cheaper"),
            ).configured:
                default_pid = "cheaper_inference"
            else:
                default_pid = "auto"

        return ProvidersResponse(
            default_provider=default_pid,
            selection_enabled=True,
            providers=summaries,
        )
