"""Chat completions and streaming endpoints."""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from javed.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatStreamEvent,
)
from javed.services.openrouter import OpenRouterService

logger = logging.getLogger("javed.api.v1.chat")

router = APIRouter(prefix="/chat", tags=["Chat"])


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
    openrouter_service: OpenRouterService = getattr(
        request.app.state,
        "openrouter_service",
        None,
    )
    if not openrouter_service:
        # Fallback if not mounted on app.state
        settings = request.app.state.settings
        openrouter_service = OpenRouterService(settings)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in openrouter_service.stream_chat(request_data):
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info("Client disconnected during chat stream generation.")
                    break
                yield f"data: {event.model_dump_json()}\n\n"
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
    openrouter_service: OpenRouterService = getattr(
        request.app.state,
        "openrouter_service",
        None,
    )
    if not openrouter_service:
        settings = request.app.state.settings
        openrouter_service = OpenRouterService(settings)

    try:
        return await openrouter_service.complete_chat(request_data)
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
