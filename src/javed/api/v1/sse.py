"""Server-Sent Events endpoint for real-time telemetry streaming."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["SSE"])


@router.get("/events", summary="Server-Sent Events Telemetry Stream")
async def sse_events(request: Request) -> StreamingResponse:
    """Subscribe to real-time server telemetry events via Server-Sent Events."""
    sse_manager = request.app.state.sse_manager
    queue = await sse_manager.subscribe()

    return StreamingResponse(
        sse_manager.event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
