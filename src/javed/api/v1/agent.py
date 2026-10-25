"""Deep Agents & LangGraph agent endpoints: streaming, thread state, and status."""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from javed.agent.runtime import AgentRuntimeManager
from javed.schemas.agent import (
    AgentRuntimeStatusResponse,
    AgentStreamEvent,
    AgentStreamRequest,
    AgentThreadStateResponse,
    validate_thread_id,
)

logger = logging.getLogger("javed.api.v1.agent")

router = APIRouter(prefix="/agent", tags=["Agent"])


def get_agent_runtime(request: Request) -> AgentRuntimeManager:
    """Retrieve the initialized AgentRuntimeManager from app state."""
    agent_runtime: AgentRuntimeManager | None = getattr(
        request.app.state,
        "agent_runtime",
        None,
    )
    if not agent_runtime:
        settings = getattr(request.app.state, "settings", None)
        openrouter_service = getattr(request.app.state, "openrouter_service", None)
        agent_runtime = AgentRuntimeManager(settings, openrouter_service=openrouter_service)
        request.app.state.agent_runtime = agent_runtime
    return agent_runtime


@router.post(
    "/stream",
    summary="Real-time Deep Agents streaming execution via Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_agent(
    request_data: AgentStreamRequest,
    request: Request,
) -> StreamingResponse:
    """Execute the stateful Deep Agent runtime and stream typed agent lifecycle events via SSE."""
    runtime = get_agent_runtime(request)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in runtime.stream_agent(request_data):
                if await request.is_disconnected():
                    logger.info(
                        "Client disconnected during agent stream generation for thread %s",
                        request_data.thread_id,
                    )
                    break
                # Emit standard W3C SSE event: event name + JSON data envelope
                yield f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception("Unhandled error in agent stream generator: %s", e)
            err_event = AgentStreamEvent(
                event="run_failed",
                data={
                    "thread_id": request_data.thread_id,
                    "error": str(e),
                },
            )
            yield f"event: run_failed\ndata: {err_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/threads/{thread_id}",
    response_model=AgentThreadStateResponse,
    summary="Retrieve persisted thread messages, task plan, and checkpoint ID",
)
async def get_thread_state(
    thread_id: str,
    request: Request,
) -> AgentThreadStateResponse:
    """Retrieve committed LangGraph checkpoints and plan state for a conversation thread."""
    try:
        validated_id = validate_thread_id(thread_id)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid thread_id: {ve!s}",
        ) from ve

    runtime = get_agent_runtime(request)
    try:
        return await runtime.get_thread_state(validated_id)
    except Exception as e:
        logger.exception("Error retrieving thread state for %s: %s", thread_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve thread state: {e!s}",
        ) from e


@router.get(
    "/status",
    response_model=AgentRuntimeStatusResponse,
    summary="Query agent runtime status, checkpointer health, and security boundaries",
)
async def get_runtime_status(
    request: Request,
) -> AgentRuntimeStatusResponse:
    """Query runtime readiness, checkpointer path, and Zero-Trust tool exclusion rules."""
    runtime = get_agent_runtime(request)
    try:
        return await runtime.get_status()
    except Exception as e:
        logger.exception("Error checking agent runtime status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query runtime status: {e!s}",
        ) from e
