"""Asynchronous Playwright browser engine manager for Project Javed.

Provides robust process lifecycle management, ephemeral context isolation,
strict timeout guardrails, and deterministic teardown without process leakage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

logger = logging.getLogger("javed.browser.engine")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 Javed/0.1.0"
)
DEFAULT_TIMEOUT_MS = 15000  # 15 seconds per NFR-06 and ARCH-001
DEFAULT_NAVIGATION_TIMEOUT_MS = 15000
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


class BrowserEngineError(Exception):
    """Base exception for all browser engine errors."""


class BrowserInitializationError(BrowserEngineError):
    """Raised when the Playwright browser engine fails to initialize."""


class BrowserContextError(BrowserEngineError):
    """Raised when an error occurs during browser context lifecycle operations."""


class BrowserEngineManager:
    """Manages the lifecycle of a Playwright browser instance and ephemeral contexts.

    Key Architectural Guarantees:
    1. Session Isolation: Every task/run executes inside an ephemeral BrowserContext
       with isolated cookies, cache, and state.
    2. Deterministic Teardown: Cleanly closes all active contexts, browsers, and
       Playwright driver processes on shutdown or failure without leaving orphaned processes.
    3. Strict Timeouts: Enforces bounded action and navigation timeouts (15 seconds default).
    4. Concurrency Safety: Async locks prevent concurrent initialization and race conditions.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        channel: str | None = None,
        default_timeout_ms: int = DEFAULT_TIMEOUT_MS,
        default_navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        viewport: dict[str, int] | None = None,
        user_agent: str | None = None,
        java_script_enabled: bool = True,
        accept_downloads: bool = True,
        ignore_https_errors: bool = False,
        launch_args: list[str] | None = None,
    ) -> None:
        self.headless = headless
        self.channel = channel
        self.default_timeout_ms = default_timeout_ms
        self.default_navigation_timeout_ms = default_navigation_timeout_ms
        self.viewport = viewport or DEFAULT_VIEWPORT
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.java_script_enabled = java_script_enabled
        self.accept_downloads = accept_downloads
        self.ignore_https_errors = ignore_https_errors
        self.launch_args = launch_args or []

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._active_contexts: set[BrowserContext] = set()
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        """Return True if the engine is initialized and the browser is connected."""
        return (
            self._browser is not None
            and self._browser.is_connected()
            and self._playwright is not None
        )

    @property
    def active_contexts_count(self) -> int:
        """Return the number of currently open ephemeral contexts."""
        return len(self._active_contexts)

    async def initialize(self) -> None:
        """Initialize the Playwright runtime and launch the browser instance.

        Idempotent: If already initialized and connected, returns immediately.
        Fault-Tolerant: If initialization fails partway, triggers an immediate teardown
        to ensure zero leaked driver processes or memory handles.
        """
        async with self._lock:
            if self.is_ready:
                return

            try:
                self._playwright = await async_playwright().start()

                launch_kwargs: dict[str, Any] = {
                    "headless": self.headless,
                    "args": list(self.launch_args),
                }

                if self.channel:
                    try:
                        self._browser = await self._playwright.chromium.launch(
                            channel=self.channel, **launch_kwargs
                        )
                    except Exception as chan_err:
                        logger.warning(
                            "Failed to launch browser with channel '%s': %s. "
                            "Falling back to default bundled Chromium.",
                            self.channel,
                            chan_err,
                        )
                        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
                else:
                    self._browser = await self._playwright.chromium.launch(**launch_kwargs)

                logger.info(
                    "BrowserEngineManager initialized successfully (headless=%s, channel=%s)",
                    self.headless,
                    self.channel,
                )
            except Exception as exc:
                logger.error("Failed to initialize Playwright browser engine: %s", exc)
                await self._close_internal()
                raise BrowserInitializationError(
                    f"Failed to initialize Playwright browser engine: {exc}"
                ) from exc

    async def close(self) -> None:
        """Cleanly close all active ephemeral contexts, browser, and Playwright driver.

        Idempotent: Safe to call multiple times without error.
        """
        async with self._lock:
            await self._close_internal()

    async def _close_internal(self) -> None:
        """Internal teardown implementation executed under self._lock."""
        # 1. Close all tracked ephemeral contexts
        contexts_to_close = list(self._active_contexts)
        self._active_contexts.clear()
        for ctx in contexts_to_close:
            try:
                await ctx.close()
            except Exception as ctx_err:
                logger.debug("Error closing ephemeral context during teardown: %s", ctx_err)

        # 2. Close the browser instance
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as browser_err:
                logger.debug("Error closing browser instance during teardown: %s", browser_err)
            finally:
                self._browser = None

        # 3. Stop the Playwright driver process
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as pw_err:
                logger.debug("Error stopping Playwright driver during teardown: %s", pw_err)
            finally:
                self._playwright = None

        logger.info("BrowserEngineManager teardown completed cleanly.")

    async def create_ephemeral_context(self, **kwargs: Any) -> BrowserContext:
        """Create and return a new isolated, ephemeral browser context.

        Every context has:
        - Separate, in-memory cookie storage and cache (no persistent state).
        - Enforced action and navigation timeouts.
        - Automatic registration in active contexts tracking.
        """
        if not self.is_ready:
            await self.initialize()

        if self._browser is None:
            raise BrowserContextError("Browser is not available to create a context.")

        context_options: dict[str, Any] = {
            "viewport": kwargs.pop("viewport", self.viewport),
            "user_agent": kwargs.pop("user_agent", self.user_agent),
            "java_script_enabled": kwargs.pop("java_script_enabled", self.java_script_enabled),
            "accept_downloads": kwargs.pop("accept_downloads", self.accept_downloads),
            "ignore_https_errors": kwargs.pop("ignore_https_errors", self.ignore_https_errors),
        }
        context_options.update(kwargs)

        try:
            context = await self._browser.new_context(**context_options)
            context.set_default_timeout(self.default_timeout_ms)
            context.set_default_navigation_timeout(self.default_navigation_timeout_ms)

            self._active_contexts.add(context)
            context.on("close", lambda: self._active_contexts.discard(context))
            return context
        except PlaywrightError as pw_err:
            raise BrowserContextError(f"Failed to create ephemeral context: {pw_err}") from pw_err

    @asynccontextmanager
    async def ephemeral_context(self, **kwargs: Any) -> AsyncIterator[BrowserContext]:
        """Async context manager that yields a newly created ephemeral BrowserContext.

        Guarantees context closure upon block exit even if an exception occurs.
        """
        context = await self.create_ephemeral_context(**kwargs)
        try:
            yield context
        finally:
            try:
                await context.close()
            except Exception as exc:
                logger.debug("Error closing ephemeral context in context manager: %s", exc)
            self._active_contexts.discard(context)

    @asynccontextmanager
    async def ephemeral_page(self, **kwargs: Any) -> AsyncIterator[Page]:
        """Async context manager that yields a new Page in an ephemeral BrowserContext.

        Guarantees both page and context closure upon block exit.
        """
        async with self.ephemeral_context(**kwargs) as context:
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception as exc:
                    logger.debug("Error closing ephemeral page in context manager: %s", exc)

    async def __aenter__(self) -> BrowserEngineManager:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
