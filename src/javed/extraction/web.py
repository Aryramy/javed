"""Bounded, deterministic public-web extraction subsystem using Crawl4AI 0.9.5.

Conforms to BRICK-007 Stage 4 specifications:
1. Bounded, single-page public web acquisition (max depth: 0, max pages: 1).
2. Zero trust URL validation & SSRF prevention (RFC 1918, loopbacks, link-local metadata).
3. Request-time and redirect-time enforcement via Playwright request and WebSocket routing.
4. Two explicit execution modes: STATIC (non-browser) and RENDERED (controlled dynamic browser).
5. HTML-to-Markdown, visible-text extraction, structured element hierarchy, and table mapping.
6. Safe discovered-link sanitization without link following or speculative prefetching.
7. Anti-bot, challenge, and authentication classification without credential capture or bypass.
8. Strict resource bounds (10 MB main doc, 25 MB total, element and char counts).
9. Output mapped to canonical NormalizedDocument, finalized, and verified against trust gates.
10. Natural lifecycle management with zero os._exit usage and zero process leaks.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp
import certifi
from bs4 import BeautifulSoup, Tag
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Route, WebSocketRoute

from javed.browser.security import (
    BrowserSecurityGuard,
    DangerousSchemeError,
    SecurityViolationError,
    SSRFBlockedError,
)
from javed.extraction.schema import (
    DocumentMetadata,
    ElementProvenance,
    ExtractionElement,
    ExtractionElementType,
    ExtractionError,
    ExtractionErrorCode,
    ExtractionStatus,
    ExtractionWarning,
    ExtractorDescriptor,
    NormalizedDocument,
    SectionReference,
    SourceDescriptor,
    SourceType,
    TableRepresentation,
    verify_trust_boundary,
)

# Suppress Crawl4AI cloud promotion notice
os.environ["CRAWL4AI_NO_CLOUD_NOTICE"] = "1"

logger = logging.getLogger("javed.extraction.web")

# -----------------------------------------------------------------------------
# Constants & Governance Boundaries
# -----------------------------------------------------------------------------

CRAWL4AI_ENGINE_NAME = "crawl4ai"
CRAWL4AI_ENGINE_VERSION = "0.9.5"

DEFAULT_MAX_MAIN_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_TOTAL_RESPONSE_BYTES = 25 * 1024 * 1024  # 25 MB
DEFAULT_MAX_HTML_CHARS = 2_000_000
DEFAULT_MAX_MARKDOWN_CHARS = 500_000
DEFAULT_MAX_TEXT_CHARS = 500_000
DEFAULT_MAX_ELEMENTS = 10_000
DEFAULT_MAX_DISCOVERED_LINKS = 2_000
DEFAULT_MAX_METADATA_VALUE_LENGTH = 4_096
DEFAULT_MAX_WARNINGS = 100

DEFAULT_NAVIGATION_TIMEOUT_SECONDS = 20.0
DEFAULT_EXTRACTION_TIMEOUT_SECONDS = 30.0
DEFAULT_MIN_DOMAIN_INTERVAL_SECONDS = 0.5
DEFAULT_MAX_CONCURRENT_CRAWLS = 5

SECRET_KEYWORD_REGEX = re.compile(
    r"(token|api_key|apikey|secret|password|passwd|pwd|auth|credential|session|access_token|private_key)",
    re.IGNORECASE,
)

CHALLENGE_SUBSTRINGS = (
    "just a moment...",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "cf-turnstile",
    "challenge-platform",
    "hcaptcha",
    "recaptcha",
    "perimeterx",
    "datadome",
    "arkoselabs",
)


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class WebExtractionError(Exception):
    """Base exception for web extraction failures."""


class WebExtractionSecurityError(WebExtractionError):
    """Raised when URL or request violates security or approved-domain policy."""


class WebExtractionTimeoutError(WebExtractionError):
    """Raised when extraction operation exceeds timeout."""


class WebExtractionLimitExceededError(WebExtractionError):
    """Raised when downloaded response size exceeds governance ceilings."""


# -----------------------------------------------------------------------------
# Enums and Dataclasses
# -----------------------------------------------------------------------------


class WebExtractionStrategy(StrEnum):
    """Explicit execution strategy for web extraction."""

    STATIC = "static"
    RENDERED = "rendered"


@dataclass(frozen=True)
class WebExtractionLimits:
    """Configurable boundaries and resource limits for web extraction."""

    max_main_document_bytes: int = DEFAULT_MAX_MAIN_DOCUMENT_BYTES
    max_total_response_bytes: int = DEFAULT_MAX_TOTAL_RESPONSE_BYTES
    max_html_chars: int = DEFAULT_MAX_HTML_CHARS
    max_markdown_chars: int = DEFAULT_MAX_MARKDOWN_CHARS
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    max_elements: int = DEFAULT_MAX_ELEMENTS
    max_discovered_links: int = DEFAULT_MAX_DISCOVERED_LINKS
    max_metadata_value_length: int = DEFAULT_MAX_METADATA_VALUE_LENGTH
    max_warnings: int = DEFAULT_MAX_WARNINGS
    fail_closed_on_overflow: bool = True


@dataclass(frozen=True)
class WebExtractionConfig:
    """Configuration settings for web extraction."""

    strategy: WebExtractionStrategy = WebExtractionStrategy.STATIC
    approved_domains: tuple[str, ...] = ()
    timeout_seconds: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    page_timeout_seconds: float = DEFAULT_NAVIGATION_TIMEOUT_SECONDS
    min_domain_interval_seconds: float = DEFAULT_MIN_DOMAIN_INTERVAL_SECONDS
    max_concurrent_crawls: int = DEFAULT_MAX_CONCURRENT_CRAWLS
    cache_mode: CacheMode = CacheMode.BYPASS
    allow_loopback_for_testing: bool = False
    raise_on_error: bool = False


# -----------------------------------------------------------------------------
# Security & URL Validation
# -----------------------------------------------------------------------------


def _matches_approved_domain(hostname: str, approved_domains: Sequence[str]) -> str | None:
    """Check if a hostname matches or is a subdomain of an approved domain."""
    norm_host = hostname.strip().lower()
    for approved in approved_domains:
        norm_approved = approved.strip().lower()
        if norm_host == norm_approved or norm_host.endswith("." + norm_approved):
            return norm_approved
    return None


def validate_web_url(
    url: str,
    *,
    approved_domains: Sequence[str] | None = None,
    allow_loopback_for_testing: bool = False,
) -> str:
    """Validate a target web URL against scheme, SSRF, secret, and domain policies.

    Args:
        url: The candidate URL string.
        approved_domains: Optional list of approved domains. If provided, the URL's
            hostname must match an approved domain or subdomain.
        allow_loopback_for_testing: Explicit test-only override to permit loopback URLs.
            Must be False in all production operations.

    Returns:
        The validated and normalized URL string.

    Raises:
        WebExtractionSecurityError: If URL fails validation.
    """
    if not url or not isinstance(url, str):
        raise WebExtractionSecurityError("Target URL cannot be empty or non-string.")

    stripped = url.strip()
    try:
        parsed = urlsplit(stripped)
    except Exception as exc:
        raise WebExtractionSecurityError(f"Malformed URL {stripped!r}: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise WebExtractionSecurityError(
            f"Unsupported scheme {scheme!r} in {stripped!r}. Only HTTP/HTTPS permitted."
        )

    if parsed.username or parsed.password:
        raise WebExtractionSecurityError(
            f"Embedded credentials in target URL are prohibited: {stripped!r}"
        )

    # Check path traversal
    if ".." in parsed.path:
        raise WebExtractionSecurityError(f"Path traversal ('..') is prohibited: {stripped!r}")

    # Check query string for sensitive parameters
    if parsed.query:
        params = parse_qs(parsed.query)
        for key in params:
            if SECRET_KEYWORD_REGEX.search(key):
                raise WebExtractionSecurityError(
                    f"Prohibited secret-bearing parameter in query string: {key!r}"
                )

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise WebExtractionSecurityError(f"URL {stripped!r} does not contain a valid hostname.")

    # Domain allowlist check
    if approved_domains:
        matched_domain = _matches_approved_domain(hostname, approved_domains)
        if not matched_domain:
            raise WebExtractionSecurityError(
                f"Domain '{hostname}' is not in approved domains: {list(approved_domains)}"
            )

    # SSRF & IP validation
    if allow_loopback_for_testing:
        # Under test mode, loopback (127.0.0.1, localhost) is permitted for local fixture servers,
        # but cloud metadata (169.254.169.254) remains strictly blocked.
        guard = BrowserSecurityGuard(
            allowed_schemes=frozenset({"http", "https"}),
            resolve_dns=False,
            extra_blocked_hosts={"169.254.169.254", "metadata.google.internal"},
        )
        try:
            guard.validate_url(stripped)
        except SSRFBlockedError as exc:
            # Re-raise if targeting metadata
            if "169.254" in str(exc) or "metadata" in str(exc):
                raise WebExtractionSecurityError(f"SSRF violation: {exc}") from exc
        except (DangerousSchemeError, SecurityViolationError) as exc:
            raise WebExtractionSecurityError(f"Security violation: {exc}") from exc
    else:
        # Production mode: full SSRF checking with DNS resolution
        guard = BrowserSecurityGuard(
            allowed_schemes=frozenset({"http", "https"}),
            resolve_dns=True,
        )
        try:
            guard.validate_url(stripped)
        except (SSRFBlockedError, DangerousSchemeError, SecurityViolationError) as exc:
            raise WebExtractionSecurityError(f"SSRF or security violation: {exc}") from exc

    return stripped


# -----------------------------------------------------------------------------
# Rate Limiting & Concurrency Manager
# -----------------------------------------------------------------------------


class DomainRateLimiter:
    """Manages polite per-domain request intervals and concurrency bounds."""

    def __init__(self, min_interval_seconds: float = DEFAULT_MIN_DOMAIN_INTERVAL_SECONDS) -> None:
        self.min_interval = min_interval_seconds
        self._last_access: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}

    def get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Get or create a domain-level concurrency semaphore (default 1)."""
        norm = domain.strip().lower()
        if norm not in self._domain_semaphores:
            self._domain_semaphores[norm] = asyncio.Semaphore(1)
        return self._domain_semaphores[norm]

    async def throttle(self, domain: str, retry_after: float | None = None) -> None:
        """Throttle requests to respect min_interval and Retry-After headers."""
        norm = domain.strip().lower()
        async with self._lock:
            now = asyncio.get_event_loop().time()
            last = self._last_access.get(norm, 0.0)
            wait_time = 0.0

            if retry_after is not None and retry_after > 0:
                wait_time = max(wait_time, retry_after)
            elif (now - last) < self.min_interval:
                wait_time = max(wait_time, self.min_interval - (now - last))

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self._last_access[norm] = asyncio.get_event_loop().time()


# -----------------------------------------------------------------------------
# HTML Content Cleaning & Element Mapping
# -----------------------------------------------------------------------------


@dataclass
class ParsedWebPage:
    """Intermediate structured representation of an extracted web page."""

    title: str | None
    meta_description: str | None
    meta_author: str | None
    created_at: datetime | None
    modified_at: datetime | None
    full_text: str
    full_markdown: str
    elements: list[ExtractionElement]
    tables: list[TableRepresentation]
    discovered_links: dict[str, list[dict[str, Any]]]
    warnings: list[ExtractionWarning]
    errors: list[ExtractionError]
    is_challenge_page: bool = False
    is_login_page: bool = False


def clean_and_extract_elements(
    html: str,
    base_url: str,
    initial_url: str,
    limits: WebExtractionLimits,
) -> ParsedWebPage:
    """Parse HTML, extract structured elements, sanitize links, and detect challenges."""
    soup = BeautifulSoup(html, "html.parser")
    warnings: list[ExtractionWarning] = []
    errors: list[ExtractionError] = []

    # 1. Page Title & Metadata
    title = None
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()[: limits.max_metadata_value_length]

    meta_desc = None
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if desc_tag and desc_tag.get("content"):
        meta_desc = str(desc_tag.get("content")).strip()[: limits.max_metadata_value_length]

    meta_author = None
    author_tag = soup.find("meta", attrs={"name": re.compile(r"^author$", re.I)})
    if author_tag and author_tag.get("content"):
        meta_author = str(author_tag.get("content")).strip()[: limits.max_metadata_value_length]

    # Timestamps from OpenGraph / Dublin Core if present
    created_at = None
    time_tag = soup.find("meta", attrs={"property": re.compile(r"published_time$", re.I)})
    if time_tag and time_tag.get("content"):
        try:
            created_at = datetime.fromisoformat(
                str(time_tag.get("content")).replace("Z", "+00:00")
            ).astimezone(UTC)
        except Exception:
            pass

    modified_at = None
    mod_tag = soup.find("meta", attrs={"property": re.compile(r"modified_time$", re.I)})
    if mod_tag and mod_tag.get("content"):
        try:
            modified_at = datetime.fromisoformat(
                str(mod_tag.get("content")).replace("Z", "+00:00")
            ).astimezone(UTC)
        except Exception:
            pass

    # 2. Challenge & Login Page Detection
    html_lower = html.lower()
    is_challenge = any(sub in html_lower for sub in CHALLENGE_SUBSTRINGS)

    # Check for login form or password field
    has_password_input = bool(soup.find("input", attrs={"type": "password"}))
    has_login_form = bool(
        soup.find(
            "form",
            attrs={"action": re.compile(r"(login|signin|session|auth)", re.I)},
        )
    )
    is_login = has_password_input or (has_login_form and "login" in html_lower[:5000])

    # 3. Discovered Links Sanitization
    discovered_links: dict[str, list[dict[str, Any]]] = {"internal": [], "external": []}
    parsed_base = urlsplit(base_url)
    base_domain = (parsed_base.hostname or "").lower()

    link_tags = soup.find_all("a", href=True)
    retained_links_count = 0

    for a_tag in link_tags:
        if retained_links_count >= limits.max_discovered_links:
            warnings.append(
                ExtractionWarning(
                    code="LINK_LIMIT_EXCEEDED",
                    message=(
                        f"Discovered links exceeded max count of {limits.max_discovered_links}; "
                        "remaining links omitted from metadata."
                    ),
                )
            )
            break

        raw_href = str(a_tag["href"]).strip()
        if not raw_href or raw_href.startswith("#"):
            continue

        resolved = urljoin(base_url, raw_href)
        try:
            parsed_link = urlsplit(resolved)
        except Exception:
            continue

        link_scheme = (parsed_link.scheme or "").lower()
        if link_scheme not in ("http", "https"):
            continue

        # Strip credentials and secret parameters
        if parsed_link.username or parsed_link.password:
            continue

        sanitized_query = ""
        if parsed_link.query:
            query_items = parse_qs(parsed_link.query)
            clean_items = {
                k: v for k, v in query_items.items() if not SECRET_KEYWORD_REGEX.search(k)
            }
            clean_pairs = []
            for k, vals in sorted(clean_items.items()):
                for v in vals:
                    clean_pairs.append(f"{k}={v}")
            sanitized_query = "&".join(clean_pairs)

        sanitized_url = parsed_link._replace(
            fragment="",
            query=sanitized_query,
        ).geturl()

        link_host = (parsed_link.hostname or "").lower()
        is_internal = link_host == base_domain or link_host.endswith("." + base_domain)
        category = "internal" if is_internal else "external"

        discovered_links[category].append(
            {
                "href": sanitized_url,
                "text": a_tag.get_text(strip=True)[:256],
                "title": (a_tag.get("title") or "")[:256],
                "base_domain": link_host,
            }
        )
        retained_links_count += 1

    # 4. Remove unwanted tags for clean visible content
    for unneeded in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "canvas",
            "template",
            "iframe",
            "object",
            "embed",
        ]
    ):
        unneeded.decompose()

    # 5. Ordered Extraction Elements & Tables
    elements: list[ExtractionElement] = []
    tables: list[TableRepresentation] = []
    section_stack: list[SectionReference] = []
    char_cursor = 0
    full_markdown_parts: list[str] = []

    # Iterate over top-level semantic tags inside body or main
    body = soup.body or soup
    semantic_tags = body.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "blockquote",
            "pre",
            "ul",
            "ol",
            "li",
            "table",
            "hr",
            "img",
        ]
    )

    for tag in semantic_tags:
        if len(elements) >= limits.max_elements:
            warnings.append(
                ExtractionWarning(
                    code="ELEMENT_LIMIT_EXCEEDED",
                    message=(
                        f"Total extracted elements exceeded limit of {limits.max_elements}; "
                        "further elements omitted."
                    ),
                )
            )
            break

        tag_name = tag.name.lower()
        elem_text = tag.get_text(separator=" ", strip=True)

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            # Maintain section stack
            section_stack = [s for s in section_stack if s.level < level]
            sec_title = elem_text if elem_text else f"Level {level}"
            ancestor_path = "/" + "/".join(s.title for s in section_stack) if section_stack else ""
            sec_path = f"{ancestor_path}/{sec_title}" if ancestor_path else f"/{sec_title}"
            sec_ref = SectionReference(title=sec_title, level=level, path=sec_path)
            section_stack.append(sec_ref)

            md = f"{'#' * level} {elem_text}"
            span_start = char_cursor
            span_end = span_start + len(elem_text)
            char_cursor = span_end + 1

            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.HEADING,
                    ordinal=len(elements),
                    text=elem_text,
                    markdown=md,
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(
                        source_native_reference=tag_name,
                        char_start=span_start,
                        char_end=span_end,
                        extractor_native_id=tag.get("id"),
                    ),
                    attributes={"level": level, "tag": tag_name},
                )
            )
            full_markdown_parts.append(md)

        elif tag_name in ("p", "blockquote"):
            if not elem_text:
                continue
            md = f"> {elem_text}" if tag_name == "blockquote" else elem_text
            span_start = char_cursor
            span_end = span_start + len(elem_text)
            char_cursor = span_end + 1

            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.TEXT,
                    ordinal=len(elements),
                    text=elem_text,
                    markdown=md,
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(
                        source_native_reference=tag_name,
                        char_start=span_start,
                        char_end=span_end,
                        extractor_native_id=tag.get("id"),
                    ),
                    attributes={"tag": tag_name},
                )
            )
            full_markdown_parts.append(md)

        elif tag_name == "pre":
            code_tag = tag.find("code")
            code_content = code_tag.get_text() if code_tag else tag.get_text()
            md = f"```\n{code_content}\n```"
            span_start = char_cursor
            span_end = span_start + len(code_content)
            char_cursor = span_end + 1

            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.CODE,
                    ordinal=len(elements),
                    text=code_content,
                    markdown=md,
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(
                        source_native_reference="pre",
                        char_start=span_start,
                        char_end=span_end,
                        extractor_native_id=tag.get("id"),
                    ),
                    attributes={"tag": "pre"},
                )
            )
            full_markdown_parts.append(md)

        elif tag_name == "li":
            if not elem_text:
                continue
            md = f"- {elem_text}"
            span_start = char_cursor
            span_end = span_start + len(elem_text)
            char_cursor = span_end + 1

            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.LIST_ITEM,
                    ordinal=len(elements),
                    text=elem_text,
                    markdown=md,
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(
                        source_native_reference="li",
                        char_start=span_start,
                        char_end=span_end,
                        extractor_native_id=tag.get("id"),
                    ),
                    attributes={"tag": "li"},
                )
            )
            full_markdown_parts.append(md)

        elif tag_name == "hr":
            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.HORIZONTAL_RULE,
                    ordinal=len(elements),
                    text="",
                    markdown="---",
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(source_native_reference="hr"),
                    attributes={"tag": "hr"},
                )
            )
            full_markdown_parts.append("---")

        elif tag_name == "img":
            alt = (tag.get("alt") or "")[:256]
            src = (tag.get("src") or "")[:512]
            md = f"![{alt}]({src})"
            elements.append(
                ExtractionElement(
                    element_id=f"elem_{len(elements):05d}",
                    element_type=ExtractionElementType.IMAGE,
                    ordinal=len(elements),
                    text=alt,
                    markdown=md,
                    section_hierarchy=list(section_stack),
                    provenance=ElementProvenance(source_native_reference="img"),
                    attributes={"alt": alt, "src": src},
                )
            )
            full_markdown_parts.append(md)

        elif tag_name == "table":
            table_elem, table_repr, table_md = _parse_html_table(
                tag, len(elements), list(section_stack), warnings
            )
            if table_elem:
                elements.append(table_elem)
                if table_repr:
                    tables.append(table_repr)
                full_markdown_parts.append(table_md)

    # Visible plain text from body
    visible_text = body.get_text(separator="\n", strip=True)
    if len(visible_text) > limits.max_text_chars:
        visible_text = visible_text[: limits.max_text_chars]
        warnings.append(
            ExtractionWarning(
                code="TEXT_TRUNCATED",
                message=f"Visible plain text truncated to {limits.max_text_chars} characters.",
            )
        )

    full_md = "\n\n".join(full_markdown_parts)
    if len(full_md) > limits.max_markdown_chars:
        full_md = full_md[: limits.max_markdown_chars]
        warnings.append(
            ExtractionWarning(
                code="MARKDOWN_TRUNCATED",
                message=f"Markdown truncated to {limits.max_markdown_chars} characters.",
            )
        )

    return ParsedWebPage(
        title=title,
        meta_description=meta_desc,
        meta_author=meta_author,
        created_at=created_at,
        modified_at=modified_at,
        full_text=visible_text,
        full_markdown=full_md,
        elements=elements,
        tables=tables,
        discovered_links=discovered_links,
        warnings=warnings[: limits.max_warnings],
        errors=errors,
        is_challenge_page=is_challenge,
        is_login_page=is_login,
    )


def _parse_html_table(
    table_tag: Tag,
    ordinal: int,
    section_stack: list[SectionReference],
    warnings: list[ExtractionWarning],
) -> tuple[ExtractionElement | None, TableRepresentation | None, str]:
    """Parse an HTML <table> tag into an ExtractionElement and TableRepresentation."""
    caption_tag = table_tag.find("caption")
    caption = caption_tag.get_text(strip=True) if caption_tag else None

    header_cells: list[str] = []
    thead = table_tag.find("thead")
    thead_trs = set(thead.find_all("tr")) if thead else set()
    if thead:
        th_tags = thead.find_all("th")
        if th_tags:
            header_cells = [th.get_text(separator=" ", strip=True) for th in th_tags]

    # Search for rows in tbody or table directly (excluding thead trs)
    row_tags = [tr for tr in table_tag.find_all("tr") if tr not in thead_trs]
    raw_rows: list[list[str]] = []
    for r in row_tags:
        # Check if first row is headers if thead was absent
        th_tags = r.find_all("th")
        td_tags = r.find_all("td")
        if th_tags and not td_tags and not header_cells:
            header_cells = [th.get_text(separator=" ", strip=True) for th in th_tags]
            continue

        cells = [c.get_text(separator=" ", strip=True) for c in (th_tags + td_tags)]
        if cells:
            raw_rows.append(cells)

    if not raw_rows and not header_cells:
        return None, None, ""

    # Determine uniform column count
    max_cols = max([len(header_cells)] + [len(r) for r in raw_rows])
    if max_cols == 0:
        return None, None, ""

    # Normalize row widths
    is_irregular = False
    if header_cells and len(header_cells) != max_cols:
        header_cells = header_cells + [""] * (max_cols - len(header_cells))
        is_irregular = True

    normalized_rows: list[list[str]] = []
    for r in raw_rows:
        if len(r) != max_cols:
            is_irregular = True
            r = r + [""] * (max_cols - len(r))
        normalized_rows.append(r)

    if is_irregular:
        warnings.append(
            ExtractionWarning(
                code="MALFORMED_TABLE",
                message=(
                    f"HTML table at element index {ordinal} had irregular row/header widths. "
                    f"Padded missing cells to normalize to {max_cols} columns."
                ),
            )
        )

    # Generate Markdown Table
    md_lines: list[str] = []
    if caption:
        md_lines.append(f"**{caption}**\n")

    cols_for_md = header_cells if header_cells else [f"Col {i + 1}" for i in range(max_cols)]
    md_lines.append("| " + " | ".join(cols_for_md) + " |")
    md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for r in normalized_rows:
        md_lines.append("| " + " | ".join(r) + " |")
    table_md = "\n".join(md_lines)

    table_repr = TableRepresentation(
        headers=header_cells,
        rows=normalized_rows,  # type: ignore[arg-type]
        row_count=len(normalized_rows),
        column_count=max_cols,
        caption=caption,
        table_id=table_tag.get("id"),
    )

    elem = ExtractionElement(
        element_id=f"elem_{ordinal:05d}",
        element_type=ExtractionElementType.TABLE,
        ordinal=ordinal,
        text=table_tag.get_text(separator=" ", strip=True),
        markdown=table_md,
        section_hierarchy=section_stack,
        provenance=ElementProvenance(source_native_reference="table"),
        table=table_repr,
        attributes={"caption": caption, "row_count": len(normalized_rows), "col_count": max_cols},
    )
    return elem, table_repr, table_md


# -----------------------------------------------------------------------------
# Crawl4AI Web Extractor Subsystem
# -----------------------------------------------------------------------------


class Crawl4AIWebExtractor:
    """Bounded, deterministic web extraction subsystem using Crawl4AI and Playwright.

    Implements strict single-page public web acquisition, request-level SSRF defense,
    and canonical schema mapping.
    """

    def __init__(
        self,
        config: WebExtractionConfig | None = None,
        limits: WebExtractionLimits | None = None,
    ) -> None:
        self.config = config or WebExtractionConfig()
        self.limits = limits or WebExtractionLimits()
        self.rate_limiter = DomainRateLimiter(self.config.min_domain_interval_seconds)
        self.global_semaphore = asyncio.Semaphore(self.config.max_concurrent_crawls)
        self._crawler: AsyncWebCrawler | None = None
        self._is_closed = False
        self._lock = asyncio.Lock()

    async def _get_or_create_crawler(self) -> AsyncWebCrawler:
        """Lazily initialize the underlying AsyncWebCrawler instance."""
        async with self._lock:
            if self._crawler is None:
                b_conf = BrowserConfig(
                    headless=True,
                    verbose=False,
                    accept_downloads=False,
                    java_script_enabled=True,
                )
                crawler = AsyncWebCrawler(config=b_conf)
                await crawler.start()
                self._crawler = crawler
            return self._crawler

    async def close(self) -> None:
        """Close browser and crawler resources idempotently."""
        async with self._lock:
            if self._is_closed:
                return
            self._is_closed = True
            if self._crawler is not None:
                try:
                    await self._crawler.close()
                except Exception as exc:
                    logger.debug("Error during crawler close: %s", exc)
                finally:
                    self._crawler = None

    async def __aenter__(self) -> Crawl4AIWebExtractor:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def extract_url(
        self,
        url: str,
        *,
        approved_domains: Sequence[str] | None = None,
        timeout_seconds: float | None = None,
        max_response_bytes: int | None = None,
        render_javascript: bool | None = None,
        strategy: WebExtractionStrategy | None = None,
        raise_on_error: bool | None = None,
    ) -> NormalizedDocument:
        """Extract a single public web page and produce a finalized NormalizedDocument.

        Args:
            url: The public HTTP/HTTPS URL to acquire.
            approved_domains: Optional domain allowlist overrides.
            timeout_seconds: Overall extraction timeout in seconds.
            max_response_bytes: Main-document response size limit in bytes.
            render_javascript: If True, uses RENDERED dynamic browser rendering.
            strategy: Explicit WebExtractionStrategy (STATIC or RENDERED).
            raise_on_error: If True, raises exceptions on failure rather than returning
                a structured failed NormalizedDocument.

        Returns:
            A deeply frozen, finalized, and hash-verified NormalizedDocument.

        Raises:
            WebExtractionSecurityError: On security/SSRF/domain violation.
            WebExtractionTimeoutError: On extraction timeout.
            WebExtractionLimitExceededError: On response size overflow.
        """
        if self._is_closed:
            raise WebExtractionError("Crawl4AIWebExtractor is closed.")

        # Determine effective parameters
        eff_approved = (
            tuple(approved_domains)
            if approved_domains is not None
            else self.config.approved_domains
        )
        eff_timeout = timeout_seconds or self.config.timeout_seconds
        eff_raise = raise_on_error if raise_on_error is not None else self.config.raise_on_error
        eff_max_bytes = max_response_bytes or self.limits.max_main_document_bytes

        eff_strategy = self.config.strategy
        if strategy is not None:
            eff_strategy = strategy
        elif render_javascript is not None:
            eff_strategy = (
                WebExtractionStrategy.RENDERED
                if render_javascript
                else WebExtractionStrategy.STATIC
            )

        # 1. Zero Trust URL Preflight Validation
        try:
            valid_url = validate_web_url(
                url,
                approved_domains=eff_approved,
                allow_loopback_for_testing=self.config.allow_loopback_for_testing,
            )
        except WebExtractionSecurityError as sec_err:
            if eff_raise:
                raise
            return self._build_rejected_document(
                url=url,
                error_code=ExtractionErrorCode.ACCESS_DENIED,
                error_message=str(sec_err),
                approved_domains=eff_approved,
            )

        parsed_url = urlsplit(valid_url)
        target_domain = (parsed_url.hostname or "").lower()

        # 2. Acquire domain throttle and concurrency semaphore
        domain_sem = self.rate_limiter.get_domain_semaphore(target_domain)
        async with self.global_semaphore, domain_sem:
            await self.rate_limiter.throttle(target_domain)

            # 3. Execution under overall deadline
            try:
                async with asyncio.timeout(eff_timeout):
                    if eff_strategy == WebExtractionStrategy.STATIC:
                        return await self._execute_static(
                            valid_url,
                            approved_domains=eff_approved,
                            max_bytes=eff_max_bytes,
                            raise_on_error=eff_raise,
                        )
                    else:
                        return await self._execute_rendered(
                            valid_url,
                            approved_domains=eff_approved,
                            max_bytes=eff_max_bytes,
                            timeout_seconds=eff_timeout,
                            raise_on_error=eff_raise,
                        )
            except TimeoutError as t_err:
                msg = f"Web extraction timed out after {eff_timeout} seconds for {valid_url}"
                if eff_raise:
                    raise WebExtractionTimeoutError(msg) from t_err
                return self._build_rejected_document(
                    url=valid_url,
                    error_code=ExtractionErrorCode.EXTRACTION_TIMEOUT,
                    error_message=msg,
                    approved_domains=eff_approved,
                )
            except WebExtractionLimitExceededError as lim_err:
                if eff_raise:
                    raise
                return self._build_rejected_document(
                    url=valid_url,
                    error_code=ExtractionErrorCode.FILE_TOO_LARGE,
                    error_message=str(lim_err),
                    approved_domains=eff_approved,
                )
            except WebExtractionSecurityError as sec_err:
                if eff_raise:
                    raise
                return self._build_rejected_document(
                    url=valid_url,
                    error_code=ExtractionErrorCode.ACCESS_DENIED,
                    error_message=str(sec_err),
                    approved_domains=eff_approved,
                )
            except Exception as exc:
                msg = f"Internal web extraction failure for {valid_url}: {type(exc).__name__}"
                logger.error("Web extraction error: %s", exc, exc_info=False)
                if eff_raise:
                    raise WebExtractionError(msg) from exc
                return self._build_rejected_document(
                    url=valid_url,
                    error_code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
                    error_message=msg,
                    approved_domains=eff_approved,
                )

    # -------------------------------------------------------------------------
    # STATIC Execution Mode (Non-Browser HTTP Fetch + Crawl4AI HTML Processing)
    # -------------------------------------------------------------------------

    async def _execute_static(
        self,
        url: str,
        *,
        approved_domains: Sequence[str],
        max_bytes: int,
        raise_on_error: bool,
    ) -> NormalizedDocument:
        """Execute extraction via bounded HTTP client with SSRF checks on every redirect."""
        current_url = url
        hops = 0
        max_hops = 5
        acquired_bytes = bytearray()
        status_code = 200
        headers_dict: dict[str, str] = {}

        timeout_cfg = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(timeout=timeout_cfg, connector=connector) as session:
            while hops < max_hops:
                hops += 1
                async with session.get(
                    current_url,
                    allow_redirects=False,
                    headers={"User-Agent": "Javed-WebExtractor/0.9.5 (compatible)"},
                ) as resp:
                    status_code = resp.status
                    headers_dict = dict(resp.headers)

                    # Handle Redirects
                    if status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location")
                        if not loc:
                            raise WebExtractionError(
                                f"HTTP {status_code} redirect without Location header."
                            )
                        next_url = urljoin(current_url, loc)
                        # Validate redirect destination against SSRF and approved domains
                        current_url = validate_web_url(
                            next_url,
                            approved_domains=approved_domains,
                            allow_loopback_for_testing=self.config.allow_loopback_for_testing,
                        )
                        continue

                    # Stream body and enforce max_bytes
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        acquired_bytes.extend(chunk)
                        if len(acquired_bytes) > max_bytes:
                            raise WebExtractionLimitExceededError(
                                f"Main document size exceeded limit of {max_bytes} bytes."
                            )
                    break

        raw_bytes = bytes(acquired_bytes)
        try:
            html_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            html_text = raw_bytes.decode("latin-1", errors="replace")

        # Check HTTP Status Codes
        if status_code == 401:
            return self._build_rejected_document(
                url=current_url,
                error_code=ExtractionErrorCode.AUTH_REQUIRED,
                error_message="HTTP 401 Unauthorized: Authentication required to access page.",
                approved_domains=approved_domains,
            )
        elif status_code == 403:
            return self._build_rejected_document(
                url=current_url,
                error_code=ExtractionErrorCode.ACCESS_DENIED,
                error_message="HTTP 403 Forbidden: Access denied by web server.",
                approved_domains=approved_domains,
            )
        elif status_code == 429:
            retry_after = headers_dict.get("Retry-After")
            return self._build_rejected_document(
                url=current_url,
                error_code=ExtractionErrorCode.RATE_LIMITED,
                error_message=f"HTTP 429 Too Many Requests (Retry-After: {retry_after}).",
                approved_domains=approved_domains,
            )

        # Process HTML and build canonical document
        return await self._map_to_normalized_document(
            url=url,
            final_url=current_url,
            html=html_text,
            raw_bytes=raw_bytes,
            status_code=status_code,
            headers=headers_dict,
            strategy=WebExtractionStrategy.STATIC,
            approved_domains=approved_domains,
        )

    # -------------------------------------------------------------------------
    # RENDERED Execution Mode (Playwright Dynamic Crawl with Request Routing)
    # -------------------------------------------------------------------------

    async def _execute_rendered(
        self,
        url: str,
        *,
        approved_domains: Sequence[str],
        max_bytes: int,
        timeout_seconds: float,
        raise_on_error: bool,
    ) -> NormalizedDocument:
        """Execute dynamic extraction with full Playwright request routing and WebSocket defense."""
        crawler = await self._get_or_create_crawler()

        observed_total_bytes = 0
        security_violation: Exception | None = None
        final_response_status = 200
        final_headers: dict[str, str] = {}

        # Define request routing hook
        async def on_page_context(
            page: Page, context: Any = None, config: Any = None, **kwargs: Any
        ) -> None:
            # 1. Intercept all HTTP/HTTPS requests & subresources
            async def handle_route(route: Route) -> None:
                nonlocal observed_total_bytes, security_violation
                req = route.request
                req_url = req.url

                # Validate subresource or main-doc request against SSRF and approved domains
                try:
                    validate_web_url(
                        req_url,
                        approved_domains=approved_domains,
                        allow_loopback_for_testing=self.config.allow_loopback_for_testing,
                    )
                except WebExtractionSecurityError as s_err:
                    security_violation = s_err
                    await route.abort("blockedbyclient")
                    return

                # Intercept redirects on main requests via route.fetch(max_redirects=0)
                try:
                    resp = await route.fetch(max_redirects=0)
                    observed_total_bytes += len(await resp.body())
                    if observed_total_bytes > self.limits.max_total_response_bytes:
                        security_violation = WebExtractionLimitExceededError(
                            "Total observed response bytes exceeded "
                            f"{self.limits.max_total_response_bytes}."
                        )
                        await route.abort("blockedbyclient")
                        return

                    if resp.status in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if loc:
                            resolved_loc = urljoin(req_url, loc)
                            validate_web_url(
                                resolved_loc,
                                approved_domains=approved_domains,
                                allow_loopback_for_testing=self.config.allow_loopback_for_testing,
                            )
                    await route.fulfill(response=resp)
                except WebExtractionSecurityError as s_err:
                    security_violation = s_err
                    await route.abort("blockedbyclient")
                except PlaywrightError:
                    # Let natural network failures proceed
                    try:
                        await route.continue_()
                    except Exception:
                        pass
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", handle_route)

            # 2. Intercept page-created WebSockets
            def handle_ws(ws: WebSocketRoute) -> None:
                nonlocal security_violation
                try:
                    validate_web_url(
                        ws.url,
                        approved_domains=approved_domains,
                        allow_loopback_for_testing=self.config.allow_loopback_for_testing,
                    )
                except WebExtractionSecurityError as s_err:
                    security_violation = s_err
                    asyncio.create_task(ws.close())

            await page.route_web_socket("**/*", handle_ws)

            # 3. Block downloads and popups
            page.on("popup", lambda p: asyncio.create_task(p.close()))
            page.on("download", lambda d: asyncio.create_task(d.cancel()))

            # 4. Track response headers & status
            def on_response(res: Any) -> None:
                nonlocal final_response_status, final_headers
                if res.request.is_navigation_request():
                    final_response_status = res.status
                    final_headers = res.headers

            page.on("response", on_response)

        # Attach hook to crawler strategy
        crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context)

        run_config = CrawlerRunConfig(
            cache_mode=self.config.cache_mode,
            page_timeout=int(self.config.page_timeout_seconds * 1000),
            wait_until="domcontentloaded",
            verbose=False,
            check_robots_txt=False,
            scan_full_page=False,
            process_iframes=False,
            magic=False,
            remove_overlay_elements=False,
        )

        res = await crawler.arun(url=url, config=run_config)

        if security_violation is not None:
            if isinstance(security_violation, WebExtractionSecurityError):
                raise security_violation
            elif isinstance(security_violation, WebExtractionLimitExceededError):
                raise security_violation

        final_url = res.redirected_url or res.url or url
        html = res.html or ""
        raw_bytes = html.encode("utf-8")

        if len(raw_bytes) > max_bytes:
            raise WebExtractionLimitExceededError(
                f"Main document size exceeded limit of {max_bytes} bytes."
            )

        status_code = res.status_code or final_response_status

        # Check HTTP Status Codes
        if status_code == 401:
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.AUTH_REQUIRED,
                error_message="HTTP 401 Unauthorized: Authentication required to access page.",
                approved_domains=approved_domains,
            )
        elif status_code == 403:
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.ACCESS_DENIED,
                error_message="HTTP 403 Forbidden: Access denied by web server.",
                approved_domains=approved_domains,
            )
        elif status_code == 429:
            retry_after = final_headers.get("retry-after")
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.RATE_LIMITED,
                error_message=f"HTTP 429 Too Many Requests (Retry-After: {retry_after}).",
                approved_domains=approved_domains,
            )

        # Check Anti-bot or Challenge error message from Crawl4AI
        if res.error_message and "anti-bot" in res.error_message.lower():
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.AUTOMATION_NOT_ALLOWED,
                error_message=f"Anti-bot protection encountered: {res.error_message}",
                approved_domains=approved_domains,
            )

        return await self._map_to_normalized_document(
            url=url,
            final_url=final_url,
            html=html,
            raw_bytes=raw_bytes,
            status_code=status_code,
            headers=final_headers or (res.response_headers or {}),
            strategy=WebExtractionStrategy.RENDERED,
            approved_domains=approved_domains,
        )

    # -------------------------------------------------------------------------
    # Canonical NormalizedDocument Construction & Finalization
    # -------------------------------------------------------------------------

    async def _map_to_normalized_document(
        self,
        url: str,
        final_url: str,
        html: str,
        raw_bytes: bytes,
        status_code: int,
        headers: dict[str, str],
        strategy: WebExtractionStrategy,
        approved_domains: Sequence[str],
    ) -> NormalizedDocument:
        """Map extracted HTML and Crawl4AI elements to a finalized NormalizedDocument."""
        parsed = clean_and_extract_elements(
            html=html,
            base_url=final_url,
            initial_url=url,
            limits=self.limits,
        )

        # Challenge / Login Detection Check
        if parsed.is_challenge_page:
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.AUTOMATION_NOT_ALLOWED,
                error_message="Security challenge page detected (e.g. Cloudflare / CAPTCHA).",
                approved_domains=approved_domains,
            )
        if parsed.is_login_page:
            return self._build_rejected_document(
                url=final_url,
                error_code=ExtractionErrorCode.AUTH_REQUIRED,
                error_message="Login page detected. Public web extraction refused.",
                approved_domains=approved_domains,
            )

        now_utc = datetime.now(UTC)
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Deterministic IDs
        doc_id = f"doc_{hashlib.sha256(final_url.encode()).hexdigest()[:16]}"
        ver_id = f"ver_{raw_hash[:16]}"
        ing_id = (
            f"ing_{hashlib.sha256(f'{final_url}:{now_utc.isoformat()}'.encode()).hexdigest()[:16]}"
        )

        parsed_host = (urlsplit(final_url).hostname or "").lower()
        matched_domain = _matches_approved_domain(parsed_host, approved_domains)

        source_desc = SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri=final_url,
            original_display_name=parsed.title or final_url,
            source_title=parsed.title,
            mime_type="text/html",
            acquisition_timestamp=now_utc,
            content_length=len(raw_bytes),
            approved_domain=matched_domain or target_domain_fallback(parsed_host),
        )

        config_params = {
            "strategy": strategy.value,
            "max_main_document_bytes": self.limits.max_main_document_bytes,
            "timeout_seconds": self.config.timeout_seconds,
            "render_javascript": strategy == WebExtractionStrategy.RENDERED,
        }
        config_hash = hashlib.sha256(
            json.dumps(config_params, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        extractor_desc = ExtractorDescriptor(
            engine_name=CRAWL4AI_ENGINE_NAME,
            engine_version=CRAWL4AI_ENGINE_VERSION,
            config_parameters=config_params,
            extractor_config_sha256=config_hash,
        )

        meta = DocumentMetadata(
            title=parsed.title,
            author=parsed.meta_author,
            created_at=parsed.created_at,
            modified_at=parsed.modified_at,
            element_count=len(parsed.elements),
            table_count=len(parsed.tables),
            word_count=len(parsed.full_text.split()),
            character_count=len(parsed.full_text),
            custom_attributes={
                "requested_url": url,
                "final_url": final_url,
                "status_code": status_code,
                "discovered_links": parsed.discovered_links,
            },
        )

        status = ExtractionStatus.SUCCESS
        if parsed.warnings:
            # If any truncation warning occurred, mark partial success
            if any("TRUNCATED" in w.code for w in parsed.warnings):
                status = ExtractionStatus.PARTIAL_SUCCESS

        doc = NormalizedDocument(
            document_id=doc_id,
            version_id=ver_id,
            ingestion_id=ing_id,
            source_sha256=raw_hash,
            source=source_desc,
            extractor=extractor_desc,
            metadata=meta,
            elements=parsed.elements,
            full_text=parsed.full_text,
            full_markdown=parsed.full_markdown,
            status=status,
            warnings=parsed.warnings,
            errors=parsed.errors,
            extracted_at=now_utc,
        )

        # Deeply freeze, compute hashes, and verify trust boundary
        doc.finalize()
        verify_trust_boundary(doc)
        return doc

    def _build_rejected_document(
        self,
        url: str,
        error_code: ExtractionErrorCode,
        error_message: str,
        approved_domains: Sequence[str],
    ) -> NormalizedDocument:
        """Construct a finalized, rejected/failed NormalizedDocument for non-fatal errors."""
        now_utc = datetime.now(UTC)
        empty_hash = hashlib.sha256(b"").hexdigest()

        doc_id = f"doc_{hashlib.sha256(url.encode()).hexdigest()[:16]}"
        ver_id = f"ver_rejected_{now_utc.strftime('%Y%m%d%H%M%S')}"
        ing_id = f"ing_{hashlib.sha256(f'{url}:{now_utc.isoformat()}'.encode()).hexdigest()[:16]}"

        parsed_host = (urlsplit(url).hostname or "").lower()
        matched_domain = _matches_approved_domain(parsed_host, approved_domains)

        source_desc = SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri=url if url.startswith(("http://", "https://")) else None,
            relative_source_ref="rejected_url"
            if not url.startswith(("http://", "https://"))
            else None,
            original_display_name=url,
            mime_type="text/html",
            acquisition_timestamp=now_utc,
            content_length=0,
            approved_domain=matched_domain or target_domain_fallback(parsed_host),
        )

        config_params = {"strategy": self.config.strategy.value}
        config_hash = hashlib.sha256(
            json.dumps(config_params, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        extractor_desc = ExtractorDescriptor(
            engine_name=CRAWL4AI_ENGINE_NAME,
            engine_version=CRAWL4AI_ENGINE_VERSION,
            config_parameters=config_params,
            extractor_config_sha256=config_hash,
        )

        doc = NormalizedDocument(
            document_id=doc_id,
            version_id=ver_id,
            ingestion_id=ing_id,
            source_sha256=empty_hash,
            source=source_desc,
            extractor=extractor_desc,
            metadata=DocumentMetadata(
                title="Extraction Refused / Failed",
                element_count=0,
                table_count=0,
                word_count=0,
                character_count=0,
                custom_attributes={"requested_url": url},
            ),
            elements=[],
            full_text="",
            full_markdown="",
            status=ExtractionStatus.REJECTED
            if error_code == ExtractionErrorCode.ACCESS_DENIED
            else ExtractionStatus.FAILED,
            warnings=[],
            errors=[
                ExtractionError(
                    code=error_code,
                    message=error_message,
                    timestamp=now_utc,
                )
            ],
            extracted_at=now_utc,
        )
        doc.finalize()
        verify_trust_boundary(doc)
        return doc


def target_domain_fallback(hostname: str) -> str | None:
    """Fallback helper to extract a clean domain name without control chars."""
    if not hostname or hostname in ("localhost", "127.0.0.1"):
        return None
    return hostname[:253]


# -----------------------------------------------------------------------------
# Top-Level Convenience API
# -----------------------------------------------------------------------------


async def extract_url(
    url: str,
    *,
    approved_domains: Sequence[str] | None = None,
    timeout_seconds: float = DEFAULT_EXTRACTION_TIMEOUT_SECONDS,
    max_response_bytes: int = DEFAULT_MAX_MAIN_DOCUMENT_BYTES,
    render_javascript: bool = False,
    strategy: WebExtractionStrategy | None = None,
    allow_loopback_for_testing: bool = False,
    raise_on_error: bool = False,
) -> NormalizedDocument:
    """Convenience top-level entry point for single-page web extraction."""
    config = WebExtractionConfig(
        strategy=strategy
        or (WebExtractionStrategy.RENDERED if render_javascript else WebExtractionStrategy.STATIC),
        approved_domains=tuple(approved_domains or ()),
        timeout_seconds=timeout_seconds,
        allow_loopback_for_testing=allow_loopback_for_testing,
        raise_on_error=raise_on_error,
    )
    limits = WebExtractionLimits(max_main_document_bytes=max_response_bytes)
    async with Crawl4AIWebExtractor(config=config, limits=limits) as extractor:
        return await extractor.extract_url(
            url,
            approved_domains=approved_domains,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            render_javascript=render_javascript,
            strategy=strategy,
            raise_on_error=raise_on_error,
        )
