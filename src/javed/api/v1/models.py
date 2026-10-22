"""Models catalog and metadata endpoints."""

import logging

from fastapi import APIRouter, Request

from javed.schemas.chat import ModelCatalogResponse
from javed.services.openrouter import OpenRouterService

logger = logging.getLogger("javed.api.v1.models")

router = APIRouter(prefix="/models", tags=["Models"])


@router.get(
    "",
    response_model=ModelCatalogResponse,
    summary="List available LLM models and account telemetry",
)
async def list_models(request: Request) -> ModelCatalogResponse:
    """Retrieve curated model catalog with context limits, pricing, and account balance."""
    openrouter_service: OpenRouterService = getattr(
        request.app.state,
        "openrouter_service",
        None,
    )
    if not openrouter_service:
        settings = request.app.state.settings
        openrouter_service = OpenRouterService(settings)

    return await openrouter_service.get_models()
