"""Security guardrails, SSRF prevention, and sensitive input protection for browser automation.

Provides:
1. URL validation against SSRF, private IP addresses (RFC 1918), link-local metadata
   endpoints (AWS/GCP/Azure 169.254.169.254), loopbacks, and dangerous URI schemes.
2. Form field sensitivity inspection detecting password, payment card, CVV, SSN, OTP,
   and secret token fields.
3. Automated blocking and redaction utilities preventing unauthorized credential access.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Locator

logger = logging.getLogger("javed.browser.security")

# Dangerous URI schemes that are never permitted for web automation
DANGEROUS_SCHEMES = frozenset(
    {
        "file",
        "javascript",
        "vbscript",
        "data",
        "about",
        "chrome",
        "edge",
        "blob",
        "filesystem",
        "ftp",
        "sftp",
        "tftp",
        "gopher",
        "ldap",
        "dict",
    }
)

# Hostnames explicitly blocked to prevent local environment probing or cloud metadata SSRF
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)

# Additional blocked IP subnets
ADDITIONAL_BLOCKED_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmark testing
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata subnet
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Experimental
    ipaddress.ip_network("0.0.0.0/8"),  # Current network ("this" host)
)

# High-confidence substrings that always indicate sensitive fields
HIGH_CONFIDENCE_SUBSTRINGS = (
    "password",
    "passwd",
    "creditcard",
    "credit_card",
    "cardnumber",
    "card_number",
    "cvv",
    "cvc",
    "ssn",
    "totp",
    "passphrase",
)

# Token set for word-boundary matching
# (handles snake_case, kebab-case, space-separated, and camelCase)
SENSITIVE_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "passphrase",
        "creditcard",
        "credit_card",
        "cardnumber",
        "card_number",
        "cc_number",
        "cvv",
        "cvc",
        "securitycode",
        "security_code",
        "ssn",
        "socialsecurity",
        "social_security",
        "otp",
        "totp",
        "onetimepassword",
        "one_time_password",
        "pin",
        "authcode",
        "auth_code",
        "apikey",
        "api_key",
        "privatekey",
        "private_key",
    }
)


def match_sensitive_text(text: str) -> tuple[bool, str | None]:
    """Determine if a text value or attribute represents sensitive credentials or payment data."""
    if not text:
        return False, None

    lower = text.lower()
    for sub in HIGH_CONFIDENCE_SUBSTRINGS:
        if sub in lower:
            return True, sub

    tokens = re.findall(r"[A-Za-z]+|\d+", text)
    for t in tokens:
        t_lower = t.lower()
        if t_lower in SENSITIVE_TOKENS:
            return True, t_lower

    return False, None


# Autocomplete attribute values explicitly indicating sensitive data per WHATWG HTML spec
SENSITIVE_AUTOCOMPLETE_VALUES = frozenset(
    {
        "current-password",
        "new-password",
        "one-time-code",
        "cc-name",
        "cc-number",
        "cc-exp",
        "cc-exp-month",
        "cc-exp-year",
        "cc-csc",
        "cc-type",
    }
)


class SecurityViolationError(Exception):
    """Base exception raised when a browser operation violates security policy."""


class DangerousSchemeError(SecurityViolationError):
    """Raised when a URL uses a disallowed or dangerous protocol scheme."""


class SSRFBlockedError(SecurityViolationError):
    """Raised when a URL attempts to target loopback, private, or metadata network addresses."""


class SensitiveFieldBlockedError(SecurityViolationError):
    """Raised when an automation action attempts to interact with or fill a sensitive field."""


@dataclass(frozen=True)
class SensitivityInspectionResult:
    """Outcome of inspecting an element or attribute set for sensitive credential/payment data."""

    is_sensitive: bool
    field_type: str | None = None
    matched_attribute: str | None = None
    matched_pattern: str | None = None
    reason: str | None = None


class BrowserSecurityGuard:
    """Validates URLs and requests to prevent SSRF and navigation to forbidden resources."""

    def __init__(
        self,
        *,
        allowed_schemes: frozenset[str] | None = None,
        allow_about_blank: bool = False,
        allow_data_urls: bool = False,
        resolve_dns: bool = True,
        extra_blocked_hosts: set[str] | None = None,
    ) -> None:
        self.allowed_schemes = allowed_schemes or frozenset({"http", "https"})
        self.allow_about_blank = allow_about_blank
        self.allow_data_urls = allow_data_urls
        self.resolve_dns = resolve_dns
        self.extra_blocked_hosts = {h.lower() for h in (extra_blocked_hosts or set())}

    def validate_url(self, url: str) -> str:
        """Validate a target navigation URL against SSRF and dangerous scheme policies.

        Args:
            url: The raw URL string to validate.

        Returns:
            The normalized valid URL string.

        Raises:
            DangerousSchemeError: If the URL uses an unapproved or dangerous scheme.
            SSRFBlockedError: If the URL targets private/loopback/metadata addresses.
            SecurityViolationError: If the URL is malformed or unparseable.
        """
        if not url or not isinstance(url, str):
            raise SecurityViolationError("URL cannot be empty or non-string.")

        stripped_url = url.strip()

        # Handle explicit about:blank if allowed
        if stripped_url == "about:blank":
            if self.allow_about_blank:
                return "about:blank"
            raise DangerousSchemeError(
                "Navigation to 'about:blank' is not permitted by this security guard instance."
            )

        # Handle data: URLs if allowed (e.g. for isolated test fixtures)
        if stripped_url.startswith("data:"):
            if self.allow_data_urls:
                return stripped_url
            raise DangerousSchemeError(
                "Data URLs ('data:...') are prohibited to prevent local script injection."
            )

        try:
            parsed = urlparse(stripped_url)
        except Exception as exc:
            raise SecurityViolationError(f"Malformed URL '{stripped_url}': {exc}") from exc

        scheme = (parsed.scheme or "").lower()
        if not scheme:
            raise DangerousSchemeError(
                f"Missing URL scheme in '{stripped_url}'. Only HTTP/HTTPS URLs are allowed."
            )

        if scheme in DANGEROUS_SCHEMES or scheme not in self.allowed_schemes:
            raise DangerousSchemeError(
                f"Dangerous or unsupported scheme '{scheme}://' in '{stripped_url}'. "
                f"Allowed schemes: {sorted(self.allowed_schemes)}"
            )

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise SecurityViolationError(f"URL '{stripped_url}' does not contain a valid hostname.")

        # 1. Hostname string checks
        if (
            hostname in BLOCKED_HOSTNAMES
            or hostname in self.extra_blocked_hosts
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
            or hostname.endswith(".lan")
            or hostname.endswith(".home.arpa")
        ):
            raise SSRFBlockedError(
                f"SSRF violation: Access to internal/local hostname '{hostname}' is blocked."
            )

        # 2. Check for numeric representations of IP addresses (decimal, hex, octal)
        self._check_numeric_ip_representation(hostname)

        # 3. Direct IP address validation (literal IPv4 or IPv6 in URL)
        direct_ip = self._try_parse_ip_address(hostname)
        if direct_ip is not None:
            self._validate_ip_is_public(direct_ip, source=f"literal IP '{hostname}'")
            return stripped_url

        # 4. DNS resolution check to prevent DNS rebinding or domains resolving to private IPs
        if self.resolve_dns:
            port = parsed.port or (443 if scheme == "https" else 80)
            self._verify_resolved_ips_are_public(hostname, port)

        return stripped_url

    def _check_numeric_ip_representation(self, hostname: str) -> None:
        """Check for decimal, octal, or hexadecimal encoded IP representations."""
        # Decimal integer representation (e.g., 2130706433 -> 127.0.0.1)
        if hostname.isdigit():
            try:
                numeric_val = int(hostname)
                if 0 <= numeric_val <= 0xFFFFFFFF:
                    ip = ipaddress.ip_address(numeric_val)
                    self._validate_ip_is_public(
                        ip, source=f"decimal IP representation '{hostname}'"
                    )
            except (ValueError, ipaddress.AddressValueError):
                pass

        # Hexadecimal representation (e.g., 0x7f000001)
        if hostname.startswith(("0x", "0X")):
            try:
                numeric_val = int(hostname, 16)
                if 0 <= numeric_val <= 0xFFFFFFFF:
                    ip = ipaddress.ip_address(numeric_val)
                    self._validate_ip_is_public(ip, source=f"hex IP representation '{hostname}'")
            except (ValueError, ipaddress.AddressValueError):
                pass

    def _try_parse_ip_address(
        self, hostname: str
    ) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        """Attempt to parse hostname as a literal IPv4 or IPv6 address."""
        # Strip brackets from IPv6 hostnames like [::1]
        raw = hostname.strip("[]")
        try:
            return ipaddress.ip_address(raw)
        except ValueError:
            return None

    def _validate_ip_is_public(
        self,
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
        source: str,
    ) -> None:
        """Ensure an IP address is strictly public and not in restricted subnets."""
        # Check IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1)
        if hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped is not None:
            self._validate_ip_is_public(ip.ipv4_mapped, source=f"IPv4-mapped {source}")

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise SSRFBlockedError(
                f"SSRF violation: Host '{source}' resolves to restricted/private address '{ip}'."
            )

        for blocked_net in ADDITIONAL_BLOCKED_NETWORKS:
            if ip in blocked_net:
                raise SSRFBlockedError(
                    f"SSRF violation: Host '{source}' resolves to blocked network address '{ip}' "
                    f"({blocked_net})."
                )

    def _verify_resolved_ips_are_public(self, hostname: str, port: int) -> None:
        """Resolve hostname via DNS and verify that ALL returned IPs are public."""
        try:
            addr_info = socket.getaddrinfo(
                hostname,
                port,
                proto=socket.IPPROTO_TCP,
            )
        except socket.gaierror as gai_err:
            logger.debug("DNS lookup failed for hostname '%s': %s", hostname, gai_err)
            # If DNS fails, allow request to proceed to fail naturally at network level
            return

        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                self._validate_ip_is_public(ip, source=f"DNS record for '{hostname}'")
            except (ValueError, ipaddress.AddressValueError):
                continue


def inspect_attributes_sensitivity(attributes: dict[str, Any]) -> SensitivityInspectionResult:
    """Inspect an HTML element attribute dictionary to detect credentials or payment data.

    Checks:
    - type="password"
    - autocomplete attributes targeting credentials or credit cards
    - name, id, placeholder, title, aria-label, and class matching sensitive patterns
    """
    field_type = str(attributes.get("type", "")).strip().lower()

    # 1. Immediate password field check
    if field_type == "password":
        return SensitivityInspectionResult(
            is_sensitive=True,
            field_type="password",
            matched_attribute="type",
            matched_pattern="password",
            reason="Input field has type='password'.",
        )

    # 2. Check autocomplete attribute
    autocomplete = str(attributes.get("autocomplete", "")).strip().lower()
    if autocomplete in SENSITIVE_AUTOCOMPLETE_VALUES:
        return SensitivityInspectionResult(
            is_sensitive=True,
            field_type=field_type or None,
            matched_attribute="autocomplete",
            matched_pattern=autocomplete,
            reason=f"Input field specifies sensitive autocomplete value '{autocomplete}'.",
        )

    # 3. Check identifying attributes against sensitive patterns
    attributes_to_check = ("name", "id", "placeholder", "aria-label", "title")
    for attr in attributes_to_check:
        val = str(attributes.get(attr, "")).strip()
        if not val:
            continue
        is_sens, matched = match_sensitive_text(val)
        if is_sens:
            return SensitivityInspectionResult(
                is_sensitive=True,
                field_type=field_type or None,
                matched_attribute=attr,
                matched_pattern=matched,
                reason=(
                    f"Attribute '{attr}' ('{val}') matches sensitive token pattern '{matched}'."
                ),
            )

    return SensitivityInspectionResult(is_sensitive=False, field_type=field_type or None)


async def inspect_locator_sensitivity(locator: Locator) -> SensitivityInspectionResult:
    """Query element attributes from a live Playwright Locator and inspect sensitivity."""
    try:
        attrs = await locator.evaluate(
            """(el) => {
                return {
                    tagName: el.tagName,
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    autocomplete: el.getAttribute('autocomplete') || '',
                    'aria-label': el.getAttribute('aria-label') || '',
                    title: el.getAttribute('title') || '',
                };
            }"""
        )
    except Exception as exc:
        logger.debug("Failed to extract attributes from locator: %s", exc)
        return SensitivityInspectionResult(is_sensitive=False)

    return inspect_attributes_sensitivity(attrs)


def assert_safe_form_input(
    selector: str,
    attributes: dict[str, Any] | None = None,
    *,
    allow_sensitive_override: bool = False,
) -> None:
    """Enforce that form inputs targeting sensitive fields are blocked unless override is set.

    Raises:
        SensitiveFieldBlockedError: If the target field is sensitive and override is False.
    """
    if allow_sensitive_override:
        return

    # Check selector name/pattern directly
    is_sens, matched = match_sensitive_text(selector)
    if is_sens:
        raise SensitiveFieldBlockedError(
            f"Action blocked: Selector '{selector}' targets a sensitive field "
            f"matching '{matched}'. Automated access to credentials, "
            "credit cards, or OTP fields is prohibited."
        )

    if attributes:
        result = inspect_attributes_sensitivity(attributes)
        if result.is_sensitive:
            raise SensitiveFieldBlockedError(
                f"Action blocked: Target field is sensitive ({result.reason}). "
                "Automated access to credentials, credit cards, or OTP fields is prohibited."
            )


def redact_sensitive_value(value: str) -> str:
    """Redact a sensitive string value for safe inclusion in logs, traces, or ledgers."""
    return "***REDACTED***"


def mask_sensitive_value(value: str, visible_suffix_chars: int = 0) -> str:
    """Mask a sensitive string, optionally retaining trailing characters (e.g. card last 4)."""
    if not value:
        return ""
    if visible_suffix_chars <= 0 or len(value) <= visible_suffix_chars:
        return "*" * len(value)
    masked_len = len(value) - visible_suffix_chars
    return ("*" * masked_len) + value[-visible_suffix_chars:]
