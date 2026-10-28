"""Deterministic browser agent tools for Project Javed.

Provides Pydantic-validated, LangChain-compatible structured tools for web navigation,
element interaction, form filling, text extraction, and screenshot capture.
Enforces SSRF validation, sensitive field masking, bounded timeouts, and structured error results.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from javed.browser.engine import BrowserEngineManager
from javed.browser.security import (
    BrowserSecurityGuard,
    SecurityViolationError,
    SensitiveFieldBlockedError,
    assert_safe_form_input,
    inspect_locator_sensitivity,
    match_sensitive_text,
    redact_sensitive_value,
)

logger = logging.getLogger("javed.browser.tools")


# --- Input Schema Definitions ---


class NavigateInput(BaseModel):
    """Input arguments for browser_navigate tool."""

    url: str = Field(
        description="The target HTTP or HTTPS URL to navigate to (e.g. 'https://example.com')."
    )
    wait_until: str = Field(
        default="domcontentloaded",
        description="Navigation wait condition: 'load', 'domcontentloaded', or 'networkidle'.",
    )
    timeout_ms: int = Field(
        default=15000,
        description="Maximum navigation timeout in milliseconds (bounded at 15000ms).",
    )


class ClickInput(BaseModel):
    """Input arguments for browser_click tool."""

    selector: str = Field(
        description=(
            "CSS selector or text locator of the element to click "
            "(e.g. 'button#submit', 'text=\"Next\"')."
        )
    )
    button: str = Field(
        default="left",
        description="Mouse button to click: 'left', 'right', or 'middle'.",
    )
    timeout_ms: int = Field(
        default=10000,
        description="Maximum timeout in milliseconds to wait for the element to be clickable.",
    )


class FillFormInput(BaseModel):
    """Input arguments for browser_fill_form tool."""

    selector: str = Field(
        description="CSS selector or locator of the form input or textarea element to fill."
    )
    value: str = Field(description="Text value to enter into the form field.")
    clear_first: bool = Field(
        default=True,
        description="Whether to clear existing text in the input before entering the new value.",
    )
    allow_sensitive_override: bool = Field(
        default=False,
        description=(
            "Privileged host override flag allowing interaction with sensitive fields "
            "(defaults to False)."
        ),
    )


class ExtractTextInput(BaseModel):
    """Input arguments for browser_extract_text tool."""

    selector: str = Field(
        default="body",
        description="CSS selector of element to extract text from. Defaults to 'body'.",
    )
    max_chars: int = Field(
        default=8000,
        description="Maximum number of characters to return to prevent context window exhaustion.",
    )
    strip_tags: bool = Field(
        default=True,
        description="Whether to strip scripts, styles, and non-content elements.",
    )


class TakeScreenshotInput(BaseModel):
    """Input arguments for browser_take_screenshot tool."""

    full_page: bool = Field(
        default=False,
        description="Whether to capture entire scrollable page height instead of just viewport.",
    )
    selector: str | None = Field(
        default=None,
        description="Optional CSS selector to screenshot an element instead of full page.",
    )


# --- Browser Session State & Execution Engine ---


class BrowserSession:
    """Maintains an active ephemeral browser context and page for an agent run.

    Provides high-level, safe browser operations with integrated SSRF and credential guardrails.
    """

    def __init__(
        self,
        engine: BrowserEngineManager,
        security_guard: BrowserSecurityGuard | None = None,
    ) -> None:
        self.engine = engine
        self.security_guard = security_guard or BrowserSecurityGuard()
        self._context: Any | None = None
        self._page: Any | None = None

    @property
    def is_active(self) -> bool:
        """Return True if an active page exists and is not closed."""
        return self._page is not None and not self._page.is_closed()

    async def get_or_create_page(self) -> Any:
        """Retrieve the current active Page or spawn a new ephemeral context and Page."""
        if not self.engine.is_ready:
            await self.engine.initialize()

        if self._context is None:
            self._context = await self.engine.create_ephemeral_context()

        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()

        return self._page

    async def close(self) -> None:
        """Close the active page and ephemeral context cleanly."""
        if self._page is not None:
            try:
                if not self._page.is_closed():
                    await self._page.close()
            except Exception as exc:
                logger.debug("Error closing page during session teardown: %s", exc)
            finally:
                self._page = None

        if self._context is not None:
            try:
                await self._context.close()
            except Exception as exc:
                logger.debug("Error closing context during session teardown: %s", exc)
            finally:
                self._context = None

    async def __aenter__(self) -> BrowserSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # --- Tool Implementation Methods ---

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 15000,
    ) -> dict[str, Any]:
        """Navigate the active browser page to a validated URL."""
        # 1. SSRF & Scheme Validation
        try:
            safe_url = self.security_guard.validate_url(url)
        except SecurityViolationError as sec_err:
            logger.warning("Navigation blocked by security guard: %s", sec_err)
            return {
                "success": False,
                "error": str(sec_err),
                "error_type": sec_err.__class__.__name__,
                "url": url,
            }

        # 2. Page Navigation
        try:
            page = await self.get_or_create_page()
            bounded_timeout = min(max(timeout_ms, 1000), 30000)
            response = await page.goto(
                safe_url,
                wait_until=wait_until,
                timeout=bounded_timeout,
            )
            title = await page.title()
            status = response.status if response else 200

            return {
                "success": True,
                "url": page.url,
                "title": title,
                "status": status,
            }
        except Exception as exc:
            logger.error("Navigation error to '%s': %s", url, exc)
            return {
                "success": False,
                "error": f"Navigation failed: {exc}",
                "error_type": exc.__class__.__name__,
                "url": url,
            }

    async def click(
        self,
        selector: str,
        button: str = "left",
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        """Click a target element on the current page."""
        try:
            page = await self.get_or_create_page()
            locator = page.locator(selector).first

            # Wait and click with bounded timeout
            bounded_timeout = min(max(timeout_ms, 500), 15000)
            await locator.click(button=button, timeout=bounded_timeout)

            return {
                "success": True,
                "selector": selector,
                "button": button,
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as exc:
            logger.warning("Click error on selector '%s': %s", selector, exc)
            return {
                "success": False,
                "selector": selector,
                "error": f"Click failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def fill_form(
        self,
        selector: str,
        value: str,
        clear_first: bool = True,
        allow_sensitive_override: bool = False,
    ) -> dict[str, Any]:
        """Fill a form input or textarea after sensitive field verification."""
        # 1. Selector name / pattern check
        try:
            assert_safe_form_input(selector, allow_sensitive_override=allow_sensitive_override)
        except SensitiveFieldBlockedError as block_err:
            logger.warning("Form fill blocked on selector '%s': %s", selector, block_err)
            return {
                "success": False,
                "selector": selector,
                "error": str(block_err),
                "error_type": "SensitiveFieldBlockedError",
            }

        try:
            page = await self.get_or_create_page()
            locator = page.locator(selector).first

            # 2. Live DOM attribute sensitivity inspection
            if not allow_sensitive_override:
                inspection = await inspect_locator_sensitivity(locator)
                if inspection.is_sensitive:
                    err_msg = (
                        f"Action blocked: Target field is sensitive ({inspection.reason}). "
                        "Automated entry of credentials, payment cards, or OTP is prohibited."
                    )
                    logger.warning(
                        "Form fill blocked by DOM inspection on '%s': %s", selector, err_msg
                    )
                    return {
                        "success": False,
                        "selector": selector,
                        "error": err_msg,
                        "error_type": "SensitiveFieldBlockedError",
                    }

            # 3. Perform fill
            if clear_first:
                await locator.fill("")
            await locator.fill(value)

            return {
                "success": True,
                "selector": selector,
                "value_length": len(value),
                "url": page.url,
            }
        except Exception as exc:
            logger.warning("Form fill failed on selector '%s': %s", selector, exc)
            return {
                "success": False,
                "selector": selector,
                "error": f"Form fill failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def extract_text(
        self,
        selector: str = "body",
        max_chars: int = 8000,
        strip_tags: bool = True,
    ) -> dict[str, Any]:
        """Extract sanitized inner text from a container element on the current page."""
        try:
            page = await self.get_or_create_page()

            if strip_tags:
                raw_text = await page.evaluate(
                    """(sel) => {
                        const el = document.querySelector(sel);
                        if (!el) return null;
                        const clone = el.cloneNode(true);
                        const removeEls = clone.querySelectorAll(
                            'script, style, noscript, svg, iframe'
                        );
                        removeEls.forEach(n => n.remove());
                        return clone.innerText || clone.textContent || '';
                    }""",
                    selector,
                )
            else:
                raw_text = await page.locator(selector).first.inner_text()

            if raw_text is None:
                return {
                    "success": False,
                    "selector": selector,
                    "error": f"Element matching selector '{selector}' was not found.",
                    "error_type": "ElementNotFoundError",
                }

            normalized_text = " ".join(raw_text.split())
            is_truncated = len(normalized_text) > max_chars
            extracted = normalized_text[:max_chars]

            return {
                "success": True,
                "selector": selector,
                "text": extracted,
                "length": len(extracted),
                "truncated": is_truncated,
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as exc:
            logger.warning("Text extraction failed on selector '%s': %s", selector, exc)
            return {
                "success": False,
                "selector": selector,
                "error": f"Text extraction failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def take_screenshot(
        self,
        full_page: bool = False,
        selector: str | None = None,
    ) -> dict[str, Any]:
        """Capture a Base64-encoded JPEG screenshot of the current page or specific element."""
        try:
            page = await self.get_or_create_page()

            if selector:
                locator = page.locator(selector).first
                image_bytes = await locator.screenshot(type="jpeg", quality=75)
            else:
                image_bytes = await page.screenshot(full_page=full_page, type="jpeg", quality=75)

            b64_str = base64.b64encode(image_bytes).decode("ascii")

            return {
                "success": True,
                "format": "jpeg",
                "size_bytes": len(image_bytes),
                "data_url": f"data:image/jpeg;base64,{b64_str}",
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as exc:
            logger.warning("Screenshot capture failed: %s", exc)
            return {
                "success": False,
                "error": f"Screenshot capture failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    def get_tools(self) -> list[StructuredTool]:
        """Return the LangChain structured tools bound to this browser session."""
        return create_browser_tools(self)


# --- LangChain Structured Tool Factory ---


def create_browser_tools(session: BrowserSession) -> list[StructuredTool]:
    """Create and return the 5 deterministic browser tools bound to a BrowserSession."""

    async def _navigate(
        url: str, wait_until: str = "domcontentloaded", timeout_ms: int = 15000
    ) -> dict[str, Any]:
        return await session.navigate(url=url, wait_until=wait_until, timeout_ms=timeout_ms)

    async def _click(
        selector: str, button: str = "left", timeout_ms: int = 10000
    ) -> dict[str, Any]:
        return await session.click(selector=selector, button=button, timeout_ms=timeout_ms)

    async def _fill_form(
        selector: str,
        value: str,
        clear_first: bool = True,
        allow_sensitive_override: bool = False,
    ) -> dict[str, Any]:
        return await session.fill_form(
            selector=selector,
            value=value,
            clear_first=clear_first,
            allow_sensitive_override=allow_sensitive_override,
        )

    async def _extract_text(
        selector: str = "body",
        max_chars: int = 8000,
        strip_tags: bool = True,
    ) -> dict[str, Any]:
        return await session.extract_text(
            selector=selector, max_chars=max_chars, strip_tags=strip_tags
        )

    async def _take_screenshot(
        full_page: bool = False, selector: str | None = None
    ) -> dict[str, Any]:
        return await session.take_screenshot(full_page=full_page, selector=selector)

    tools = [
        StructuredTool.from_function(
            coroutine=_navigate,
            name="browser_navigate",
            description=(
                "Navigate the browser to an external HTTP/HTTPS URL. "
                "Enforces SSRF validation and returns the page title, URL, and HTTP status."
            ),
            args_schema=NavigateInput,
        ),
        StructuredTool.from_function(
            coroutine=_click,
            name="browser_click",
            description=(
                "Click an interactive element matching a CSS selector on the active browser page."
            ),
            args_schema=ClickInput,
        ),
        StructuredTool.from_function(
            coroutine=_fill_form,
            name="browser_fill_form",
            description=(
                "Fill a text field or form input element with a value. "
                "Automatically blocks inputs targeting password, credit card, or OTP fields."
            ),
            args_schema=FillFormInput,
        ),
        StructuredTool.from_function(
            coroutine=_extract_text,
            name="browser_extract_text",
            description=(
                "Extract clean, readable text content from an element or the entire page body."
            ),
            args_schema=ExtractTextInput,
        ),
        StructuredTool.from_function(
            coroutine=_take_screenshot,
            name="browser_take_screenshot",
            description=(
                "Capture a JPEG screenshot of the current page viewport or a specific element."
            ),
            args_schema=TakeScreenshotInput,
        ),
    ]
    return tools


def redact_browser_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive arguments from browser tool calls before recording in ledger or logs."""
    redacted = dict(args)
    if tool_name == "browser_fill_form":
        selector = str(args.get("selector", ""))
        is_sens, _ = match_sensitive_text(selector)
        if is_sens or args.get("allow_sensitive_override"):
            if "value" in redacted:
                redacted["value"] = redact_sensitive_value(str(redacted["value"]))
    return redacted
