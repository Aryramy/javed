"""Inference providers API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from javed.config import Settings, get_settings
from javed.providers.registry import ProviderRegistry, ProvidersResponse
from javed.schemas.providers import ProviderBindingResponse, ProviderSelectionRequest

logger = logging.getLogger("javed.api.v1.providers")

router = APIRouter(prefix="/providers", tags=["Inference Providers"])


def get_provider_registry(request: Request) -> ProviderRegistry:
    """Dependency to retrieve the shared ProviderRegistry instance."""
    registry = getattr(request.app.state, "provider_registry", None)
    if registry is None:
        settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
        registry = ProviderRegistry(settings)
        request.app.state.provider_registry = registry
    return registry


@router.get(
    "",
    summary="List available inference providers and capability matrix",
    response_model=ProvidersResponse,
)
async def list_providers(
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProvidersResponse:
    """Retrieve sanitized non-secret descriptors and live health status."""
    await registry.refresh_capabilities()
    return registry.get_sanitized_response()


@router.post(
    "/bind-thread",
    summary="Atomically validate and bind provider, model, thread, and runtime version",
    response_model=ProviderBindingResponse,
)
async def bind_thread_provider(
    selection: ProviderSelectionRequest,
    request: Request,
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> ProviderBindingResponse:
    """Validate provider, resolve effective model, and return confirmed atomic binding.

    Enforces:
    1. Blocks provider switching while an agent run is active on the current thread.
    2. Blocks provider switching while an approval is pending on the current thread.
    3. Resolves the authoritative backend-controlled model without frontend interference.
    4. Generates an isolated provider-bound thread or updates idle thread state.
    5. Returns confirmed atomic configuration (thread_id, provider_id, effective_model_id, version).
    """
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    inference_router = getattr(request.app.state, "inference_router", None)
    agent_runtime = getattr(request.app.state, "agent_runtime", None)

    target_provider = selection.provider_id.strip().lower()
    valid_providers = {"auto", "openrouter", "cheaper_inference"}
    if target_provider not in valid_providers:
        supported = sorted(list(valid_providers))
        msg = f"Unknown provider '{selection.provider_id}'. Supported providers are: {supported}"
        raise HTTPException(
            status_code=400,
            detail=msg,
        )

    # 1. Block switching if current thread has an active execution
    if selection.current_thread_id and agent_runtime:
        if selection.current_thread_id in agent_runtime._active_threads:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot switch provider to '{selection.provider_id}' while an agent run "
                    f"is actively executing on thread '{selection.current_thread_id}'."
                ),
            )
        # 2. Block switching if current thread has pending approvals
        if agent_runtime.approval_store:
            pending = await agent_runtime.approval_store.get_pending_approvals(
                thread_id=selection.current_thread_id
            )
            if pending:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot switch provider to '{selection.provider_id}' while an approval "
                        f"is pending on thread '{selection.current_thread_id}'. "
                        "Execution must resume under the bound provider."
                    ),
                )

    # 3. Backend validation and effective model resolution
    effective_model: str
    provider_mode: str
    resolved_provider: str
    display_name: str

    if inference_router is not None:
        try:
            if selection.interaction_mode == "agent":
                decision = inference_router.resolve_provider_for_agent(
                    requested_provider_id=target_provider,
                    has_tools=True,
                    cost_tier=selection.cost_tier,
                )
            else:
                decision = inference_router.resolve_provider_for_chat(
                    requested_provider_id=target_provider,
                    cost_tier=selection.cost_tier,
                )
            effective_model = decision.selected_model
            provider_mode = decision.routing_mode
            resolved_provider = decision.selected_provider
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve)) from ve
    else:
        if target_provider == "cheaper_inference":
            effective_model = settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
            provider_mode = "explicit"
            resolved_provider = "cheaper_inference"
        elif target_provider == "openrouter":
            effective_model = settings.openrouter_model or "openrouter/auto"
            provider_mode = "explicit"
            resolved_provider = "openrouter"
        else:
            resolved_provider = (
                "cheaper_inference" if settings.cheaper_inference_api_key else "openrouter"
            )
            effective_model = (
                settings.cheaper_inference_model or "deepseek-v4.1-flash-1017"
                if resolved_provider == "cheaper_inference"
                else "openrouter/auto"
            )
            provider_mode = "auto"

    # 4. Thread allocation: isolate thread on provider switch
    if selection.create_new_thread or not selection.current_thread_id:
        thread_id = f"thread-{uuid.uuid4().hex[:8]}"
    else:
        thread_id = selection.current_thread_id

    config_version = f"v-{uuid.uuid4().hex[:8]}"

    # 5. Atomically bind thread in agent runtime
    if agent_runtime:
        agent_runtime.bind_thread_atomic(
            thread_id=thread_id,
            provider_id=target_provider,
            provider_mode=provider_mode,
            effective_model_id=effective_model,
            configuration_version=config_version,
            reason="api_provider_bind",
            selected_provider_id=resolved_provider,
        )

    # 6. Extract sanitized capabilities
    desc = registry.get_descriptor(target_provider)
    caps: dict[str, bool] = {}
    if desc:
        caps = desc.capabilities.model_dump()
        display_name = desc.display_name
    elif target_provider == "auto":
        display_name = "Auto Router"
        caps = {
            "chat": True,
            "agent": True,
            "transcription": True,
            "translation": True,
            "speech": True,
            "realtime_voice": False,
            "live_voice": False,
        }
    else:
        display_name = target_provider

    return ProviderBindingResponse(
        thread_id=thread_id,
        provider_id=target_provider,
        provider_mode=provider_mode,
        effective_model_id=effective_model,
        configuration_version=config_version,
        display_name=display_name,
        capabilities=caps,
    )
