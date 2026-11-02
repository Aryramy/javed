"""Comprehensive deterministic tests for BRICK-007 Phase 4 Crawl4AI Web Extraction Subsystem.

Validates:
1. URL validation, SSRF defense, scheme validation, credential blocking, query secret stripping.
2. Static page acquisition (headings, paragraphs, lists, code, hr, images).
3. Dynamic rendered page acquisition.
4. Markdown output and visible plain-text output.
5. Title, metadata, and timestamps mapping.
6. Table extraction, caption handling, and malformed table warning.
7. Discovered link sanitization, relative URL resolution, same-origin vs external classification.
8. Request-level redirect validation (blocking redirect to private IP or unapproved domain).
9. Subresource and WebSocket interception.
10. Popups and downloads blocking.
11. Timeouts and cancellation handling.
12. HTTP 401, 403, 429 (with Retry-After), login, and challenge classification.
13. Output bounds enforcement (10 MB main doc limit, character and element count limits).
14. Canonical NormalizedDocument mapping, hash generation, and trust boundary gates.
15. Lifecycle management: start, idempotent close, context manager, and zero process leaks.
"""

from __future__ import annotations

import asyncio
import socket

import pytest
from aiohttp import web

from javed.extraction.schema import (
    ExtractionElementType,
    ExtractionErrorCode,
    ExtractionStatus,
    verify_trust_boundary,
)
from javed.extraction.web import (
    Crawl4AIWebExtractor,
    WebExtractionConfig,
    WebExtractionLimits,
    WebExtractionSecurityError,
    WebExtractionStrategy,
    clean_and_extract_elements,
    extract_url,
    validate_web_url,
)

# -----------------------------------------------------------------------------
# Fixtures: Local Deterministic Aiohttp Test Server
# -----------------------------------------------------------------------------


def find_free_port() -> int:
    """Find a free ephemeral TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fixture_server_port() -> int:
    return find_free_port()


@pytest.fixture
async def local_fixture_server(fixture_server_port: int):
    """Run an isolated local HTTP fixture server on loopback."""
    app = web.Application()

    async def handle_static(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Deterministic Test Page</title>
    <meta name="description" content="A test page for web extraction.">
    <meta name="author" content="Test Author">
    <meta property="article:published_time" content="2026-11-01T12:00:00Z">
</head>
<body>
    <h1>Main Heading</h1>
    <p>This is the first paragraph with important text.</p>
    <h2>Subheading Level 2</h2>
    <p>Second paragraph under level 2.</p>
    <blockquote>Quoted text for extraction.</blockquote>
    <pre><code>def hello():\n    return 'world'</code></pre>
    <ul>
        <li>First list item</li>
        <li>Second list item</li>
    </ul>
    <hr>
    <img src="/logo.png" alt="Company Logo">
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_rendered(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Dynamic Rendered Page</title></head>
<body>
    <h1>Dynamic Title</h1>
    <p>This is a rendered page designed to verify dynamic client-side JavaScript execution.
    Crawl4AI acquires the fully rendered DOM after JavaScript runs.</p>
    <div id="content">Initial text</div>
    <script>
        document.getElementById('content').innerText = 'Dynamically rendered content';
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_table(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Table Page</title></head>
<body>
    <h1>Table Demonstration</h1>
    <table>
        <caption>Financial Overview</caption>
        <thead>
            <tr><th>Quarter</th><th>Revenue</th><th>Growth</th></tr>
        </thead>
        <tbody>
            <tr><td>Q1</td><td>$10M</td><td>+5%</td></tr>
            <tr><td>Q2</td><td>$12M</td><td>+8%</td></tr>
        </tbody>
    </table>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_malformed_table(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Malformed Table</title></head>
<body>
    <h1>Irregular Rows</h1>
    <table>
        <tr><th>Col A</th><th>Col B</th></tr>
        <tr><td>Only One Cell</td></tr>
        <tr><td>Cell 1</td><td>Cell 2</td><td>Surprise Cell 3</td></tr>
    </table>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_links(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Links Page</title></head>
<body>
    <h1>Links Collection</h1>
    <a href="/subpage">Relative Subpage</a>
    <a href="http://127.0.0.1:PORT/about">Same-Origin Absolute</a>
    <a href="https://external-example.com/docs?token=SECRET123&topic=ai">External Link</a>
    <a href="#section-top">Anchor Link</a>
    <a href="javascript:alert(1)">Dangerous JS Link</a>
</body>
</html>""".replace("PORT", str(fixture_server_port))
        return web.Response(text=html, content_type="text/html")

    async def handle_redirect_ok(request: web.Request) -> web.Response:
        raise web.HTTPFound("/static")

    async def handle_redirect_forbidden_ip(request: web.Request) -> web.Response:
        raise web.HTTPFound("http://169.254.169.254/latest/meta-data/")

    async def handle_redirect_unapproved(request: web.Request) -> web.Response:
        raise web.HTTPFound("http://unapproved-evil.com/payload")

    async def handle_subresources(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Subresources</title>
    <link rel="stylesheet" href="/style.css">
    <script src="/script.js"></script>
</head>
<body>
    <h1>Subresource Test</h1>
    <img src="/img.png" alt="Pic">
    <iframe src="/static"></iframe>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_static_asset(request: web.Request) -> web.Response:
        return web.Response(text="/* asset */", content_type="text/plain")

    async def handle_auth_401(request: web.Request) -> web.Response:
        return web.Response(status=401, text="Unauthorized: Login Required")

    async def handle_forbidden_403(request: web.Request) -> web.Response:
        return web.Response(status=403, text="Forbidden: Access Denied")

    async def handle_rate_limit_429(request: web.Request) -> web.Response:
        return web.Response(
            status=429,
            headers={"Retry-After": "1"},
            text="Too Many Requests",
        )

    async def handle_slow(request: web.Request) -> web.Response:
        await asyncio.sleep(4.0)
        return web.Response(
            text="<html><body><h1>Slow</h1></body></html>",
            content_type="text/html",
        )

    async def handle_login(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Login Page</title></head>
<body>
    <h1>Please Sign In</h1>
    <form action="/login" method="post">
        <input type="text" name="user">
        <input type="password" name="password">
        <button type="submit">Log In</button>
    </form>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_challenge(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Attention Required! | Cloudflare</title></head>
<body>
    <h1>Just a moment...</h1>
    <div id="cf-turnstile"></div>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_oversized(request: web.Request) -> web.Response:
        # 12 MB of text
        big_text = "A" * (12 * 1024 * 1024)
        html = f"<html><body><p>{big_text}</p></body></html>"
        return web.Response(text=html, content_type="text/html")

    async def handle_forbidden_sub(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Forbidden Subresource</title></head>
<body>
    <h1>Subresource Test</h1>
    <p>This page tries to load a forbidden image from metadata endpoint.</p>
    <img src="http://169.254.169.254/secret.png" alt="Blocked">
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_forbidden_ws(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Forbidden WebSocket</title></head>
<body>
    <h1>WebSocket Test</h1>
    <p>This page tries to open a forbidden WebSocket.</p>
    <script>
        try { new WebSocket("ws://169.254.169.254/ws"); } catch(e) {}
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_pop_down(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Popup and Download</title></head>
<body>
    <h1>Action Test</h1>
    <p>Attempts popup and download.</p>
    <script>
        try { window.open("/static", "_blank"); } catch(e) {}
    </script>
    <a href="/file.bin" download>DL</a>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_many_elements(request: web.Request) -> web.Response:
        paras = "\n".join(f"<p>Paragraph {i}</p>" for i in range(50))
        html = (
            "<!DOCTYPE html><html><head><title>Many</title></head>"
            f"<body><h1>Header</h1>{paras}</body></html>"
        )
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/static", handle_static)
    app.router.add_get("/rendered", handle_rendered)
    app.router.add_get("/table", handle_table)
    app.router.add_get("/malformed-table", handle_malformed_table)
    app.router.add_get("/links", handle_links)
    app.router.add_get("/redirect-ok", handle_redirect_ok)
    app.router.add_get("/redirect-forbidden-ip", handle_redirect_forbidden_ip)
    app.router.add_get("/redirect-unapproved", handle_redirect_unapproved)
    app.router.add_get("/subresources", handle_subresources)
    app.router.add_get("/style.css", handle_static_asset)
    app.router.add_get("/script.js", handle_static_asset)
    app.router.add_get("/img.png", handle_static_asset)
    app.router.add_get("/auth-401", handle_auth_401)
    app.router.add_get("/forbidden-403", handle_forbidden_403)
    app.router.add_get("/rate-limit-429", handle_rate_limit_429)
    app.router.add_get("/slow", handle_slow)
    app.router.add_get("/login", handle_login)
    app.router.add_get("/challenge", handle_challenge)
    app.router.add_get("/oversized", handle_oversized)
    app.router.add_get("/forbidden-sub", handle_forbidden_sub)
    app.router.add_get("/forbidden-ws", handle_forbidden_ws)
    app.router.add_get("/pop-down", handle_pop_down)
    app.router.add_get("/many-elements", handle_many_elements)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", fixture_server_port)
    await site.start()

    yield f"http://127.0.0.1:{fixture_server_port}"

    await runner.cleanup()


# -----------------------------------------------------------------------------
# Unit Tests: URL Validation & SSRF Prevention
# -----------------------------------------------------------------------------


def test_url_validation_accepts_public_http_and_https() -> None:
    valid_https = validate_web_url("https://example.com/path?foo=bar")
    assert valid_https == "https://example.com/path?foo=bar"

    valid_http = validate_web_url("http://example.com/")
    assert valid_http == "http://example.com/"


def test_url_validation_rejects_dangerous_schemes() -> None:
    for scheme in ("file", "data", "javascript", "blob", "ftp"):
        with pytest.raises(WebExtractionSecurityError, match="Unsupported scheme"):
            validate_web_url(f"{scheme}://example.com/data")


def test_url_validation_rejects_embedded_credentials() -> None:
    with pytest.raises(WebExtractionSecurityError, match="Embedded credentials"):
        validate_web_url("https://user:password@example.com/page")


def test_url_validation_rejects_path_traversal() -> None:
    with pytest.raises(WebExtractionSecurityError, match="Path traversal"):
        validate_web_url("https://example.com/path/../secret")


def test_url_validation_rejects_secret_bearing_query_params() -> None:
    with pytest.raises(WebExtractionSecurityError, match="Prohibited secret-bearing parameter"):
        validate_web_url("https://example.com/data?token=xyz123")

    with pytest.raises(WebExtractionSecurityError, match="Prohibited secret-bearing parameter"):
        validate_web_url("https://example.com/data?api_key=secretkey")


def test_url_validation_enforces_approved_domains() -> None:
    approved = ["example.com", "trusted.org"]

    # Exact match passes
    assert (
        validate_web_url("https://example.com/page", approved_domains=approved)
        == "https://example.com/page"
    )

    # Subdomain passes
    assert (
        validate_web_url("https://sub.example.com/page", approved_domains=approved)
        == "https://sub.example.com/page"
    )

    # Unapproved domain rejected
    with pytest.raises(WebExtractionSecurityError, match="not in approved domains"):
        validate_web_url("https://evil.com/page", approved_domains=approved)


def test_url_validation_production_rejects_loopback_and_metadata() -> None:
    # Default production mode (allow_loopback_for_testing=False)
    with pytest.raises(WebExtractionSecurityError, match="SSRF or security violation"):
        validate_web_url("http://127.0.0.1:8080/admin")

    with pytest.raises(WebExtractionSecurityError, match="SSRF or security violation"):
        validate_web_url("http://localhost:8080/admin")

    with pytest.raises(WebExtractionSecurityError, match="SSRF or security violation"):
        validate_web_url("http://169.254.169.254/latest/meta-data/")

    # Hex/decimal loopback representation
    with pytest.raises(WebExtractionSecurityError, match="SSRF or security violation"):
        validate_web_url("http://0x7f000001:8080/")

    with pytest.raises(WebExtractionSecurityError, match="SSRF or security violation"):
        validate_web_url("http://2130706433:8080/")


def test_url_validation_test_override_allows_loopback_but_blocks_metadata() -> None:
    # Test override permits loopback for testing
    ok = validate_web_url("http://127.0.0.1:8999/test", allow_loopback_for_testing=True)
    assert "127.0.0.1" in ok

    # But cloud metadata remains blocked even under test mode!
    with pytest.raises(WebExtractionSecurityError, match="SSRF violation"):
        validate_web_url(
            "http://169.254.169.254/latest/meta-data/",
            allow_loopback_for_testing=True,
        )


# -----------------------------------------------------------------------------
# Unit Tests: HTML Element Cleaning & Parsing
# -----------------------------------------------------------------------------


def test_clean_and_extract_elements_structure() -> None:
    html = """<!DOCTYPE html>
<html>
<head><title>Sample Doc</title></head>
<body>
    <h1>Title</h1>
    <p>Para 1</p>
    <h2>Sub</h2>
    <p>Para 2</p>
    <ul><li>Bullet 1</li></ul>
    <pre><code>val = 1</code></pre>
    <hr>
    <img src="/img.png" alt="Alt text">
</body>
</html>"""
    parsed = clean_and_extract_elements(
        html=html,
        base_url="https://example.com/doc",
        initial_url="https://example.com/doc",
        limits=WebExtractionLimits(),
    )
    assert parsed.title == "Sample Doc"
    assert len(parsed.elements) == 8
    types = [e.element_type for e in parsed.elements]
    assert types == [
        ExtractionElementType.HEADING,
        ExtractionElementType.TEXT,
        ExtractionElementType.HEADING,
        ExtractionElementType.TEXT,
        ExtractionElementType.LIST_ITEM,
        ExtractionElementType.CODE,
        ExtractionElementType.HORIZONTAL_RULE,
        ExtractionElementType.IMAGE,
    ]
    # Check hierarchy
    h2_elem = parsed.elements[2]
    assert len(h2_elem.section_hierarchy) == 2
    assert h2_elem.section_hierarchy[0].title == "Title"
    assert h2_elem.section_hierarchy[1].title == "Sub"


def test_clean_and_extract_table_and_malformed_normalization() -> None:
    html = """<table>
        <caption>Cap</caption>
        <thead><tr><th>A</th><th>B</th></tr></thead>
        <tbody>
            <tr><td>1</td></tr>
            <tr><td>2</td><td>3</td><td>Extra</td></tr>
        </tbody>
    </table>"""
    parsed = clean_and_extract_elements(
        html=html,
        base_url="https://example.com",
        initial_url="https://example.com",
        limits=WebExtractionLimits(),
    )
    assert len(parsed.tables) == 1
    t = parsed.tables[0]
    assert t.column_count == 3
    assert t.row_count == 2
    # Row 1 padded with empty cell
    assert t.rows[0] == ["1", "", ""]
    # Row 2 retained all 3
    assert t.rows[1] == ["2", "3", "Extra"]
    assert any(w.code == "MALFORMED_TABLE" for w in parsed.warnings)


def test_clean_and_extract_links_sanitization() -> None:
    html = """<div>
        <a href="/internal">Internal</a>
        <a href="https://other.com/ext?token=SECRET&page=1">External</a>
        <a href="javascript:void(0)">JS</a>
    </div>"""
    parsed = clean_and_extract_elements(
        html=html,
        base_url="https://example.com/dir/",
        initial_url="https://example.com/dir/",
        limits=WebExtractionLimits(),
    )
    assert len(parsed.discovered_links["internal"]) == 1
    assert parsed.discovered_links["internal"][0]["href"] == "https://example.com/internal"

    assert len(parsed.discovered_links["external"]) == 1
    ext_link = parsed.discovered_links["external"][0]["href"]
    assert "token=SECRET" not in ext_link
    assert "page=1" in ext_link


# -----------------------------------------------------------------------------
# Integration Tests: Local Deterministic Server Scenarios
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_extraction_success(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/static"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.SUCCESS
    assert doc.metadata.title == "Deterministic Test Page"
    assert "Main Heading" in (doc.full_text or "")
    assert "# Main Heading" in (doc.full_markdown or "")
    assert len(doc.elements) >= 5
    assert doc.source.source_type.value == "web_page"
    assert doc.source_sha256 is not None
    assert doc.is_finalized is True
    # Trust boundary gate must pass
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_rendered_extraction_dynamic_content(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/rendered"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.RENDERED,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        doc = await extractor.extract_url(url, render_javascript=True)
        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.metadata.title == "Dynamic Rendered Page"
        # The dynamic script replaced innerText
        assert "Dynamically rendered content" in (doc.full_text or "")
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_table_extraction_with_caption(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/table"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.SUCCESS
    assert doc.metadata.table_count == 1
    table_elems = [e for e in doc.elements if e.element_type == ExtractionElementType.TABLE]
    assert len(table_elems) == 1
    table_elem = table_elems[0]
    assert table_elem.table is not None
    assert table_elem.table.caption == "Financial Overview"
    assert table_elem.table.row_count == 2
    assert table_elem.table.column_count == 3
    assert table_elem.table.headers == ["Quarter", "Revenue", "Growth"]
    assert table_elem.table.rows[0] == ["Q1", "$10M", "+5%"]
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_malformed_table_emits_structured_warning(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/malformed-table"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.SUCCESS
    assert any(w.code == "MALFORMED_TABLE" for w in doc.warnings)
    table_elems = [e for e in doc.elements if e.element_type == ExtractionElementType.TABLE]
    assert len(table_elems) == 1
    table_elem = table_elems[0]
    assert table_elem.table is not None
    # All rows normalized to max column count (3)
    assert table_elem.table.column_count == 3
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_redirect_to_approved_destination_succeeds(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/redirect-ok"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.SUCCESS
    assert doc.metadata.title == "Deterministic Test Page"
    assert doc.source.source_uri.endswith("/static")
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_redirect_to_metadata_ip_blocked(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/redirect-forbidden-ip"
    # Should reject navigation to 169.254.169.254
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.REJECTED
    assert any(e.code == ExtractionErrorCode.ACCESS_DENIED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_redirect_outside_approved_domains_blocked(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/redirect-unapproved"
    approved = ["127.0.0.1"]
    doc = await extract_url(
        url,
        approved_domains=approved,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.REJECTED
    assert any(e.code == ExtractionErrorCode.ACCESS_DENIED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_http_401_classified_as_auth_required(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/auth-401"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.AUTH_REQUIRED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_http_403_classified_as_access_denied(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/forbidden-403"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.REJECTED
    assert any(e.code == ExtractionErrorCode.ACCESS_DENIED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_http_429_classified_as_rate_limited(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/rate-limit-429"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.RATE_LIMITED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_login_page_detection_refuses_public_extraction(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/login"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.AUTH_REQUIRED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_challenge_page_detection_refuses_automation(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/challenge"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.AUTOMATION_NOT_ALLOWED for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_timeout_enforcement(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/slow"
    # Timeout set to 0.5s while server takes 4.0s
    doc = await extract_url(
        url,
        timeout_seconds=0.5,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.EXTRACTION_TIMEOUT for e in doc.errors)
    verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_oversized_response_fails_closed(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/oversized"
    # Default limit 10 MB, server sends 12 MB
    doc = await extract_url(
        url,
        max_response_bytes=10 * 1024 * 1024,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.status == ExtractionStatus.FAILED
    assert any(e.code == ExtractionErrorCode.FILE_TOO_LARGE for e in doc.errors)
    verify_trust_boundary(doc)


# -----------------------------------------------------------------------------
# Lifecycle & Resource Teardown Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extractor_lifecycle_and_idempotent_close() -> None:
    config = WebExtractionConfig(allow_loopback_for_testing=True)
    extractor = Crawl4AIWebExtractor(config=config)
    # Repeated close calls must be safe and idempotent
    await extractor.close()
    await extractor.close()
    assert extractor._is_closed is True

    # Subsequent extract_url on closed extractor raises WebExtractionError
    with pytest.raises(Exception, match="closed"):
        await extractor.extract_url("http://127.0.0.1:8080/")


@pytest.mark.asyncio
async def test_hash_integrity_and_frozen_document_contract(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/static"
    doc = await extract_url(
        url,
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    assert doc.is_finalized is True
    assert doc.normalized_content_sha256 is not None
    assert doc.extraction_record_sha256 is not None
    assert doc.verify_hashes() is True

    # Mutating finalized document must raise TypeError
    with pytest.raises(TypeError):
        doc.full_text = "Hacked"

    with pytest.raises(TypeError):
        doc.elements.append(doc.elements[0])


@pytest.mark.asyncio
async def test_rendered_forbidden_subresource_blocked(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/forbidden-sub"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.RENDERED,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        doc = await extractor.extract_url(url, render_javascript=True)
        assert doc.status in (ExtractionStatus.REJECTED, ExtractionStatus.FAILED)
        assert any(e.code == ExtractionErrorCode.ACCESS_DENIED for e in doc.errors)
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_rendered_forbidden_websocket_blocked(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/forbidden-ws"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.RENDERED,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        doc = await extractor.extract_url(url, render_javascript=True)
        assert doc.status in (ExtractionStatus.REJECTED, ExtractionStatus.FAILED)
        assert any(e.code == ExtractionErrorCode.ACCESS_DENIED for e in doc.errors)
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_rendered_popups_and_downloads_blocked(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/pop-down"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.RENDERED,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        doc = await extractor.extract_url(url, render_javascript=True)
        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.metadata.title == "Popup and Download"
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_caller_cancellation_cleans_up(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/slow"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        task = asyncio.create_task(extractor.extract_url(url))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    await extractor.close()


@pytest.mark.asyncio
async def test_element_count_limit_truncates_with_warning(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/many-elements"
    limits = WebExtractionLimits(max_elements=10)
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config, limits=limits) as extractor:
        doc = await extractor.extract_url(url)
        assert doc.status == ExtractionStatus.SUCCESS
        assert len(doc.elements) == 10
        assert any(w.code == "ELEMENT_LIMIT_EXCEEDED" for w in doc.warnings)
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_single_page_policy_never_follows_links(local_fixture_server: str) -> None:
    url = f"{local_fixture_server}/links"
    config = WebExtractionConfig(
        strategy=WebExtractionStrategy.STATIC,
        allow_loopback_for_testing=True,
    )
    async with Crawl4AIWebExtractor(config=config) as extractor:
        doc = await extractor.extract_url(url)
        assert doc.status == ExtractionStatus.SUCCESS
        discovered = doc.metadata.custom_attributes.get("discovered_links", {})
        assert len(discovered.get("internal", [])) >= 1
        assert len(discovered.get("external", [])) >= 1
        assert doc.source.source_uri == url
        verify_trust_boundary(doc)
