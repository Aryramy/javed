"""Pydantic schemas for extraction REST API endpoints and telemetry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from javed.extraction.storage import (
    StoredDocumentSummary,
    StoredExtractionRecord,
    StoredTableInfo,
)


class CrawlRequest(BaseModel):
    """Payload requesting web crawl and content extraction."""

    url: str = Field(description="Target public HTTP or HTTPS web URL to extract.")
    strategy: Literal["static", "rendered"] = Field(
        default="static",
        description="Acquisition strategy: 'static' or 'rendered'.",
    )
    max_chars: int = Field(
        default=25000,
        description="Maximum characters of extracted text/markdown to include in the preview.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Timeout for the web crawl operation in seconds.",
    )

    @field_validator("url")
    @classmethod
    def validate_url_syntax(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("URL cannot be empty")
        if not (s.startswith("http://") or s.startswith("https://")):
            raise ValueError("URL must begin with http:// or https://")
        return s

    @field_validator("max_chars")
    @classmethod
    def validate_max_chars(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_chars must be strictly positive")
        return min(v, 100000)

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout_seconds must be strictly positive")
        return min(v, 120.0)


class TableSummary(BaseModel):
    """Compact summary of a structured table extracted from a document."""

    table_id: str | None = Field(default=None, description="Unique table identifier.")
    row_count: int = Field(description="Number of data rows in table.")
    column_count: int = Field(description="Number of columns in table.")
    headers: list[str] = Field(default_factory=list, description="Column header strings.")
    sheet_name: str | None = Field(default=None, description="Source sheet name if spreadsheet.")
    markdown: str = Field(default="", description="Markdown representation of table.")


class ExtractionResponse(BaseModel):
    """Unified response returned after document or web content extraction."""

    success: bool = Field(description="Whether the extraction succeeded.")
    document_id: str = Field(description="Unique identifier for the stored document entity.")
    extraction_id: str = Field(description="Unique identifier for this specific extraction run.")
    version_id: str = Field(description="Content-addressed version hash.")
    source_uri: str | None = Field(default=None, description="Original source URI or web URL.")
    original_display_name: str = Field(description="Original sanitized file or title name.")
    mime_type: str = Field(description="Verified MIME type of the source.")
    title: str | None = Field(default=None, description="Extracted document title.")
    is_duplicate: bool = Field(
        default=False,
        description="Whether identical content was already ingested.",
    )
    is_new_version: bool = Field(
        default=False,
        description="Whether this represents a new version of existing URI.",
    )
    status: str = Field(description="Execution status ('SUCCESS', 'PARTIAL_SUCCESS', etc.).")
    element_count: int = Field(default=0, description="Total extracted semantic elements.")
    table_count: int = Field(default=0, description="Total structured tables extracted.")
    page_count: int | None = Field(default=None, description="Total pages if paginated document.")
    word_count: int | None = Field(default=None, description="Total word count in document body.")
    tables: list[TableSummary] = Field(
        default_factory=list,
        description="Extracted tables summaries.",
    )
    text_preview: str = Field(default="", description="Preview of normalized plain text.")
    markdown_preview: str = Field(default="", description="Preview of normalized markdown.")
    is_truncated: bool = Field(
        default=False,
        description="Whether text/markdown previews are truncated.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Security and extraction warning messages.",
    )


class DocumentListResponse(BaseModel):
    """Paginated list of stored document summaries from the metadata registry."""

    items: list[StoredDocumentSummary] = Field(description="List of document entities.")
    total: int = Field(description="Total count of documents matching filter.")
    limit: int = Field(description="Pagination limit.")
    offset: int = Field(description="Pagination offset.")


class DocumentDetailResponse(BaseModel):
    """Full detail view of an ingested document entity with telemetry and table exports."""

    document: StoredDocumentSummary = Field(description="Document summary entity.")
    extractions: list[StoredExtractionRecord] = Field(
        default_factory=list, description="Historical extraction execution records."
    )
    tables: list[StoredTableInfo] = Field(
        default_factory=list, description="Standalone exported table artifacts."
    )
    text_preview: str = Field(default="", description="Full canonical plain text.")
    markdown_preview: str = Field(default="", description="Full canonical markdown.")
    is_truncated: bool = Field(default=False, description="Whether previews were truncated.")


class ExtractionTelemetryResponse(BaseModel):
    """Developer mode telemetry describing extraction pipeline statistics and health."""

    total_documents: int = Field(description="Total unique documents stored in SQLite.")
    total_extractions: int = Field(description="Total extraction runs recorded.")
    total_tables: int = Field(description="Total extracted table artifacts stored.")
    db_path: str = Field(description="SQLite database path.")
    sources_dir: str = Field(description="Raw source storage directory.")
    extractions_dir: str = Field(description="Canonical JSON extractions directory.")
    tables_dir: str = Field(description="Exported tables directory.")
    supported_document_formats: list[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".xlsx"],
        description="Supported local document extensions.",
    )
    supported_web_strategies: list[str] = Field(
        default_factory=lambda: ["static", "rendered"],
        description="Supported web crawl strategies.",
    )
    storage_healthy: bool = Field(
        default=True,
        description="Whether extraction storage is healthy.",
    )


class DeleteDocumentResponse(BaseModel):
    """Response confirming document deletion and artifact cleanup."""

    success: bool = Field(description="Whether the deletion request completed.")
    document_id: str = Field(description="Identifier of the deleted document.")
    deleted: bool = Field(description="Whether the document entity was found and removed.")
    message: str = Field(description="Human-readable outcome description.")
