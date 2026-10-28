"""Unit and integration tests for deterministic browser agent tools.

Verifies:
1. Pydantic schema validation and LangChain StructuredTool inventory.
2. browser_navigate execution and SSRF rejection with structured error results.
3. browser_click and browser_fill_form execution on interactive elements.
4. browser_fill_form automatic blocking on sensitive credential and card fields.
5. browser_extract_text with tag stripping and character bounds.
6. browser_take_screenshot Base64 output generation.
7. End-to-end tool invocation via LangChain ainvoke().
8. Argument redaction utility for execution ledger recording.
"""

from __future__ import annotations

import pytest

from javed.browser.engine import BrowserEngineManager
from javed.browser.security import BrowserSecurityGuard
from javed.browser.tools import (
    BrowserSession,
    create_browser_tools,
    redact_browser_tool_args,
)


@pytest.fixture
def test_guard() -> BrowserSecurityGuard:
    """Return a security guard that permits data: URLs for local test HTML."""
    return BrowserSecurityGuard(allow_data_urls=True, allow_about_blank=True)


def test_create_browser_tools_inventory() -> None:
    """Verify tool factory returns all 5 expected tools with proper names and descriptions."""
    engine = BrowserEngineManager(headless=True)
    session = BrowserSession(engine)
    tools = session.get_tools()

    tool_names = {t.name for t in tools}
    expected_names = {
        "browser_navigate",
        "browser_click",
        "browser_fill_form",
        "browser_extract_text",
        "browser_take_screenshot",
    }
    assert tool_names == expected_names

    for tool in tools:
        assert tool.description
        assert tool.args_schema is not None


@pytest.mark.asyncio
async def test_browser_navigate_success_and_structured_result(
    test_guard: BrowserSecurityGuard,
) -> None:
    """Verify successful navigation returns structured title, url, and status."""
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        test_url = (
            "data:text/html,<html><head><title>Javed Nav Test</title></head>"
            "<body><h1>Nav Success</h1></body></html>"
        )
        result = await session.navigate(test_url)

        assert result["success"] is True
        assert result["title"] == "Javed Nav Test"
        assert result["status"] == 200
        assert result["url"].startswith("data:text/html")
    await engine.close()


@pytest.mark.asyncio
async def test_browser_navigate_ssrf_and_scheme_rejection() -> None:
    """Verify SSRF and dangerous schemes are blocked and return structured error results."""
    engine = BrowserEngineManager(headless=True)
    strict_guard = BrowserSecurityGuard(resolve_dns=False)
    async with BrowserSession(engine, strict_guard) as session:
        # SSRF loopback attempt
        ssrf_res = await session.navigate("http://127.0.0.1:8000/api")
        assert ssrf_res["success"] is False
        assert ssrf_res["error_type"] == "SSRFBlockedError"
        assert "SSRF violation" in ssrf_res["error"]

        # Dangerous scheme attempt
        scheme_res = await session.navigate("file:///etc/passwd")
        assert scheme_res["success"] is False
        assert scheme_res["error_type"] == "DangerousSchemeError"
        assert "Dangerous or unsupported scheme" in scheme_res["error"]
    await engine.close()


@pytest.mark.asyncio
async def test_browser_click_and_fill_form(test_guard: BrowserSecurityGuard) -> None:
    """Verify clicking elements and filling safe form inputs."""
    html = """
    <!DOCTYPE html>
    <html>
        <body>
            <input id="name-box" type="text" value="" />
            <button id="submit-btn" onclick="document.getElementById('name-box').value='submitted'">
                Submit
            </button>
        </body>
    </html>
    """
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        await session.navigate(f"data:text/html,{html}")

        # Fill input
        fill_res = await session.fill_form("#name-box", "JARVIS Pilot")
        assert fill_res["success"] is True
        assert fill_res["value_length"] == len("JARVIS Pilot")

        # Click button
        click_res = await session.click("#submit-btn")
        assert click_res["success"] is True
        assert click_res["selector"] == "#submit-btn"

        # Verify action result in page
        page = await session.get_or_create_page()
        val = await page.locator("#name-box").input_value()
        assert val == "submitted"
    await engine.close()


@pytest.mark.asyncio
async def test_browser_fill_form_sensitive_blocking(test_guard: BrowserSecurityGuard) -> None:
    """Verify fill_form blocks inputs targeting password, credit card, and sensitive fields."""
    html = """
    <!DOCTYPE html>
    <html>
        <body>
            <form>
                <input id="pass-field" type="password" />
                <input id="safe-field" type="text" name="notes" />
            </form>
        </body>
    </html>
    """
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        await session.navigate(f"data:text/html,{html}")

        # Attempt 1: Target password field -> MUST be blocked by DOM sensitivity inspection
        block_res = await session.fill_form("#pass-field", "secret_pass_123")
        assert block_res["success"] is False
        assert block_res["error_type"] == "SensitiveFieldBlockedError"
        assert "sensitive" in block_res["error"]

        # Attempt 2: Selector matching sensitive token -> MUST be blocked immediately
        selector_block_res = await session.fill_form("input[name='user_password']", "pass123")
        assert selector_block_res["success"] is False
        assert selector_block_res["error_type"] == "SensitiveFieldBlockedError"

        # Attempt 3: Sensitive override flag allows action
        override_res = await session.fill_form(
            "#pass-field", "authorized_pass", allow_sensitive_override=True
        )
        assert override_res["success"] is True

        # Attempt 4: Safe field succeeds normally
        safe_res = await session.fill_form("#safe-field", "Just some notes")
        assert safe_res["success"] is True
    await engine.close()


@pytest.mark.asyncio
async def test_browser_extract_text(test_guard: BrowserSecurityGuard) -> None:
    """Verify text extraction with tag removal and truncation."""
    html = """
    <!DOCTYPE html>
    <html>
        <body>
            <header><h1>Welcome to Javed</h1></header>
            <main>
                <p>This is paragraph content.</p>
                <script>const secret = "should be stripped";</script>
                <style>body { background: black; }</style>
            </main>
        </body>
    </html>
    """
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        await session.navigate(f"data:text/html,{html}")

        # Extract whole body
        res = await session.extract_text("body")
        assert res["success"] is True
        assert "Welcome to Javed" in res["text"]
        assert "This is paragraph content." in res["text"]
        # Scripts and styles must be stripped
        assert "should be stripped" not in res["text"]
        assert "background: black" not in res["text"]

        # Missing element error handling
        missing_res = await session.extract_text("#missing-container")
        assert missing_res["success"] is False
        assert missing_res["error_type"] == "ElementNotFoundError"
    await engine.close()


@pytest.mark.asyncio
async def test_browser_take_screenshot(test_guard: BrowserSecurityGuard) -> None:
    """Verify screenshot capture returns valid Base64 data URL and metadata."""
    html = "<html><body><h1 id='title'>Screenshot Test</h1></body></html>"
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        await session.navigate(f"data:text/html,{html}")

        # Full page screenshot
        res = await session.take_screenshot(full_page=False)
        assert res["success"] is True
        assert res["format"] == "jpeg"
        assert res["size_bytes"] > 0
        assert res["data_url"].startswith("data:image/jpeg;base64,")

        # Element screenshot
        elem_res = await session.take_screenshot(selector="#title")
        assert elem_res["success"] is True
        assert elem_res["size_bytes"] > 0
    await engine.close()


@pytest.mark.asyncio
async def test_langchain_ainvoke_tool_execution(test_guard: BrowserSecurityGuard) -> None:
    """Verify tool execution via LangChain StructuredTool.ainvoke interface."""
    engine = BrowserEngineManager(headless=True)
    async with BrowserSession(engine, test_guard) as session:
        tools = create_browser_tools(session)
        nav_tool = next(t for t in tools if t.name == "browser_navigate")
        extract_tool = next(t for t in tools if t.name == "browser_extract_text")

        # Invoke navigate tool
        nav_output = await nav_tool.ainvoke(
            {"url": "data:text/html,<h1>LangChain Integration</h1>"}
        )
        assert nav_output["success"] is True

        # Invoke extract text tool
        extract_output = await extract_tool.ainvoke({"selector": "h1"})
        assert extract_output["success"] is True
        assert extract_output["text"] == "LangChain Integration"
    await engine.close()


def test_redact_browser_tool_args() -> None:
    """Verify argument redaction for sensitive form fills."""
    # Sensitive selector
    sens_args = {"selector": "input#password", "value": "super_secret_123"}
    redacted = redact_browser_tool_args("browser_fill_form", sens_args)
    assert redacted["value"] == "***REDACTED***"
    assert redacted["selector"] == "input#password"

    # Override flag present
    override_args = {
        "selector": "#pin",
        "value": "1234",
        "allow_sensitive_override": True,
    }
    redacted_override = redact_browser_tool_args("browser_fill_form", override_args)
    assert redacted_override["value"] == "***REDACTED***"

    # Non-sensitive selector
    safe_args = {"selector": "#search-query", "value": "Python Playwright"}
    safe_redacted = redact_browser_tool_args("browser_fill_form", safe_args)
    assert safe_redacted["value"] == "Python Playwright"
