"""Unit and integration tests for the core Playwright browser engine subsystem.

Verifies:
1. Asynchronous startup and shutdown of BrowserEngineManager.
2. Ephemeral context creation, isolation, and cookie separation.
3. Basic navigation and DOM inspection with default viewport and timeouts.
4. Robust partial-initialization teardown and exception handling.
5. Fallback behavior when a specified browser channel is unavailable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from javed.browser.engine import (
    DEFAULT_NAVIGATION_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    BrowserEngineManager,
    BrowserInitializationError,
)


@pytest.mark.asyncio
async def test_browser_engine_startup_and_teardown() -> None:
    """Verify clean async startup, ready state, and idempotent shutdown."""
    engine = BrowserEngineManager(headless=True)
    assert not engine.is_ready
    assert engine.active_contexts_count == 0

    try:
        await engine.initialize()
        assert engine.is_ready
        assert engine.active_contexts_count == 0

        # Calling initialize again is idempotent
        await engine.initialize()
        assert engine.is_ready
    finally:
        await engine.close()

    assert not engine.is_ready
    assert engine.active_contexts_count == 0

    # Calling close again is safe and idempotent
    await engine.close()
    assert not engine.is_ready


@pytest.mark.asyncio
async def test_browser_engine_context_manager() -> None:
    """Verify BrowserEngineManager works as an async context manager."""
    async with BrowserEngineManager(headless=True) as engine:
        assert engine.is_ready
        assert engine.active_contexts_count == 0

    assert not engine.is_ready


@pytest.mark.asyncio
async def test_ephemeral_context_creation_and_isolation() -> None:
    """Verify that multiple ephemeral contexts maintain strict state and cookie isolation."""
    async with BrowserEngineManager(headless=True) as engine:
        ctx1 = await engine.create_ephemeral_context()
        ctx2 = await engine.create_ephemeral_context()

        assert engine.active_contexts_count == 2

        try:
            page1 = await ctx1.new_page()
            page2 = await ctx2.new_page()

            # Set a cookie in context 1
            await ctx1.add_cookies(
                [
                    {
                        "name": "jarvis_token",
                        "value": "isolated_secret_abc",
                        "domain": "localhost",
                        "path": "/",
                    }
                ]
            )

            # Navigate both pages to local data URL
            html = "<html><body><h1>Context Isolation</h1></body></html>"
            await page1.set_content(html)
            await page2.set_content(html)

            # Inspect cookies in both contexts
            cookies1 = await ctx1.cookies()
            cookies2 = await ctx2.cookies()

            assert len(cookies1) == 1
            assert cookies1[0]["name"] == "jarvis_token"
            assert cookies1[0]["value"] == "isolated_secret_abc"

            # Context 2 MUST be completely isolated (zero cookies)
            assert len(cookies2) == 0

            await page1.close()
            await page2.close()
        finally:
            await ctx1.close()
            await ctx2.close()

        assert engine.active_contexts_count == 0


@pytest.mark.asyncio
async def test_ephemeral_page_and_basic_navigation() -> None:
    """Verify ephemeral_page yields a functional Page with default viewports and navigates."""
    test_html = """
    <!DOCTYPE html>
    <html>
        <head><title>Javed Test Benchmark</title></head>
        <body>
            <header><h1>JARVIS Automation</h1></header>
            <main>
                <div id="status-indicator">READY</div>
                <input id="search-box" type="text" placeholder="Type here..." />
            </main>
        </body>
    </html>
    """

    async with BrowserEngineManager(headless=True) as engine:
        async with engine.ephemeral_page() as page:
            assert engine.active_contexts_count == 1

            # Navigate using data URL to avoid external network dependency
            await page.set_content(test_html)

            title = await page.title()
            assert title == "Javed Test Benchmark"

            status_text = await page.locator("#status-indicator").text_content()
            assert status_text == "READY"

            # Verify form interaction in page
            search_input = page.locator("#search-box")
            await search_input.fill("Playwright Subsystem Core")
            value = await search_input.input_value()
            assert value == "Playwright Subsystem Core"

            # Verify viewport dimensions
            assert page.viewport_size == DEFAULT_VIEWPORT

        # Context and page must be closed immediately upon exiting ephemeral_page block
        assert engine.active_contexts_count == 0


@pytest.mark.asyncio
async def test_timeout_guardrails_enforced() -> None:
    """Verify that action timeouts are strictly bounded and do not hang indefinitely."""
    # Configure tight timeout of 300ms
    engine = BrowserEngineManager(headless=True, default_timeout_ms=300)
    async with engine:
        async with engine.ephemeral_page() as page:
            await page.set_content("<html><body><div>No elements here</div></body></html>")

            # Expect PlaywrightTimeoutError when waiting for missing element
            with pytest.raises(PlaywrightTimeoutError):
                await page.locator("#nonexistent-target-button").wait_for(timeout=300)


@pytest.mark.asyncio
async def test_teardown_resilience_on_simulated_initialization_failure() -> None:
    """Verify that if browser launch fails, partial state is cleanly torn down with 0 leaks."""
    engine = BrowserEngineManager(headless=True)

    with patch(
        "playwright.async_api._context_manager.PlaywrightContextManager.start"
    ) as mock_start:
        mock_pw = AsyncMock()
        mock_pw.chromium.launch.side_effect = RuntimeError("Simulated launch failure")
        mock_pw.stop = AsyncMock()
        mock_start.return_value = mock_pw

        with pytest.raises(BrowserInitializationError) as exc_info:
            await engine.initialize()

        assert "Simulated launch failure" in str(exc_info.value)
        assert not engine.is_ready
        # Verify that playwright.stop was invoked to prevent leaking driver process
        mock_pw.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_fallback_to_bundled_chromium() -> None:
    """Verify that if a requested channel is unavailable, the engine falls back to Chromium."""
    # Supply a nonexistent channel name to force fallback
    engine = BrowserEngineManager(headless=True, channel="nonexistent_channel_xyz_123")
    try:
        await engine.initialize()
        assert engine.is_ready
        async with engine.ephemeral_page() as page:
            await page.set_content("<html><body><h1>Fallback OK</h1></body></html>")
            assert await page.locator("h1").text_content() == "Fallback OK"
    finally:
        await engine.close()

    assert not engine.is_ready


def test_default_constants() -> None:
    """Verify architectural constants conform to specification."""
    assert DEFAULT_TIMEOUT_MS == 15000
    assert DEFAULT_NAVIGATION_TIMEOUT_MS == 15000
    assert DEFAULT_VIEWPORT == {"width": 1280, "height": 720}
