"""Server-Sent Events (SSE) broadcaster for one-way server telemetry streams."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from javed.schemas.events import EventEnvelope

logger = logging.getLogger("javed.transport.sse")


class SSEManager:
    """Manages lightweight Server-Sent Event client subscriptions for one-way telemetry."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        """Register a new SSE client subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        logger.info("SSE client subscribed (total: %d)", len(self._subscribers))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unregister an SSE client queue."""
        async with self._lock:
            self._subscribers.discard(queue)
        logger.info("SSE client unsubscribed (total: %d)", len(self._subscribers))

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish a message to all active SSE subscribers."""
        if not self._subscribers:
            return

        envelope = EventEnvelope(
            type=event_type,
            payload=data,
        )
        msg_str = f"event: {event_type}\ndata: {envelope.model_dump_json()}\n\n"

        async with self._lock:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(msg_str)
                except asyncio.QueueFull:
                    logger.warning("Dropping SSE event for slow consumer")

    async def event_generator(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE events to a connected client."""
        # Send initial connection event
        initial = EventEnvelope(
            type="sse_connected",
            payload={
                "message": "SSE telemetry stream active",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        yield f"event: sse_connected\ndata: {initial.model_dump_json()}\n\n"

        try:
            while True:
                try:
                    # Wait for next event or keep-alive tick
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield msg
                except TimeoutError:
                    # Keep-alive comment ping
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self.unsubscribe(queue)
