"""Chat completions and streaming endpoints with multi-provider dispatch."""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from javed.config import Settings
from javed.providers.cheaper_inference import CheaperInferenceService
from javed.providers.registry import ProviderRegistry
from javed.providers.router import InferenceRouter
from javed.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
)
from javed.services.openrouter import OpenRouterService

logger = logging.getLogger("javed.api.v1.chat")

router = APIRouter(prefix="/chat", tags=["Chat"])


def get_inference_router(request: Request) -> InferenceRouter:
    """Retrieve shared InferenceRouter instance from app state or construct fallback."""
    router_instance: InferenceRouter | None = getattr(
        request.app.state,
        "inference_router",
        None,
    )
    if not router_instance:
        settings: Settings = getattr(request.app.state, "settings", None) or Settings()
        openrouter_service = getattr(
            request.app.state, "openrouter_service", None
        ) or OpenRouterService(settings)
        cheaper_service = getattr(
            request.app.state, "cheaper_service", None
        ) or CheaperInferenceService(settings)
        registry = getattr(request.app.state, "provider_registry", None) or ProviderRegistry(
            settings
        )
        router_instance = InferenceRouter(settings, registry, openrouter_service, cheaper_service)
        request.app.state.inference_router = router_instance
    return router_instance


@router.post(
    "/stream",
    summary="Real-time LLM chat streaming via Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_chat(
    request_data: ChatRequest,
    request: Request,
) -> StreamingResponse:
    """Stream chat completion tokens, usage telemetry, and status envelopes via SSE."""
    inference_router = get_inference_router(request)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in inference_router.stream_chat(
                request_data, provider_id=request_data.provider_id
            ):
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info("Client disconnected during chat stream generation.")
                    break
                yield f"data: {event.model_dump_json()}\n\n"
        except ValueError as e:
            logger.warning(f"Validation error in chat stream routing: {e}")
            err_event = ChatStreamEvent(type="error", error=str(e))
            yield f"data: {err_event.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception(f"Unhandled error in chat stream generator: {e}")
            err_event = ChatStreamEvent(type="error", error=str(e))
            yield f"data: {err_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/completions",
    response_model=ChatResponse,
    summary="Synchronous LLM chat completion",
)
async def complete_chat(
    request_data: ChatRequest,
    request: Request,
) -> ChatResponse:
    """Execute a synchronous, non-streaming chat completion."""
    inference_router = get_inference_router(request)

    try:
        return await inference_router.complete_chat(
            request_data, provider_id=request_data.provider_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception(f"Error in chat completion: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream inference failure: {e!s}",
        ) from e
