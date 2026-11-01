"""Canonical normalized extraction schema and Pydantic data models for BRICK-007.

Defines the zero-trust, strongly typed intermediate contracts for content
extraction across web pages (Crawl4AI) and local documents (Docling).

Strict Invariants:
1. Zero heavy runtime imports (no crawl4ai, docling, torch, ocr, playwright, db).
2. Zero import side-effects (no network, disk writes, threads, or model downloads).
3. All models enforce `extra="forbid"` to reject unexpected/untrusted fields.
4. Cryptographic separation: document_id, version_id, ingestion_id, source_sha256,
   normalized_output_sha256, and extractor_config_sha256.
5. All timestamps are strictly UTC-aware.
6. Absolute secrets prohibition in AuthenticatedSourceContext and element payloads.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# -----------------------------------------------------------------------------
# Regular Expressions & Constants
# -----------------------------------------------------------------------------

SHA256_HEX_REGEX = re.compile(r"^[0-9a-f]{64}$")
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x1f\x7f]")
CELL_RANGE_REGEX = re.compile(r"^[A-Z]+[0-9]+:[A-Z]+[0-9]+$")
PROHIBITED_SHEET_CHARS_REGEX = re.compile(r"[\[\]*?:/\\]")
OPAQUE_SESSION_REF_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{8,128}$")

SECRET_KEYWORD_REGEX = re.compile(
    r"(password|passwd|secret|token|apikey|api_key|bearer|cookie|auth|credential|session_id)",
    re.IGNORECASE,
)

FORBIDDEN_SECRET_FIELD_NAMES = {
    "password",
    "passwords",
    "otp",
    "otps",
    "mfa",
    "mfa_value",
    "passkey",
    "passkeys",
    "recovery_code",
    "recovery_codes",
    "cookie",
    "cookies",
    "access_token",
    "refresh_token",
    "authorization",
    "raw_browser_storage",
    "chrome_profile",
    "profile_path",
}


def _validate_utc(dt: datetime | None) -> datetime | None:
    """Ensure datetime is UTC-aware."""
    if dt is not None:
        if dt.tzinfo is None or dt.tzinfo != UTC:
            raise ValueError("Datetime must be UTC-aware (tzinfo=timezone.utc)")
    return dt


def _validate_sha256_hex(val: str | None, field_name: str) -> str | None:
    """Validate that a string is a 64-character lowercase hex SHA-256 digest."""
    if val is not None:
        if not SHA256_HEX_REGEX.match(val):
            raise ValueError(
                f"{field_name} must be exactly 64 lowercase hexadecimal characters, got {val!r}"
            )
    return val


def _reject_control_chars(val: str | None, field_name: str) -> str | None:
    """Reject ASCII control characters in strings."""
    if val is not None and CONTROL_CHAR_REGEX.search(val):
        raise ValueError(f"{field_name} contains prohibited control characters")
    return val


# -----------------------------------------------------------------------------
# Enumerations
# -----------------------------------------------------------------------------


class SourceType(StrEnum):
    """Supported source content types planned for extraction."""

    WEB_PAGE = "web_page"
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    TEXT = "text"


class ExtractionElementType(StrEnum):
    """Structural element types within a normalized document."""

    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    CODE = "code"
    LIST_ITEM = "list_item"
    IMAGE = "image"
    KEY_VALUE = "key_value"
    PAGE_BREAK = "page_break"
    HORIZONTAL_RULE = "horizontal_rule"


class ExtractionStatus(StrEnum):
    """Lifecycle status of a document extraction."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ExtractionErrorCode(StrEnum):
    """Standardized failure and rejection error codes."""

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    MIME_MISMATCH = "MIME_MISMATCH"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    CORRUPTED_DOCUMENT = "CORRUPTED_DOCUMENT"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    ARCHIVE_LIMIT_EXCEEDED = "ARCHIVE_LIMIT_EXCEEDED"
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    NETWORK_DISABLED = "NETWORK_DISABLED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTOMATION_NOT_ALLOWED = "AUTOMATION_NOT_ALLOWED"
    OWNER_TAKEOVER_REQUIRED = "OWNER_TAKEOVER_REQUIRED"
    INTERNAL_EXTRACTION_ERROR = "INTERNAL_EXTRACTION_ERROR"


class AccessMethod(StrEnum):
    """Channel or method used to acquire the source content."""

    PUBLIC_HTTP = "public_http"
    LOCAL_FILE = "local_file"
    AUTHENTICATED_SESSION = "authenticated_session"


class AuthenticationStatus(StrEnum):
    """Authentication authorization status for acquired sources."""

    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CoordinateOrigin(StrEnum):
    """Reference origin for spatial bounding box coordinates."""

    TOP_LEFT = "top_left"
    BOTTOM_LEFT = "bottom_left"


class CoordinateSpace(StrEnum):
    """Unit coordinate space for spatial elements."""

    POINTS = "points"
    PIXELS = "pixels"
    NORMALIZED_PERCENT = "normalized_percent"


# -----------------------------------------------------------------------------
# Base Schema Configuration
# -----------------------------------------------------------------------------


class ImmutableExtractionBase(BaseModel):
    """Base model enforcing strict unknown-field rejection and assignment validation.

    Note on Immutability:
    Instances are deliberately configured with `frozen=False` (allowing mutable assignment
    during staged extraction pipelines, e.g. attaching metadata or elements before finalization),
    paired with `validate_assignment=True` (ensuring every mutation is type-checked and
    satisfies all field constraints) and `extra='forbid'` (rejecting unknown fields).
    Cryptographic and canonical immutability is achieved at output time via
    `NormalizedDocument.with_computed_output_hash()` and content-addressed SHA-256 serialization.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )


# -----------------------------------------------------------------------------
# Spatial Coordinates & Provenance Models
# -----------------------------------------------------------------------------


class BoundingBox(ImmutableExtractionBase):
    """Spatial bounding box with declared coordinate system and orientation."""

    left: float
    top: float
    right: float
    bottom: float
    coordinate_space: CoordinateSpace = CoordinateSpace.POINTS
    origin: CoordinateOrigin = CoordinateOrigin.TOP_LEFT
    page_width: float | None = None
    page_height: float | None = None
    source_units: str | None = "pt"
    rotation_degrees: int = 0

    @model_validator(mode="after")
    def validate_spatial_bounds(self) -> BoundingBox:
        for val, name in [
            (self.left, "left"),
            (self.top, "top"),
            (self.right, "right"),
            (self.bottom, "bottom"),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"BoundingBox coordinate {name} must be finite, got {val}")

        if self.left > self.right:
            raise ValueError(f"BoundingBox left ({self.left}) cannot exceed right ({self.right})")

        if self.origin == CoordinateOrigin.TOP_LEFT:
            if self.top > self.bottom:
                raise ValueError(
                    f"BoundingBox top ({self.top}) exceeds bottom ({self.bottom}) (TOP_LEFT)"
                )
        elif self.origin == CoordinateOrigin.BOTTOM_LEFT:
            if self.bottom > self.top:
                raise ValueError(
                    f"BoundingBox bottom ({self.bottom}) exceeds top ({self.top}) (BOTTOM_LEFT)"
                )

        if self.coordinate_space == CoordinateSpace.NORMALIZED_PERCENT:
            for val, name in [
                (self.left, "left"),
                (self.top, "top"),
                (self.right, "right"),
                (self.bottom, "bottom"),
            ]:
                if not (0.0 <= val <= 1.0):
                    raise ValueError(
                        f"Normalized coordinate {name} must be in [0.0, 1.0], got {val}"
                    )

        if self.page_width is not None:
            if not math.isfinite(self.page_width) or self.page_width <= 0:
                raise ValueError(f"page_width must be positive, got {self.page_width}")

        if self.page_height is not None:
            if not math.isfinite(self.page_height) or self.page_height <= 0:
                raise ValueError(f"page_height must be positive, got {self.page_height}")

        if self.rotation_degrees not in (0, 90, 180, 270):
            raise ValueError(
                f"rotation_degrees must be one of (0, 90, 180, 270), got {self.rotation_degrees}"
            )

        return self


class ElementProvenance(ImmutableExtractionBase):
    """Source-level provenance mapping an element back to its exact origin."""

    page_number: int | None = Field(default=None, ge=1)
    source_native_reference: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    sheet_name: str | None = None
    cell_range: str | None = None
    bounding_box: BoundingBox | None = None
    extractor_native_id: str | None = None

    @model_validator(mode="after")
    def validate_provenance_spans(self) -> ElementProvenance:
        _reject_control_chars(self.source_native_reference, "source_native_reference")
        _reject_control_chars(self.sheet_name, "sheet_name")
        _reject_control_chars(self.cell_range, "cell_range")
        _reject_control_chars(self.extractor_native_id, "extractor_native_id")

        if self.char_start is not None and self.char_end is not None:
            if self.char_start > self.char_end:
                raise ValueError(
                    f"char_start ({self.char_start}) cannot exceed char_end ({self.char_end})"
                )

        if self.cell_range is not None:
            if not CELL_RANGE_REGEX.match(self.cell_range):
                raise ValueError(
                    f"cell_range syntax invalid (expected 'A1:C10'), got {self.cell_range!r}"
                )

        return self


# -----------------------------------------------------------------------------
# Tabular Data Models
# -----------------------------------------------------------------------------


class MergedCell(ImmutableExtractionBase):
    """Defines a merged cell region within a structured table."""

    start_row: int = Field(ge=0)
    end_row: int = Field(ge=0)
    start_col: int = Field(ge=0)
    end_col: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_merged_bounds(self) -> MergedCell:
        if self.start_row > self.end_row:
            raise ValueError(
                f"MergedCell start_row ({self.start_row}) cannot exceed end_row ({self.end_row})"
            )
        if self.start_col > self.end_col:
            raise ValueError(
                f"MergedCell start_col ({self.start_col}) cannot exceed end_col ({self.end_col})"
            )
        return self


class TableCell(ImmutableExtractionBase):
    """Individual cell representation with optional merged cell reference."""

    row: int = Field(ge=0)
    col: int = Field(ge=0)
    text: str
    is_header: bool = False
    merged_cell: MergedCell | None = None


class TableRepresentation(ImmutableExtractionBase):
    """Structured table representation attached directly to an ExtractionElement."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    sheet_name: str | None = None
    cell_range: str | None = None
    merged_cells: list[MergedCell] = Field(default_factory=list)
    caption: str | None = None
    table_id: str | None = None

    @model_validator(mode="after")
    def validate_table_integrity(self) -> TableRepresentation:
        _reject_control_chars(self.sheet_name, "sheet_name")
        _reject_control_chars(self.caption, "caption")
        _reject_control_chars(self.table_id, "table_id")

        if self.sheet_name is not None:
            if len(self.sheet_name) > 31:
                raise ValueError(
                    f"sheet_name cannot exceed 31 characters, got {len(self.sheet_name)}"
                )
            if PROHIBITED_SHEET_CHARS_REGEX.search(self.sheet_name):
                raise ValueError(
                    f"sheet_name contains prohibited characters ([]*?:/\\): {self.sheet_name!r}"
                )

        if self.cell_range is not None:
            if not CELL_RANGE_REGEX.match(self.cell_range):
                raise ValueError(
                    f"cell_range syntax invalid (expected 'A1:C10'), got {self.cell_range!r}"
                )

        # Dimension checks
        if self.row_count == 0:
            if self.column_count != 0 or len(self.rows) != 0:
                raise ValueError(
                    f"Empty table requires row_count=0, column_count=0, rows=[], "
                    f"got row_count={self.row_count}, col_count={self.column_count}"
                )
        else:
            if len(self.rows) != self.row_count:
                raise ValueError(
                    f"Declared row_count ({self.row_count}) differs from rows ({len(self.rows)})"
                )

            for idx, row in enumerate(self.rows):
                if len(row) != self.column_count:
                    raise ValueError(
                        f"Row {idx} width ({len(row)}) != column_count ({self.column_count})"
                    )

        if self.headers:
            if len(self.headers) != self.column_count:
                raise ValueError(
                    f"Headers width ({len(self.headers)}) != col_count ({self.column_count})"
                )

        # Merged cell bounds and non-overlapping verification
        occupied_coords: set[tuple[int, int]] = set()
        for mc in self.merged_cells:
            if mc.end_row >= self.row_count:
                raise ValueError(
                    f"MergedCell end_row ({mc.end_row}) exceeds row_count ({self.row_count})"
                )
            if mc.end_col >= self.column_count:
                raise ValueError(
                    f"MergedCell end_col ({mc.end_col}) exceeds col_count ({self.column_count})"
                )

            for r in range(mc.start_row, mc.end_row + 1):
                for c in range(mc.start_col, mc.end_col + 1):
                    coord = (r, c)
                    if coord in occupied_coords:
                        raise ValueError(f"Overlapping merged cell detected at row {r}, col {c}")
                    occupied_coords.add(coord)

        return self


# -----------------------------------------------------------------------------
# Document Structure & Hierarchy
# -----------------------------------------------------------------------------


class SectionReference(ImmutableExtractionBase):
    """Hierarchical section reference indicating document structure."""

    title: str = Field(min_length=1)
    level: int = Field(ge=1)
    path: str = Field(min_length=1)

    @field_validator("title", "path")
    @classmethod
    def validate_strings(cls, v: str) -> str:
        _reject_control_chars(v, "SectionReference field")
        return v


class ExtractionElement(ImmutableExtractionBase):
    """Atomic structural element extracted from a document or web page."""

    element_id: str = Field(min_length=1)
    element_type: ExtractionElementType
    ordinal: int = Field(ge=0)
    text: str | None = None
    markdown: str | None = None
    section_hierarchy: list[SectionReference] = Field(default_factory=list)
    provenance: ElementProvenance | None = None
    table: TableRepresentation | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_element_contracts(self) -> ExtractionElement:
        _reject_control_chars(self.element_id, "element_id")

        # Table binding exclusivity
        if self.element_type != ExtractionElementType.TABLE:
            if self.table is not None:
                raise ValueError(
                    f"Non-table element type ({self.element_type}) cannot carry TableRepresentation"
                )

        # Structural empty check
        allowed_empty = (
            ExtractionElementType.PAGE_BREAK,
            ExtractionElementType.HORIZONTAL_RULE,
            ExtractionElementType.IMAGE,
        )
        if self.element_type not in allowed_empty:
            has_text = self.text is not None and bool(self.text.strip())
            has_markdown = self.markdown is not None and bool(self.markdown.strip())
            has_table = self.table is not None

            if not (has_text or has_markdown or has_table):
                raise ValueError(
                    f"ExtractionElement {self.element_id} ({self.element_type}) cannot be empty"
                )

        return self


# -----------------------------------------------------------------------------
# Source & Security Descriptors
# -----------------------------------------------------------------------------


class SourceDescriptor(ImmutableExtractionBase):
    """Authoritative descriptor of the source content being extracted."""

    source_type: SourceType
    source_uri: str | None = None
    relative_source_ref: str | None = None
    original_display_name: str = Field(min_length=1)
    source_title: str | None = None
    mime_type: str = Field(min_length=1)
    acquisition_timestamp: datetime
    content_length: int | None = Field(default=None, ge=0)
    approved_domain: str | None = None

    @field_validator("acquisition_timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        return _validate_utc(v)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_source_references(self) -> SourceDescriptor:
        _reject_control_chars(self.original_display_name, "original_display_name")
        _reject_control_chars(self.source_title, "source_title")
        _reject_control_chars(self.mime_type, "mime_type")
        _reject_control_chars(self.approved_domain, "approved_domain")

        if self.source_uri is None and self.relative_source_ref is None:
            raise ValueError(
                "SourceDescriptor must specify either source_uri or relative_source_ref"
            )

        if self.source_uri is not None:
            _reject_control_chars(self.source_uri, "source_uri")
            parsed = urlsplit(self.source_uri)

            if parsed.scheme.lower() not in ("http", "https"):
                raise ValueError(
                    f"Unsupported scheme {parsed.scheme!r}. Only http/https permitted in source_uri"
                )

            if parsed.username or parsed.password:
                raise ValueError("Embedded credentials in source_uri are strictly forbidden")

            if ".." in parsed.path:
                raise ValueError("Path traversal segments ('..') are forbidden in source_uri")

            # Check query string for sensitive parameters
            if parsed.query:
                query_params = parse_qs(parsed.query)
                for key in query_params:
                    if SECRET_KEYWORD_REGEX.search(key):
                        raise ValueError(
                            f"Prohibited secret-bearing parameter in query string: {key!r}"
                        )

            # Normalize hostname to lowercase
            normalized_netloc = parsed.netloc.lower()
            if normalized_netloc != parsed.netloc:
                self.source_uri = parsed._replace(netloc=normalized_netloc).geturl()

        if self.relative_source_ref is not None:
            _reject_control_chars(self.relative_source_ref, "relative_source_ref")

            # Reject path traversal
            segments = self.relative_source_ref.replace("\\", "/").split("/")
            if ".." in segments:
                raise ValueError(
                    "Path traversal ('..') is strictly prohibited in relative_source_ref"
                )

            # Reject absolute paths (POSIX and Windows)
            if (
                os.path.isabs(self.relative_source_ref)
                or self.relative_source_ref.startswith("/")
                or self.relative_source_ref.startswith("\\")
                or re.match(r"^[a-zA-Z]:", self.relative_source_ref)
            ):
                raise ValueError(
                    "Absolute local filesystem paths are prohibited in relative_source_ref"
                )

        return self


class AuthenticatedSourceContext(ImmutableExtractionBase):
    """Metadata-only descriptor for future owner-authorized authenticated sources.

    Strict Invariant:
    This model must NEVER accept or hold credentials, tokens, cookies, passwords,
    or secret-bearing values. All session references are opaque tokens.
    """

    account_alias: str = Field(min_length=1)
    service: str = Field(min_length=1)
    access_method: AccessMethod = AccessMethod.AUTHENTICATED_SESSION
    opaque_browser_session_reference: str = Field(min_length=8, max_length=128)
    owner_authorized: bool = Field(default=False)
    approved_domains: list[str] = Field(default_factory=list)
    authentication_status: AuthenticationStatus = AuthenticationStatus.AUTHORIZED
    session_created_at: datetime | None = None
    session_expires_at: datetime | None = None

    @field_validator("session_created_at", "session_expires_at")
    @classmethod
    def validate_timestamps(cls, v: datetime | None) -> datetime | None:
        return _validate_utc(v)

    @model_validator(mode="after")
    def validate_opaque_session_ref(self) -> AuthenticatedSourceContext:
        _reject_control_chars(self.account_alias, "account_alias")
        _reject_control_chars(self.service, "service")
        _reject_control_chars(
            self.opaque_browser_session_reference, "opaque_browser_session_reference"
        )

        for d in self.approved_domains:
            _reject_control_chars(d, "approved_domain")

        # Session reference must be an opaque alphanumeric/UUID token
        if not OPAQUE_SESSION_REF_REGEX.match(self.opaque_browser_session_reference):
            raise ValueError(
                "opaque_browser_session_reference must be a sanitized opaque token "
                f"matching {OPAQUE_SESSION_REF_REGEX.pattern}"
            )

        # Prohibit path characters, Bearer headers, or cookie-like strings
        ref = self.opaque_browser_session_reference
        if any(c in ref for c in ("/", "\\", ";", "=", ":", "@")):
            raise ValueError(
                "opaque_browser_session_reference contains prohibited path/credential characters"
            )

        if ref.lower().startswith("bearer"):
            raise ValueError(
                "opaque_browser_session_reference cannot contain Bearer authorization tokens"
            )

        return self


# -----------------------------------------------------------------------------
# Diagnostics & Errors
# -----------------------------------------------------------------------------


class ExtractionWarning(ImmutableExtractionBase):
    """Structured diagnostic warning during extraction."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    element_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message", "element_id")
    @classmethod
    def validate_strings(cls, v: str | None) -> str | None:
        return _reject_control_chars(v, "ExtractionWarning field")


class ExtractionError(ImmutableExtractionBase):
    """Structured failure description."""

    code: ExtractionErrorCode
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        return _validate_utc(v)  # type: ignore[return-value]

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        _reject_control_chars(v, "ExtractionError message")
        return v


# -----------------------------------------------------------------------------
# Engine & Document Metadata
# -----------------------------------------------------------------------------


class ExtractorDescriptor(ImmutableExtractionBase):
    """Descriptor capturing the exact extraction engine, version, and configuration."""

    engine_name: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    config_parameters: dict[str, Any] = Field(default_factory=dict)
    extractor_config_sha256: str

    @field_validator("extractor_config_sha256")
    @classmethod
    def validate_config_hash(cls, v: str) -> str:
        return _validate_sha256_hex(v, "extractor_config_sha256")  # type: ignore[return-value]

    @field_validator("engine_name", "engine_version")
    @classmethod
    def validate_strings(cls, v: str) -> str:
        _reject_control_chars(v, "ExtractorDescriptor field")
        return v


class DocumentMetadata(ImmutableExtractionBase):
    """Normalized document-level metadata."""

    title: str | None = None
    author: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    page_count: int | None = Field(default=None, ge=1)
    element_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    word_count: int | None = Field(default=None, ge=0)
    character_count: int | None = Field(default=None, ge=0)
    language: str | None = None
    custom_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "modified_at")
    @classmethod
    def validate_timestamps(cls, v: datetime | None) -> datetime | None:
        return _validate_utc(v)

    @field_validator("title", "author", "language")
    @classmethod
    def validate_strings(cls, v: str | None) -> str | None:
        return _reject_control_chars(v, "DocumentMetadata field")


# -----------------------------------------------------------------------------
# Canonical Root NormalizedDocument Model
# -----------------------------------------------------------------------------


class NormalizedDocument(ImmutableExtractionBase):
    """The canonical root contract for all extracted content in Javed.

    Provides strict cryptographic identity separation, deterministic canonical
    serialization, and fail-closed validation.
    """

    schema_version: str = "1.0.0"
    document_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    ingestion_id: str = Field(min_length=1)
    source_sha256: str
    normalized_output_sha256: str | None = None

    source: SourceDescriptor
    authenticated_context: AuthenticatedSourceContext | None = None
    extractor: ExtractorDescriptor
    metadata: DocumentMetadata
    elements: list[ExtractionElement] = Field(default_factory=list)
    full_text: str | None = None
    full_markdown: str | None = None

    status: ExtractionStatus = ExtractionStatus.SUCCESS
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    errors: list[ExtractionError] = Field(default_factory=list)
    extracted_at: datetime

    @field_validator("extracted_at")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        return _validate_utc(v)  # type: ignore[return-value]

    @field_validator("source_sha256", "normalized_output_sha256")
    @classmethod
    def validate_hashes(cls, v: str | None) -> str | None:
        return _validate_sha256_hex(v, "SHA-256 hash")

    @model_validator(mode="after")
    def validate_document_contracts(self) -> NormalizedDocument:
        _reject_control_chars(self.document_id, "document_id")
        _reject_control_chars(self.version_id, "version_id")
        _reject_control_chars(self.ingestion_id, "ingestion_id")

        # Element IDs must be strictly unique within the document
        seen_element_ids: set[str] = set()
        table_elements_count = 0
        for elem in self.elements:
            if elem.element_id in seen_element_ids:
                raise ValueError(
                    f"Duplicate element_id detected in NormalizedDocument: {elem.element_id!r}"
                )
            seen_element_ids.add(elem.element_id)
            if elem.table is not None:
                table_elements_count += 1

        # Metadata consistency checks
        if self.metadata.element_count != len(self.elements):
            msg = f"element_count mismatch: {self.metadata.element_count} != {len(self.elements)}"
            raise ValueError(msg)
        if self.metadata.table_count != table_elements_count:
            msg = f"table_count mismatch: {self.metadata.table_count} != {table_elements_count}"
            raise ValueError(msg)

        # Status contract verification
        if self.status == ExtractionStatus.SUCCESS:
            if len(self.errors) > 0:
                raise ValueError("SUCCESS status document cannot contain extraction errors")

        elif self.status == ExtractionStatus.FAILED:
            if len(self.errors) == 0:
                raise ValueError(
                    "FAILED status document must contain at least one extraction error"
                )

        elif self.status == ExtractionStatus.PARTIAL_SUCCESS:
            if len(self.warnings) == 0 and len(self.errors) == 0:
                raise ValueError(
                    "PARTIAL_SUCCESS status document requires at least one warning or error signal"
                )

        return self

    def to_canonical_dict(self) -> dict[str, Any]:
        """Produce a canonical dictionary representation for hashing.

        Identity Distinction:
        - Normalized-Content Identity (`normalized_output_sha256`): Cryptographic hash
          of the exact extracted content and structure produced by this method.
        - Full Extraction-Record Identity: Composed of `document_id` (stable logical asset
          identity), `version_id` (revision identifier), `ingestion_id` (attempt UUID),
          `source_sha256` (raw source bytes), and `extractor_config_sha256`.

        Exact Fields Included in Canonical Payload:
        - `schema_version`: String schema version.
        - `document_id`: Logical asset identifier.
        - `version_id`: Revision identifier.
        - `ingestion_id`: Attempt identifier.
        - `source_sha256`: Hash of unparsed input bytes.
        - `source`: Complete `SourceDescriptor` model.
        - `authenticated_context`: `AuthenticatedSourceContext` or None.
        - `extractor`: `ExtractorDescriptor` (engine, version, config, config hash).
        - `metadata`: `DocumentMetadata` (counts, author, language, etc.).
        - `elements`: Ordered array of `ExtractionElement` instances (including tables).
        - `full_text`: Optional concatenated plain text.
        - `full_markdown`: Optional concatenated markdown.
        - `status`: ExtractionStatus enum value.
        - `warnings`: Array of `ExtractionWarning` models.
        - `errors`: Array of `ExtractionError` models.
        - `extracted_at`: UTC timestamp string.

        Excluded Fields:
        - `normalized_output_sha256`: Strictly excluded to prevent circular hash dependency.
        """
        data = self.model_dump(
            mode="json",
            exclude={"normalized_output_sha256"},
            exclude_none=False,
        )
        return data

    def to_canonical_json(self) -> str:
        """Serialize the canonical payload deterministically.

        Ensures lexicographical key ordering, uniform separators, and UTF-8 encoding.
        """
        canonical_dict = self.to_canonical_dict()
        return json.dumps(
            canonical_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    def compute_canonical_sha256(self) -> str:
        """Compute the SHA-256 digest of the canonical normalized content."""
        canonical_json = self.to_canonical_json()
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def with_computed_output_hash(self) -> NormalizedDocument:
        """Return a copy of the document with `normalized_output_sha256` populated."""
        computed_hash = self.compute_canonical_sha256()
        return self.model_copy(update={"normalized_output_sha256": computed_hash})
