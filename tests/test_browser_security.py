"""Unit and integration tests for browser security guardrails and sensitive input protection.

Verifies:
1. SSRF prevention blocking RFC 1918 subnets, loopbacks, link-local, and cloud metadata.
2. Dangerous URI scheme blocking (file://, javascript://, data://, vbscript://, etc.).
3. Allowance and validation of safe, public external URLs.
4. Detection of sensitive form inputs (passwords, credit cards, CVVs, OTPs) from attributes.
5. Automated action blocking via assert_safe_form_input.
6. Value redaction and masking utilities.
7. Live DOM sensitivity inspection with Playwright locators.
"""

from __future__ import annotations

import pytest

from javed.browser.engine import BrowserEngineManager
from javed.browser.security import (
    BrowserSecurityGuard,
    DangerousSchemeError,
    SecurityViolationError,
    SensitiveFieldBlockedError,
    SSRFBlockedError,
    assert_safe_form_input,
    inspect_attributes_sensitivity,
    inspect_locator_sensitivity,
    mask_sensitive_value,
    redact_sensitive_value,
)


def test_ssrf_blocks_private_rfc1918_ips() -> None:
    """Verify that RFC 1918 private subnets are blocked immediately."""
    guard = BrowserSecurityGuard(resolve_dns=False)

    private_urls = [
        "http://10.0.0.1/",
        "http://10.254.0.1:8080/admin",
        "http://172.16.0.1/",
        "http://172.31.255.255/internal",
        "http://192.168.0.1/",
        "http://192.168.1.254:8443/api",
    ]

    for url in private_urls:
        with pytest.raises(SSRFBlockedError) as exc_info:
            guard.validate_url(url)
        assert "restricted/private address" in str(exc_info.value)


def test_ssrf_blocks_loopback_addresses() -> None:
    """Verify that loopback addresses and hostnames are blocked."""
    guard = BrowserSecurityGuard(resolve_dns=False)

    loopback_urls = [
        "http://127.0.0.1/",
        "http://127.0.0.2:8000/",
        "http://127.1.2.3:3000/status",
        "http://localhost/",
        "http://localhost:5173/app",
        "http://service.localhost/",
        "http://[::1]/",
        "http://[::1]:8080/admin",
    ]

    for url in loopback_urls:
        with pytest.raises(SSRFBlockedError) as exc_info:
            guard.validate_url(url)
        assert "SSRF violation" in str(exc_info.value)


def test_ssrf_blocks_cloud_metadata_endpoints() -> None:
    """Verify that link-local cloud metadata IP addresses and hostnames are blocked."""
    guard = BrowserSecurityGuard(resolve_dns=False)

    metadata_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://169.254.1.1:8000/",
        "http://metadata.google.internal/",
        "http://instance-data/latest/meta-data",
    ]

    for url in metadata_urls:
        with pytest.raises(SSRFBlockedError) as exc_info:
            guard.validate_url(url)
        assert "SSRF violation" in str(exc_info.value)


def test_ssrf_blocks_numeric_encoded_ips() -> None:
    """Verify that decimal and hex numeric representations of loopback/private IPs are blocked."""
    guard = BrowserSecurityGuard(resolve_dns=False)

    # 2130706433 is decimal representation of 127.0.0.1
    with pytest.raises(SSRFBlockedError) as exc_info:
        guard.validate_url("http://2130706433/")
    assert "SSRF violation" in str(exc_info.value)

    # 0x7f000001 is hexadecimal representation of 127.0.0.1
    with pytest.raises(SSRFBlockedError) as exc_info2:
        guard.validate_url("http://0x7f000001/")
    assert "SSRF violation" in str(exc_info2.value)


def test_dangerous_schemes_rejected() -> None:
    """Verify that non-web protocol schemes are blocked with DangerousSchemeError."""
    guard = BrowserSecurityGuard()

    dangerous_urls = [
        "file:///C:/Windows/System32/drivers/etc/hosts",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "vbscript:msgbox(1)",
        "data:text/html,<script>alert(1)</script>",
        "about:config",
        "chrome://settings",
        "ftp://ftp.example.com/files",
        "sftp://sftp.example.com/data",
    ]

    for url in dangerous_urls:
        with pytest.raises(DangerousSchemeError) as exc_info:
            guard.validate_url(url)
        assert "Dangerous or unsupported scheme" in str(exc_info.value) or "prohibited" in str(
            exc_info.value
        )


def test_allow_safe_public_urls() -> None:
    """Verify that standard public web URLs pass validation."""
    guard = BrowserSecurityGuard(resolve_dns=True)

    safe_urls = [
        "https://example.com",
        "https://example.com/index.html?ref=123",
        "http://example.org:8080/path",
    ]

    for url in safe_urls:
        validated = guard.validate_url(url)
        assert validated == url


def test_about_blank_and_data_url_toggle() -> None:
    """Verify explicit toggles for about:blank and data URLs (for test contexts)."""
    strict_guard = BrowserSecurityGuard()
    with pytest.raises(DangerousSchemeError):
        strict_guard.validate_url("about:blank")
    with pytest.raises(DangerousSchemeError):
        strict_guard.validate_url("data:text/html,<h1>Test</h1>")

    test_guard = BrowserSecurityGuard(allow_about_blank=True, allow_data_urls=True)
    assert test_guard.validate_url("about:blank") == "about:blank"
    assert test_guard.validate_url("data:text/html,<h1>Test</h1>") == "data:text/html,<h1>Test</h1>"


def test_malformed_urls_rejected() -> None:
    """Verify malformed or empty URLs raise SecurityViolationError."""
    guard = BrowserSecurityGuard()

    with pytest.raises(SecurityViolationError):
        guard.validate_url("")

    with pytest.raises(DangerousSchemeError):
        guard.validate_url("example.com")  # Missing scheme


def test_sensitive_field_detection_attributes() -> None:
    """Verify sensitivity inspection across various HTML element attribute patterns."""
    # 1. Type password
    res = inspect_attributes_sensitivity({"type": "password", "name": "pwd"})
    assert res.is_sensitive
    assert res.matched_attribute == "type"

    # 2. Name containing password
    res = inspect_attributes_sensitivity({"type": "text", "name": "user_password"})
    assert res.is_sensitive
    assert res.matched_attribute == "name"

    # 3. Credit card number in ID
    res = inspect_attributes_sensitivity({"type": "text", "id": "credit_card_number"})
    assert res.is_sensitive
    assert res.matched_attribute == "id"

    # 4. CVV in placeholder
    res = inspect_attributes_sensitivity({"type": "text", "placeholder": "Enter CVV"})
    assert res.is_sensitive
    assert res.matched_attribute == "placeholder"

    # 5. Sensitive autocomplete
    res = inspect_attributes_sensitivity({"type": "text", "autocomplete": "cc-csc"})
    assert res.is_sensitive
    assert res.matched_attribute == "autocomplete"

    # 6. OTP in aria-label
    res = inspect_attributes_sensitivity({"type": "text", "aria-label": "One-Time Password (OTP)"})
    assert res.is_sensitive
    assert res.matched_attribute == "aria-label"

    # 7. Safe non-sensitive input
    safe_res = inspect_attributes_sensitivity(
        {"type": "text", "name": "search_query", "placeholder": "Search documentation..."}
    )
    assert not safe_res.is_sensitive


def test_assert_safe_form_input_enforcement() -> None:
    """Verify assert_safe_form_input raises SensitiveFieldBlockedError on sensitive inputs."""
    # Direct selector match
    with pytest.raises(SensitiveFieldBlockedError) as exc_info:
        assert_safe_form_input("#password-input")
    assert "Automated access to credentials" in str(exc_info.value)

    # Attribute match
    with pytest.raises(SensitiveFieldBlockedError) as exc_info2:
        assert_safe_form_input("#field-1", attributes={"type": "password"})
    assert "Target field is sensitive" in str(exc_info2.value)

    # Override flag allows operation
    assert_safe_form_input("#password-input", allow_sensitive_override=True)

    # Safe field succeeds without error
    assert_safe_form_input("#search", attributes={"type": "text", "name": "query"})


def test_redact_and_mask_utilities() -> None:
    """Verify string redaction and masking helpers."""
    assert redact_sensitive_value("secret_token_12345") == "***REDACTED***"
    assert mask_sensitive_value("1234567890123456", visible_suffix_chars=4) == "************3456"
    assert mask_sensitive_value("secret", visible_suffix_chars=0) == "******"
    assert mask_sensitive_value("") == ""


@pytest.mark.asyncio
async def test_live_locator_sensitivity_inspection() -> None:
    """Verify sensitivity inspection on real Playwright DOM elements."""
    html_page = """
    <!DOCTYPE html>
    <html>
        <body>
            <form id="login-form">
                <input id="user-input" type="text" name="username" placeholder="Username" />
                <input id="pass-input" type="password" name="password" />
                <input id="card-input" type="text" autocomplete="cc-number" />
                <input id="cvv-input" type="text" placeholder="CVV" />
            </form>
        </body>
    </html>
    """

    async with BrowserEngineManager(headless=True) as engine:
        async with engine.ephemeral_page() as page:
            await page.set_content(html_page)

            # Inspect safe username input
            user_loc = page.locator("#user-input")
            user_res = await inspect_locator_sensitivity(user_loc)
            assert not user_res.is_sensitive

            # Inspect password input
            pass_loc = page.locator("#pass-input")
            pass_res = await inspect_locator_sensitivity(pass_loc)
            assert pass_res.is_sensitive
            assert pass_res.matched_attribute == "type"

            # Inspect credit card input
            card_loc = page.locator("#card-input")
            card_res = await inspect_locator_sensitivity(card_loc)
            assert card_res.is_sensitive
            assert card_res.matched_attribute == "autocomplete"

            # Inspect CVV input
            cvv_loc = page.locator("#cvv-input")
            cvv_res = await inspect_locator_sensitivity(cvv_loc)
            assert cvv_res.is_sensitive
            assert cvv_res.matched_attribute in {"id", "placeholder"}
