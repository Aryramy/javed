"""Asynchronous viewport frame streamer for live browser preview.

Captures throttled snapshots (JPEG, quality 60) from active Playwright pages
and broadcasts standardized EventEnvelope payloads to WebSocket subscribers.
Features auto-pause when idle (0 subscribers) to eliminate CPU and bandwidth waste.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from javed.schemas.events import EventEnvelope

logger = logging.getLogger("javed.browser.streamer")

SubscriberCallback = Callable[[EventEnvelope], Awaitable[None]]

DEFAULT_INTERVAL_SECONDS = 0.33  # ~3 FPS throttled stream
DEFAULT_JPEG_QUALITY = 60


class BrowserFrameStreamer:
    """Manages periodic viewport frame capture and broadcasting to connected clients.

    Key Features:
    1. Throttled Capture: Captures JPEG screenshots at a bounded rate (default ~3 fps).
    2. Zero-Idle Waste: Automatically pauses the capture loop when no subscribers are connected.
    3. Resilient Teardown: Cancels capture tasks without dangling async loops or process leaks.
    """

    def __init__(
        self,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        self.interval_seconds = max(0.1, interval_seconds)
        self.quality = min(max(quality, 10), 100)

        self._page: Page | None = None
        self._subscribers: set[SubscriberCallback] = set()
        self._capture_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._frame_count = 0
        self._running = False

    @property
    def has_page(self) -> bool:
        """Return True if an active, open Playwright Page is attached."""
        return self._page is not None and not self._page.is_closed()

    @property
    def is_running(self) -> bool:
        """Return True if the background capture loop is currently active."""
        return self._running and self._capture_task is not None and not self._capture_task.done()

    @property
    def subscriber_count(self) -> int:
        """Return the number of registered subscriber callbacks."""
        return len(self._subscribers)

    @property
    def frame_count(self) -> int:
        """Return the total number of frames captured in the current session."""
        return self._frame_count

    def attach_page(self, page: Page) -> None:
        """Attach a Playwright Page to the streamer and resume capture if subscribers exist."""
        self._page = page
        logger.info(
            "Attached Page to BrowserFrameStreamer (subscribers: %d)", len(self._subscribers)
        )
        if self._subscribers and not self.is_running:
            self._start_capture_task()

    def detach_page(self) -> None:
        """Detach the current page from the streamer and pause capture."""
        self._page = None
        logger.info("Detached Page from BrowserFrameStreamer")

    def add_subscriber(self, callback: SubscriberCallback) -> None:
        """Register a subscriber callback. Starts capture loop if first subscriber."""
        self._subscribers.add(callback)
        logger.debug("Subscriber added (total: %d)", len(self._subscribers))
        if self._page and not self.is_running:
            self._start_capture_task()

    def remove_subscriber(self, callback: SubscriberCallback) -> None:
        """Unregister a subscriber. Pauses the capture loop if no subscribers remain."""
        self._subscribers.discard(callback)
        logger.debug("Subscriber removed (total: %d)", len(self._subscribers))
        if not self._subscribers and self.is_running:
            self._stop_capture_task()

    async def capture_frame(self) -> EventEnvelope | None:
        """Capture a single JPEG snapshot from the attached page and return an EventEnvelope.

        Returns None if no page is attached or the page is closed/navigating.
        """
        if not self.has_page or self._page is None:
            return None

        try:
            image_bytes = await self._page.screenshot(
                type="jpeg",
                quality=self.quality,
                timeout=5000,
            )
            b64_data = base64.b64encode(image_bytes).decode("ascii")
            self._frame_count += 1

            title = ""
            try:
                title = await self._page.title()
            except Exception:
                pass

            viewport = self._page.viewport_size or {"width": 1280, "height": 720}

            envelope = EventEnvelope(
                type="viewport_frame",
                version="1.0",
                correlation_id=None,
                timestamp=datetime.now(UTC),
                payload={
                    "frame_number": self._frame_count,
                    "timestamp": time.time(),
                    "url": self._page.url,
                    "title": title,
                    "viewport": viewport,
                    "format": "jpeg",
                    "size_bytes": len(image_bytes),
                    "image": f"data:image/jpeg;base64,{b64_data}",
                },
            )
            return envelope
        except PlaywrightError as pw_err:
            logger.debug("Frame capture skipped due to Playwright state: %s", pw_err)
            return None
        except Exception as exc:
            logger.warning("Unexpected error during frame capture: %s", exc)
            return None

    async def broadcast_frame(self, envelope: EventEnvelope) -> None:
        """Deliver an EventEnvelope to all registered subscribers."""
        if not self._subscribers:
            return

        callbacks = list(self._subscribers)
        tasks = [self._safe_notify(cb, envelope) for cb in callbacks]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_notify(self, callback: SubscriberCallback, envelope: EventEnvelope) -> None:
        try:
            await callback(envelope)
        except Exception as exc:
            logger.debug("Subscriber notification failed: %s", exc)

    def _start_capture_task(self) -> None:
        """Start the background streaming loop task."""
        if self._capture_task is None or self._capture_task.done():
            self._running = True
            self._capture_task = asyncio.create_task(
                self._stream_loop(), name="BrowserFrameStreamer-loop"
            )
            logger.info("Started background viewport capture task")

    def _stop_capture_task(self) -> None:
        """Request cancellation of the background capture task."""
        self._running = False
        if self._capture_task is not None and not self._capture_task.done():
            self._capture_task.cancel()
            logger.info("Requested cancellation of viewport capture task")

    async def _stream_loop(self) -> None:
        """Continuous capture loop executing at self.interval_seconds."""
        logger.debug("Entering viewport frame stream loop")
        try:
            while self._running:
                # If page was closed or detached, wait briefly or break
                if not self.has_page:
                    await asyncio.sleep(self.interval_seconds)
                    continue

                if self._subscribers:
                    envelope = await self.capture_frame()
                    if envelope is not None:
                        await self.broadcast_frame(envelope)

                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            logger.debug("Viewport stream loop cancelled cleanly")
        except Exception as exc:
            logger.error("Unhandled error in viewport stream loop: %s", exc, exc_info=True)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Cleanly stop the streamer and await task cancellation."""
        self._running = False
        if self._capture_task is not None:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
            finally:
                self._capture_task = None
        self._subscribers.clear()
        self._page = None
        logger.info("BrowserFrameStreamer stopped cleanly")
