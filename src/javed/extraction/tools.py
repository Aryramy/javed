"""LangChain agent extraction tools and HITL ingestion gating for Project Javed.

Provides Pydantic-validated, LangChain-compatible structured tools for web and local
document extraction (PDF, Word DOCX, Excel XLSX).
Integrates:
1. Crawl4AI web extraction with zero-trust URL and SSRF validation.
2. Docling document extraction with native local parsing and preflight checks.
3. ExtractionStorageManager metadata persistence, content deduplication, and versioning.
4. LangGraph agent runtime binding and 4-tier permission sandbox integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from javed.extraction.documents import (
    DoclingDocumentExtractor,
    DocumentExtractionSecurityError,
)
from javed.extraction.schema import SourceType
from javed.extraction.security import ExtractionSecurityGuard
from javed.extraction.storage import (
    ExtractionStorageManager,
    StorageConfig,
)
from javed.extraction.web import (
    Crawl4AIWebExtractor,
    WebExtractionConfig,
    WebExtractionSecurityError,
    WebExtractionStrategy,
    validate_web_url,
)

logger = logging.getLogger("javed.extraction.tools")

# Default character limits to prevent context window exhaustion
DEFAULT_PREVIEW_MAX_CHARS = 25000
DEFAULT_DETAILS_MAX_CHARS = 10000

# Permitted document extensions for local extraction
PERMITTED_DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx"})


# -----------------------------------------------------------------------------
# Input Schema Definitions
# -----------------------------------------------------------------------------


class ExtractWebPageInput(BaseModel):
    """Input arguments for extract_web_page tool."""

    url: str = Field(
        description=(
            "The target HTTP or HTTPS URL to extract content from "
            "(e.g. 'https://example.com/report')."
        )
    )
    strategy: str = Field(
        default="static",
        description=(
            "Extraction strategy: 'static' (fast, lightweight, SSRF checked) "
            "or 'rendered' (browser-rendered dynamic DOM)."
        ),
    )
    max_chars: int = Field(
        default=DEFAULT_PREVIEW_MAX_CHARS,
        description=(
            "Maximum characters of text/markdown content to return in response "
            "to avoid context exhaustion."
        ),
    )

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in ("static", "rendered"):
            raise ValueError("strategy must be either 'static' or 'rendered'")
        return s

    @field_validator("max_chars")
    @classmethod
    def validate_max_chars(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_chars must be strictly positive")
        return min(v, 100000)


class ExtractDocumentInput(BaseModel):
    """Input arguments for extract_document tool."""

    file_path: str = Field(
        description=(
            "Local path to the document file to parse and extract (supports PDF, DOCX, XLSX)."
        )
    )
    max_chars: int = Field(
        default=DEFAULT_PREVIEW_MAX_CHARS,
        description="Maximum characters of text/markdown content to return in response.",
    )

    @field_validator("file_path")
    @classmethod
    def validate_path_syntax(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("file_path cannot be empty")
        if "\x00" in s:
            raise ValueError("file_path cannot contain null bytes")
        return s

    @field_validator("max_chars")
    @classmethod
    def validate_max_chars(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_chars must be strictly positive")
        return min(v, 100000)


class ListIngestedDocumentsInput(BaseModel):
    """Input arguments for list_ingested_documents tool."""

    limit: int = Field(
        default=20,
        description="Maximum number of stored documents to return (max 100).",
    )
    offset: int = Field(
        default=0,
        description="Pagination offset index.",
    )
    source_type: str | None = Field(
        default=None,
        description="Optional filter by source type: 'web_page', 'pdf', 'docx', 'xlsx'.",
    )

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("limit must be strictly positive")
        return min(v, 100)

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError("offset cannot be negative")
        return v


class GetDocumentDetailsInput(BaseModel):
    """Input arguments for get_document_details tool."""

    document_id: str = Field(
        description="The unique document identifier to retrieve metadata, tables, and content for."
    )
    include_text: bool = Field(
        default=True,
        description="Whether to include full extracted text and markdown content.",
    )
    max_chars: int = Field(
        default=DEFAULT_DETAILS_MAX_CHARS,
        description="Maximum characters of text/markdown to return if include_text is True.",
    )

    @field_validator("document_id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("document_id cannot be empty")
        return s


# -----------------------------------------------------------------------------
# Path Security Verification
# -----------------------------------------------------------------------------


def validate_safe_local_document_path(
    file_path: str | Path,
    allowed_roots: list[Path | str] | None = None,
) -> Path:
    """Validate that a local document path exists, has a permitted extension,
    and does not escape allowed roots.

    Raises:
        DocumentExtractionSecurityError: If the path is invalid, escapes boundaries,
            or has an unapproved extension.
        FileNotFoundError: If the file does not exist.
    """
    path_str = str(file_path).strip()
    if not path_str:
        raise DocumentExtractionSecurityError("Document path cannot be empty")
    if "\x00" in path_str:
        raise DocumentExtractionSecurityError("Document path contains prohibited null characters")

    resolved = Path(path_str).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Document file not found: {resolved}")

    # Extension validation
    ext = resolved.suffix.lower()
    if ext not in PERMITTED_DOCUMENT_EXTENSIONS:
        permitted_list = sorted(PERMITTED_DOCUMENT_EXTENSIONS)
        raise DocumentExtractionSecurityError(
            f"Unsupported document format '{ext}'. Permitted formats: {permitted_list}"
        )

    # Allowed boundary validation if roots are configured
    if allowed_roots:
        resolved_roots = [Path(r).resolve() for r in allowed_roots]
        is_safe = any(resolved.is_relative_to(root) for root in resolved_roots)
        if not is_safe:
            raise DocumentExtractionSecurityError(
                f"Access denied: document '{resolved}' escapes allowed directories"
            )

    return resolved


# -----------------------------------------------------------------------------
# Extraction Tools Manager (Session & Lifecycle)
# -----------------------------------------------------------------------------


class ExtractionToolsManager:
    """Session manager coordinating extraction tools, extractors, and persistence."""

    def __init__(
        self,
        storage_manager: ExtractionStorageManager | None = None,
        storage_config: StorageConfig | None = None,
        allowed_document_roots: list[Path | str] | None = None,
        allow_loopback_for_testing: bool = False,
    ) -> None:
        self.storage = storage_manager or ExtractionStorageManager(config=storage_config)
        self.allowed_document_roots = allowed_document_roots
        self.allow_loopback_for_testing = allow_loopback_for_testing
        self._web_extractor: Crawl4AIWebExtractor | None = None
        self._doc_extractor: DoclingDocumentExtractor | None = None
        self._security_guard = ExtractionSecurityGuard()
        self._closed = False

    def get_web_extractor(self) -> Crawl4AIWebExtractor:
        """Lazily initialize and return the Crawl4AI web extractor."""
        if self._web_extractor is None:
            config = WebExtractionConfig(
                allow_loopback_for_testing=self.allow_loopback_for_testing,
                raise_on_error=True,
            )
            self._web_extractor = Crawl4AIWebExtractor(config=config)
        return self._web_extractor

    def get_doc_extractor(self) -> DoclingDocumentExtractor:
        """Lazily initialize and return the Docling document extractor."""
        if self._doc_extractor is None:
            self._doc_extractor = DoclingDocumentExtractor()
        return self._doc_extractor

    def close(self) -> None:
        """Synchronously close extractors, security guard thread pools, and storage."""
        if self._closed:
            return
        self._closed = True

        if self._web_extractor is not None:
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    loop.create_task(self._web_extractor.close())
                else:
                    asyncio.run(self._web_extractor.close())
            except Exception as e:
                logger.warning("Error closing web extractor: %s", e)
            self._web_extractor = None

        if self._doc_extractor is not None:
            try:
                self._doc_extractor.close()
            except Exception as e:
                logger.warning("Error closing document extractor: %s", e)
            self._doc_extractor = None

        if self._security_guard is not None:
            try:
                self._security_guard.close()
            except Exception as e:
                logger.warning("Error closing security guard: %s", e)

        if self.storage is not None:
            try:
                self.storage.close()
            except Exception as e:
                logger.warning("Error closing storage manager: %s", e)

    async def close_async(self) -> None:
        """Asynchronously close extractors, thread pools, and storage."""
        if self._closed:
            return
        self._closed = True

        if self._web_extractor is not None:
            try:
                await self._web_extractor.close()
            except Exception as e:
                logger.warning("Error closing web extractor async: %s", e)
            self._web_extractor = None

        if self._doc_extractor is not None:
            try:
                self._doc_extractor.close()
            except Exception as e:
                logger.warning("Error closing document extractor async: %s", e)
            self._doc_extractor = None

        if self._security_guard is not None:
            try:
                self._security_guard.close()
            except Exception as e:
                logger.warning("Error closing security guard async: %s", e)

        if self.storage is not None:
            try:
                await self.storage.close_async()
            except Exception as e:
                logger.warning("Error closing storage manager async: %s", e)

    def __enter__(self) -> ExtractionToolsManager:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> ExtractionToolsManager:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close_async()

    # -------------------------------------------------------------------------
    # Core Tool Execution Implementations
    # -------------------------------------------------------------------------

    async def extract_web_page(
        self,
        url: str,
        strategy: str = "static",
        max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    ) -> dict[str, Any]:
        """Extract structured content from a public web page URL using Crawl4AI."""
        try:
            # 1. Zero-trust URL & SSRF validation
            validate_web_url(url, allow_loopback_for_testing=self.allow_loopback_for_testing)

            # 2. Extract content via Crawl4AI
            strat = (
                WebExtractionStrategy.STATIC
                if strategy.lower() == "static"
                else WebExtractionStrategy.RENDERED
            )
            extractor = self.get_web_extractor()
            doc = await extractor.extract_url(url=url, strategy=strat)

            # 3. Persist and deduplicate via storage manager
            ingestion = await self.storage.store_document_async(doc)

            # 4. Build sanitized response payload
            text_content = doc.full_text or ""
            md_content = doc.full_markdown or ""
            is_truncated = len(text_content) > max_chars or len(md_content) > max_chars

            tables_summary = []
            for t in doc.tables:
                tables_summary.append(
                    {
                        "table_id": t.table_id,
                        "row_count": t.row_count,
                        "column_count": t.column_count,
                        "headers": t.headers,
                        "markdown": t.to_markdown() if hasattr(t, "to_markdown") else "",
                    }
                )

            return {
                "success": True,
                "document_id": ingestion.document_id,
                "extraction_id": ingestion.extraction_id,
                "version_id": ingestion.version_id,
                "source_uri": doc.source.source_uri,
                "title": doc.metadata.title,
                "is_duplicate": ingestion.is_duplicate,
                "is_new_version": ingestion.is_new_version,
                "status": doc.status.value,
                "element_count": len(doc.elements),
                "table_count": doc.metadata.table_count,
                "word_count": doc.metadata.word_count,
                "tables": tables_summary,
                "text_preview": text_content[:max_chars],
                "markdown_preview": md_content[:max_chars],
                "is_truncated": is_truncated,
                "warnings": [w.message for w in doc.warnings],
            }

        except WebExtractionSecurityError as sec_err:
            logger.warning("Security rejection during extract_web_page for '%s': %s", url, sec_err)
            return {
                "success": False,
                "error": f"Security Policy Violation: {sec_err}",
                "error_type": sec_err.__class__.__name__,
            }
        except Exception as exc:
            logger.error("Failed extracting web page '%s': %s", url, exc, exc_info=True)
            return {
                "success": False,
                "error": f"Extraction failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def extract_document(
        self,
        file_path: str,
        max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    ) -> dict[str, Any]:
        """Extract structured content from a local document (PDF, DOCX, XLSX) using Docling."""
        try:
            # 1. Path safety and extension validation
            safe_path = validate_safe_local_document_path(
                file_path=file_path,
                allowed_roots=self.allowed_document_roots,
            )

            # 2. Extract content via Docling
            extractor = self.get_doc_extractor()
            doc = await extractor.extract_file_async(safe_path)

            # 3. Read raw bytes for content-addressed storage
            raw_bytes = await asyncio.to_thread(safe_path.read_bytes)

            # 4. Persist and deduplicate via storage manager
            ingestion = await self.storage.store_document_async(doc, raw_bytes=raw_bytes)

            # 5. Build sanitized response payload
            text_content = doc.full_text or ""
            md_content = doc.full_markdown or ""
            is_truncated = len(text_content) > max_chars or len(md_content) > max_chars

            tables_summary = []
            for t in doc.tables:
                tables_summary.append(
                    {
                        "table_id": t.table_id,
                        "row_count": t.row_count,
                        "column_count": t.column_count,
                        "headers": t.headers,
                        "sheet_name": t.sheet_name,
                        "markdown": t.to_markdown() if hasattr(t, "to_markdown") else "",
                    }
                )

            return {
                "success": True,
                "document_id": ingestion.document_id,
                "extraction_id": ingestion.extraction_id,
                "version_id": ingestion.version_id,
                "original_display_name": doc.source.original_display_name,
                "mime_type": doc.source.mime_type,
                "title": doc.metadata.title,
                "is_duplicate": ingestion.is_duplicate,
                "is_new_version": ingestion.is_new_version,
                "status": doc.status.value,
                "element_count": len(doc.elements),
                "table_count": doc.metadata.table_count,
                "page_count": doc.metadata.page_count,
                "word_count": doc.metadata.word_count,
                "tables": tables_summary,
                "text_preview": text_content[:max_chars],
                "markdown_preview": md_content[:max_chars],
                "is_truncated": is_truncated,
                "warnings": [w.message for w in doc.warnings],
            }

        except DocumentExtractionSecurityError as sec_err:
            logger.warning(
                "Security rejection during extract_document for '%s': %s", file_path, sec_err
            )
            return {
                "success": False,
                "error": f"Security Policy Violation: {sec_err}",
                "error_type": sec_err.__class__.__name__,
            }
        except FileNotFoundError as fnf_err:
            return {
                "success": False,
                "error": str(fnf_err),
                "error_type": "FileNotFoundError",
            }
        except Exception as exc:
            logger.error("Failed extracting document '%s': %s", file_path, exc, exc_info=True)
            return {
                "success": False,
                "error": f"Document extraction failed: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def list_ingested_documents(
        self,
        limit: int = 20,
        offset: int = 0,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        """List previously ingested and extracted documents from the metadata registry."""
        try:
            st: SourceType | None = None
            if source_type:
                try:
                    st = SourceType(source_type.strip().lower())
                except ValueError:
                    return {
                        "success": False,
                        "error": (
                            f"Invalid source_type '{source_type}'. "
                            f"Valid types: {[s.value for s in SourceType]}"
                        ),
                        "error_type": "ValueError",
                    }

            docs = await self.storage.list_documents_async(
                limit=limit,
                offset=offset,
                source_type=st,
            )

            summaries = [doc.model_dump(mode="json") for doc in docs]
            return {
                "success": True,
                "count": len(summaries),
                "limit": limit,
                "offset": offset,
                "documents": summaries,
            }

        except Exception as exc:
            logger.error("Failed listing ingested documents: %s", exc, exc_info=True)
            return {
                "success": False,
                "error": f"Failed listing documents: {exc}",
                "error_type": exc.__class__.__name__,
            }

    async def get_document_details(
        self,
        document_id: str,
        include_text: bool = True,
        max_chars: int = DEFAULT_DETAILS_MAX_CHARS,
    ) -> dict[str, Any]:
        """Retrieve detailed metadata, structured tables, and content for an ingested document."""
        try:
            doc_summary = await self.storage.get_document_async(document_id)
            if not doc_summary:
                return {
                    "success": False,
                    "error": f"Document '{document_id}' not found in registry",
                    "error_type": "DocumentNotFoundError",
                }

            meta_dict: dict[str, Any] = {}
            if doc_summary.metadata_json:
                try:
                    meta_dict = json.loads(doc_summary.metadata_json)
                except Exception:
                    meta_dict = {}

            result: dict[str, Any] = {
                "success": True,
                "document_id": doc_summary.document_id,
                "source_type": doc_summary.source_type.value,
                "original_display_name": doc_summary.original_display_name,
                "source_uri": doc_summary.source_uri,
                "source_title": doc_summary.source_title,
                "mime_type": doc_summary.mime_type,
                "source_sha256": doc_summary.source_sha256,
                "normalized_content_sha256": doc_summary.normalized_content_sha256,
                "version_count": doc_summary.version_count,
                "current_version_id": doc_summary.current_version_id,
                "current_extraction_id": doc_summary.current_extraction_id,
                "first_ingested_at": doc_summary.first_ingested_at.isoformat(),
                "last_ingested_at": doc_summary.last_ingested_at.isoformat(),
                "metadata": meta_dict,
            }

            # Retrieve extraction record details
            record = await asyncio.to_thread(
                self.storage.get_extraction_record, doc_summary.current_extraction_id
            )
            if record:
                result["extraction_record"] = {
                    "extractor_name": record.extractor_name,
                    "extractor_version": record.extractor_version,
                    "extractor_strategy": record.extractor_strategy,
                    "status": record.status.value,
                    "element_count": record.element_count,
                    "table_count": record.table_count,
                    "word_count": record.word_count,
                    "page_count": record.page_count,
                    "warning_count": record.warning_count,
                    "error_count": record.error_count,
                }

            # Retrieve standalone table exports
            tables = await asyncio.to_thread(self.storage.list_tables, doc_summary.document_id)
            result["tables"] = [tbl.model_dump(mode="json") for tbl in tables]

            # Optionally reload full document and include text/markdown
            if include_text and doc_summary.current_extraction_id:
                normalized_doc = await self.storage.load_normalized_document_async(
                    doc_summary.current_extraction_id
                )
                if normalized_doc:
                    full_txt = normalized_doc.full_text or ""
                    full_md = normalized_doc.full_markdown or ""
                    result["text_content"] = full_txt[:max_chars]
                    result["markdown_content"] = full_md[:max_chars]
                    result["is_truncated"] = len(full_txt) > max_chars or len(full_md) > max_chars

            return result

        except Exception as exc:
            logger.error("Failed getting document details for '%s': %s", document_id, exc)
            return {
                "success": False,
                "error": f"Failed getting document details: {exc}",
                "error_type": exc.__class__.__name__,
            }

    def get_tools(self) -> list[StructuredTool]:
        """Return the LangChain structured tools bound to this extraction manager."""
        return create_extraction_tools(self)


# -----------------------------------------------------------------------------
# LangChain Structured Tool Factory
# -----------------------------------------------------------------------------


def create_extraction_tools(manager: ExtractionToolsManager) -> list[StructuredTool]:
    """Create and return the 4 deterministic extraction tools bound to an ExtractionToolsManager."""

    async def _extract_web_page(
        url: str,
        strategy: str = "static",
        max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    ) -> dict[str, Any]:
        return await manager.extract_web_page(url=url, strategy=strategy, max_chars=max_chars)

    async def _extract_document(
        file_path: str,
        max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
    ) -> dict[str, Any]:
        return await manager.extract_document(file_path=file_path, max_chars=max_chars)

    async def _list_ingested_documents(
        limit: int = 20,
        offset: int = 0,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        return await manager.list_ingested_documents(
            limit=limit, offset=offset, source_type=source_type
        )

    async def _get_document_details(
        document_id: str,
        include_text: bool = True,
        max_chars: int = DEFAULT_DETAILS_MAX_CHARS,
    ) -> dict[str, Any]:
        return await manager.get_document_details(
            document_id=document_id, include_text=include_text, max_chars=max_chars
        )

    return [
        StructuredTool.from_function(
            coroutine=_extract_web_page,
            name="extract_web_page",
            description=(
                "Extract structured text, markdown, and tables from a public web page URL "
                "using Crawl4AI. Enforces SSRF and redirect validation, dedupes content, "
                "and persists into the extraction registry."
            ),
            args_schema=ExtractWebPageInput,
        ),
        StructuredTool.from_function(
            coroutine=_extract_document,
            name="extract_document",
            description=(
                "Extract structured text, heading hierarchy, and tables from a local document "
                "(PDF, Word DOCX, Excel XLSX) using Docling. Enforces security preflight, "
                "content deduplication, and persistence."
            ),
            args_schema=ExtractDocumentInput,
        ),
        StructuredTool.from_function(
            coroutine=_list_ingested_documents,
            name="list_ingested_documents",
            description=(
                "List previously ingested and extracted documents from the metadata registry "
                "with versioning and summary statistics."
            ),
            args_schema=ListIngestedDocumentsInput,
        ),
        StructuredTool.from_function(
            coroutine=_get_document_details,
            name="get_document_details",
            description=(
                "Retrieve detailed metadata, structured tables, and text/markdown content "
                "for a previously ingested document by its document_id."
            ),
            args_schema=GetDocumentDetailsInput,
        ),
    ]


def create_extraction_tools_inventory(
    manager: ExtractionToolsManager | None = None,
) -> list[StructuredTool]:
    """Create and return the deterministic extraction tools inventory."""
    active_mgr = manager if manager is not None else ExtractionToolsManager()
    return active_mgr.get_tools()
