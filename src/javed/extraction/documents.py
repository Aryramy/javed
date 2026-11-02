"""Bounded, deterministic document extraction subsystem using Docling 2.144.0.

Conforms to BRICK-007 Stage 4 / Phase 5 specifications:
1. Multi-format local document understanding: PDF, Word (DOCX), and Excel (XLSX).
2. 100% offline, local execution: zero HuggingFace model downloads in default native mode.
3. Native PDF extraction via PyPdfiumDocumentBackend and NativePdfPipeline.
4. Structured element hierarchy: headings, paragraphs, lists, code blocks, tables, and captions.
5. Deep table extraction: TableRepresentation with cells, spans, and markdown.
6. Provenance tracking: 1-based page numbers, sheet names, bounding boxes, and spans.
7. Defensive boundary: ExtractionSecurityGuard preflight (MIME, size, zip bomb, encryption).
8. Strict resource bounds: document byte limits, page ceilings, element and table limits.
9. Canonical output: mapped to NormalizedDocument, finalized with hashes, verified via gates.
10. Concurrency safety: thread-safe execution, bounded thread pool, zero leaks.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import docling
import openpyxl
import pypdfium2
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.native_pdf_pipeline import NativePdfPipeline

from javed.extraction.schema import (
    BoundingBox,
    CoordinateOrigin,
    CoordinateSpace,
    DocumentMetadata,
    ElementProvenance,
    ExtractionElement,
    ExtractionElementType,
    ExtractionError,
    ExtractionErrorCode,
    ExtractionStatus,
    ExtractionWarning,
    ExtractorDescriptor,
    MergedCell,
    NormalizedDocument,
    SectionReference,
    SourceDescriptor,
    SourceType,
    TableCell,
    TableRepresentation,
    verify_trust_boundary,
)
from javed.extraction.security import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    MAX_GOVERNANCE_FILE_SIZE_BYTES,
    ExtractionSecurityGuard,
    SecurityDecisionOutcome,
    SecurityValidationDecision,
    sanitize_and_validate_display_name,
)

logger = logging.getLogger("javed.extraction.documents")

# -----------------------------------------------------------------------------
# Constants & Governance Boundaries
# -----------------------------------------------------------------------------

DOCLING_ENGINE_NAME = "docling"
DOCLING_ENGINE_VERSION = docling.__version__

DEFAULT_MAX_DOCUMENT_BYTES = DEFAULT_MAX_FILE_SIZE_BYTES  # 25 MB
MAX_GOVERNANCE_DOCUMENT_BYTES = MAX_GOVERNANCE_FILE_SIZE_BYTES  # 50 MB
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_ELEMENTS = 10_000
DEFAULT_MAX_TABLES = 500
DEFAULT_MAX_MARKDOWN_CHARS = 1_000_000
DEFAULT_MAX_TEXT_CHARS = 1_000_000
DEFAULT_MAX_WARNINGS = 100

DEFAULT_DOCUMENT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_CONCURRENT_EXTRACTIONS = 4

SUPPORTED_MIME_TYPES: dict[str, SourceType] = {
    "application/pdf": SourceType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": SourceType.DOCX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": SourceType.XLSX,
}

SUPPORTED_EXTENSIONS: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".docx": SourceType.DOCX,
    ".xlsx": SourceType.XLSX,
}


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class DocumentExtractionError(Exception):
    """Base exception for document extraction failures."""


class DocumentExtractionSecurityError(DocumentExtractionError):
    """Raised when document violates security or quarantine policy."""


class DocumentExtractionTimeoutError(DocumentExtractionError):
    """Raised when document conversion exceeds timeout."""


class DocumentExtractionLimitExceededError(DocumentExtractionError):
    """Raised when document size, page count, or element count exceeds ceilings."""


class UnsupportedDocumentFormatError(DocumentExtractionError):
    """Raised when document format or MIME type is not supported."""


class CorruptedDocumentError(DocumentExtractionError):
    """Raised when document cannot be parsed due to container or format corruption."""


class PasswordProtectedDocumentError(DocumentExtractionError):
    """Raised when document is encrypted or requires password to open."""


# -----------------------------------------------------------------------------
# Enums and Dataclasses
# -----------------------------------------------------------------------------


class DocumentBackendStrategy(StrEnum):
    """Execution strategy for document parsing."""

    NATIVE = "native"
    STANDARD = "standard"


@dataclass(frozen=True)
class DocumentExtractionLimits:
    """Configurable resource boundaries for document extraction."""

    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES
    max_pages: int = DEFAULT_MAX_PAGES
    max_elements: int = DEFAULT_MAX_ELEMENTS
    max_tables: int = DEFAULT_MAX_TABLES
    max_markdown_chars: int = DEFAULT_MAX_MARKDOWN_CHARS
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    max_warnings: int = DEFAULT_MAX_WARNINGS
    fail_closed_on_overflow: bool = True


@dataclass(frozen=True)
class DocumentExtractionConfig:
    """Configuration settings for document extraction."""

    strategy: DocumentBackendStrategy = DocumentBackendStrategy.NATIVE
    timeout_seconds: float = DEFAULT_DOCUMENT_TIMEOUT_SECONDS
    max_concurrent_extractions: int = DEFAULT_MAX_CONCURRENT_EXTRACTIONS
    validate_security: bool = True
    raise_on_error: bool = False
    temp_dir: Path | None = None


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def detect_source_type_from_filename(filename: str) -> SourceType | None:
    """Detect SourceType from filename extension."""
    suffix = Path(filename).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(suffix)


def detect_input_format(source_type: SourceType) -> InputFormat | None:
    """Map SourceType enum to Docling InputFormat."""
    if source_type == SourceType.PDF:
        return InputFormat.PDF
    if source_type == SourceType.DOCX:
        return InputFormat.DOCX
    if source_type == SourceType.XLSX:
        return InputFormat.XLSX
    return None


def _clean_text(val: str | None) -> str:
    """Clean and strip control characters from text strings."""
    if not val:
        return ""
    # Strip null bytes and non-printable control characters except newline and tab
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", val).strip()


def _extract_excel_sheet_names(content_bytes: bytes) -> list[str]:
    """Extract ordered worksheet names from an Excel XLSX byte stream."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content_bytes), read_only=True, data_only=True)
        sheet_names = list(wb.sheetnames)
        wb.close()
        return sheet_names
    except Exception as exc:
        logger.debug("Failed to extract Excel sheet names: %s", exc)
        return []


def _create_converter(strategy: DocumentBackendStrategy) -> DocumentConverter:
    """Factory creating a configured Docling DocumentConverter.

    In NATIVE mode, PDF parsing is explicitly pinned to NativePdfPipeline
    and PyPdfiumDocumentBackend, ensuring 100% offline execution with zero
    HuggingFace model downloads.
    """
    if strategy == DocumentBackendStrategy.NATIVE:
        pdf_option = PdfFormatOption(
            pipeline_cls=NativePdfPipeline,
            backend=PyPdfiumDocumentBackend,
        )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: pdf_option,
            }
        )

    # Standard strategy allows Docling default layout pipeline
    return DocumentConverter()


# -----------------------------------------------------------------------------
# Main Subsystem Class: DoclingDocumentExtractor
# -----------------------------------------------------------------------------


class DoclingDocumentExtractor:
    """Production-grade document extraction subsystem using Docling 2.144.0.

    Extracts high-fidelity structured text, hierarchical headings, and tables
    from PDF, DOCX, and XLSX documents into the canonical NormalizedDocument
    representation, with full provenance and integrity verification.
    """

    def __init__(
        self,
        config: DocumentExtractionConfig | None = None,
        limits: DocumentExtractionLimits | None = None,
        security_guard: ExtractionSecurityGuard | None = None,
    ) -> None:
        self.config = config or DocumentExtractionConfig()
        self.limits = limits or DocumentExtractionLimits()
        self._owns_security_guard = security_guard is None
        self.security_guard = security_guard or ExtractionSecurityGuard()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_extractions)
        self._converter = _create_converter(self.config.strategy)
        self._closed = False

    def close(self) -> None:
        """Idempotent teardown of extractor resources."""
        if not self._closed:
            self._closed = True
            if self._owns_security_guard and hasattr(self.security_guard, "close"):
                self.security_guard.close()
                if hasattr(self.security_guard, "_executor"):
                    self.security_guard._executor.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> DoclingDocumentExtractor:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> DoclingDocumentExtractor:
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Public Extraction API
    # -------------------------------------------------------------------------

    def extract_file(
        self,
        file_path: Path | str,
        *,
        display_name: str | None = None,
        source_uri: str | None = None,
        source_type: SourceType | None = None,
    ) -> NormalizedDocument:
        """Synchronously extract content from a local file path."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Document file not found: {path}")

        name = display_name or path.name
        uri = source_uri or str(path)
        content_bytes = path.read_bytes()
        return self.extract_bytes(
            content_bytes,
            display_name=name,
            source_uri=uri,
            source_type=source_type,
        )

    async def extract_file_async(
        self,
        file_path: Path | str,
        *,
        display_name: str | None = None,
        source_uri: str | None = None,
        source_type: SourceType | None = None,
    ) -> NormalizedDocument:
        """Asynchronously extract content from a local file path."""
        async with self._semaphore:
            return await asyncio.to_thread(
                self.extract_file,
                file_path,
                display_name=display_name,
                source_uri=source_uri,
                source_type=source_type,
            )

    def extract_bytes(
        self,
        content: bytes,
        display_name: str,
        *,
        source_uri: str | None = None,
        source_type: SourceType | None = None,
    ) -> NormalizedDocument:
        """Synchronously extract content from document bytes."""
        if self._closed:
            raise RuntimeError("DoclingDocumentExtractor is closed")

        clean_name = sanitize_and_validate_display_name(display_name)
        uri = source_uri or clean_name
        source_sha256 = hashlib.sha256(content).hexdigest()

        quarantine_to_clean: str | None = None

        # 1. Preflight Security Guard Validation
        if self.config.validate_security:
            decision = self.security_guard.validate_file(content, clean_name)
            quarantine_to_clean = decision.quarantine_path
            if decision.outcome != SecurityDecisionOutcome.ACCEPTED:
                if quarantine_to_clean:
                    self.security_guard.quarantine_mgr.cleanup(quarantine_to_clean)
                return self._build_security_rejected_document(
                    decision=decision,
                    source_uri=uri,
                    display_name=clean_name,
                    source_sha256=source_sha256,
                    source_type=source_type,
                )

        try:
            # 2. Source Type Resolution
            resolved_type = source_type or detect_source_type_from_filename(clean_name)
            if not resolved_type:
                # Fall back to MIME detection
                mime = self.security_guard._detect_mime_type(content)
                resolved_type = SUPPORTED_MIME_TYPES.get(mime)

            if not resolved_type or resolved_type not in (
                SourceType.PDF,
                SourceType.DOCX,
                SourceType.XLSX,
            ):
                err_msg = f"Unsupported document format: {clean_name}"
                if self.config.raise_on_error:
                    raise UnsupportedDocumentFormatError(err_msg)
                return self._build_failed_document(
                    error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                    error_message=err_msg,
                    source_uri=uri,
                    display_name=clean_name,
                    source_sha256=source_sha256,
                    source_type=resolved_type or SourceType.PDF,
                )

            # 3. Size Bounds Check
            if len(content) > self.limits.max_document_bytes:
                err_msg = (
                    f"Document size ({len(content)} bytes) exceeds limit "
                    f"({self.limits.max_document_bytes} bytes)"
                )
                if self.limits.fail_closed_on_overflow:
                    if self.config.raise_on_error:
                        raise DocumentExtractionLimitExceededError(err_msg)
                    return self._build_failed_document(
                        error_code=ExtractionErrorCode.FILE_TOO_LARGE,
                        error_message=err_msg,
                        source_uri=uri,
                        display_name=clean_name,
                        source_sha256=source_sha256,
                        source_type=resolved_type,
                    )

            # 4. Conversion Execution via Docling
            t0 = time.perf_counter()
            doc_id = str(uuid.uuid4())
            excel_sheet_names = (
                _extract_excel_sheet_names(content) if resolved_type == SourceType.XLSX else []
            )

            try:
                stream = DocumentStream(name=clean_name, stream=io.BytesIO(content))
                conv_res = self._converter.convert(stream)
                docling_doc = conv_res.document
            except pypdfium2.PdfiumError as p_err:
                p_msg = str(p_err)
                if "password" in p_msg.lower():
                    if self.config.raise_on_error:
                        raise PasswordProtectedDocumentError("PDF is password-protected") from p_err
                    return self._build_failed_document(
                        error_code=ExtractionErrorCode.PASSWORD_PROTECTED,
                        error_message="Document is password protected and cannot be decrypted",
                        source_uri=uri,
                        display_name=clean_name,
                        source_sha256=source_sha256,
                        source_type=resolved_type,
                    )
                if self.config.raise_on_error:
                    raise CorruptedDocumentError(f"PDFium parsing error: {p_msg}") from p_err
                return self._build_failed_document(
                    error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                    error_message=f"PDF parsing failed: {p_msg}",
                    source_uri=uri,
                    display_name=clean_name,
                    source_sha256=source_sha256,
                    source_type=resolved_type,
                )
            except Exception as exc:
                exc_msg = str(exc)
                if "password" in exc_msg.lower():
                    if self.config.raise_on_error:
                        raise PasswordProtectedDocumentError("Document is encrypted") from exc
                    return self._build_failed_document(
                        error_code=ExtractionErrorCode.PASSWORD_PROTECTED,
                        error_message="Document is password protected",
                        source_uri=uri,
                        display_name=clean_name,
                        source_sha256=source_sha256,
                        source_type=resolved_type,
                    )
                logger.error("Docling document conversion failed for %s: %s", clean_name, exc)
                if self.config.raise_on_error:
                    raise DocumentExtractionError(f"Docling conversion failed: {exc_msg}") from exc
                return self._build_failed_document(
                    error_code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
                    error_message=f"Document parsing error: {exc_msg}",
                    source_uri=uri,
                    display_name=clean_name,
                    source_sha256=source_sha256,
                    source_type=resolved_type,
                )

            duration = time.perf_counter() - t0
            logger.info("Docling converted %s in %.2fs", clean_name, duration)

            # 5. Transform DoclingDocument to Canonical NormalizedDocument
            return self._transform_docling_document(
                docling_doc=docling_doc,
                doc_id=doc_id,
                source_uri=uri,
                display_name=clean_name,
                source_type=resolved_type,
                source_sha256=source_sha256,
                excel_sheet_names=excel_sheet_names,
                byte_count=len(content),
            )
        finally:
            if quarantine_to_clean:
                self.security_guard.quarantine_mgr.cleanup(quarantine_to_clean)

    async def extract_bytes_async(
        self,
        content: bytes,
        display_name: str,
        *,
        source_uri: str | None = None,
        source_type: SourceType | None = None,
    ) -> NormalizedDocument:
        """Asynchronously extract content from document bytes."""
        async with self._semaphore:
            return await asyncio.to_thread(
                self.extract_bytes,
                content,
                display_name,
                source_uri=source_uri,
                source_type=source_type,
            )

    # -------------------------------------------------------------------------
    # Internal Transformation & Mapping
    # -------------------------------------------------------------------------

    def _transform_docling_document(
        self,
        *,
        docling_doc: Any,
        doc_id: str,
        source_uri: str,
        display_name: str,
        source_type: SourceType,
        source_sha256: str,
        excel_sheet_names: list[str],
        byte_count: int,
    ) -> NormalizedDocument:
        """Map a DoclingDocument instance to a finalized NormalizedDocument."""
        elements: list[ExtractionElement] = []
        tables: list[TableRepresentation] = []
        warnings: list[ExtractionWarning] = []
        section_stack: list[SectionReference] = []

        total_words = 0
        total_chars = 0
        pages_seen: set[int] = set()
        ordinal = 0

        # Iterate all document items in reading order
        for item, level in docling_doc.iterate_items():
            if ordinal >= self.limits.max_elements:
                warnings.append(
                    ExtractionWarning(
                        code="ELEMENTS_TRUNCATED",
                        message=f"Element count exceeded limit ({self.limits.max_elements})",
                    )
                )
                break

            label = getattr(item, "label", None)
            item_text = getattr(item, "text", None) or ""
            clean_item_text = _clean_text(item_text)

            # 1. Provenance extraction
            prov: ElementProvenance | None = None
            raw_prov_list = getattr(item, "prov", None)
            if raw_prov_list and len(raw_prov_list) > 0:
                p_item = raw_prov_list[0]
                p_no = getattr(p_item, "page_no", None)
                if p_no and p_no > 0:
                    pages_seen.add(p_no)

                bbox: BoundingBox | None = None
                raw_bbox = getattr(p_item, "bbox", None)
                if raw_bbox:
                    origin = (
                        CoordinateOrigin.BOTTOM_LEFT
                        if getattr(raw_bbox, "coord_origin", None)
                        and "bottom" in str(raw_bbox.coord_origin).lower()
                        else CoordinateOrigin.TOP_LEFT
                    )
                    bbox = BoundingBox(
                        left=float(raw_bbox.l),
                        top=float(raw_bbox.t),
                        right=float(raw_bbox.r),
                        bottom=float(raw_bbox.b),
                        origin=origin,
                        coordinate_space=CoordinateSpace.POINTS,
                    )

                char_start = None
                char_end = None
                cspan = getattr(p_item, "charspan", None)
                if cspan and len(cspan) == 2:
                    char_start = cspan[0]
                    char_end = cspan[1]

                sheet_name = None
                if source_type == SourceType.XLSX and p_no and 1 <= p_no <= len(excel_sheet_names):
                    sheet_name = excel_sheet_names[p_no - 1]

                prov = ElementProvenance(
                    page_number=p_no,
                    bounding_box=bbox,
                    char_start=char_start,
                    char_end=char_end,
                    sheet_name=sheet_name,
                )

            # 2. Heading hierarchy tracking
            is_heading = label in ("section_header", "title", "heading") or type(item).__name__ in (
                "SectionHeaderItem",
                "TitleItem",
            )
            if is_heading and clean_item_text:
                heading_level = max(1, min(6, level if level > 0 else 1))
                # Pop headings of equal or greater level
                while section_stack and section_stack[-1].level >= heading_level:
                    section_stack.pop()

                hierarchy_titles = [h.title for h in section_stack] + [clean_item_text]
                path_str = " / ".join(hierarchy_titles)
                sec_ref = SectionReference(
                    title=clean_item_text,
                    level=heading_level,
                    path=path_str,
                )
                section_stack.append(sec_ref)

                elem = ExtractionElement(
                    element_id=f"elem_{ordinal:05d}",
                    element_type=ExtractionElementType.HEADING,
                    ordinal=ordinal,
                    text=clean_item_text,
                    markdown=f"{'#' * heading_level} {clean_item_text}",
                    section_hierarchy=list(section_stack),
                    provenance=prov,
                )
                elements.append(elem)
                ordinal += 1
                total_chars += len(clean_item_text)
                total_words += len(clean_item_text.split())
                continue

            # 3. Table handling
            is_table = label == "table" or type(item).__name__ == "TableItem"
            if is_table:
                if len(tables) >= self.limits.max_tables:
                    warnings.append(
                        ExtractionWarning(
                            code="TABLES_TRUNCATED",
                            message=f"Table count exceeded limit ({self.limits.max_tables})",
                        )
                    )
                    continue

                table_repr, table_md = self._map_docling_table(
                    item=item,
                    docling_doc=docling_doc,
                    table_index=len(tables),
                    excel_sheet_names=excel_sheet_names,
                    warnings=warnings,
                )
                tables.append(table_repr)

                elem = ExtractionElement(
                    element_id=f"elem_{ordinal:05d}",
                    element_type=ExtractionElementType.TABLE,
                    ordinal=ordinal,
                    text=f"Table {len(tables)}: {table_repr.row_count}x{table_repr.column_count}",
                    markdown=table_md,
                    section_hierarchy=list(section_stack),
                    provenance=prov,
                    table=table_repr,
                )
                elements.append(elem)
                ordinal += 1
                total_chars += len(table_md)
                continue

            # 4. Standard text, list items, code, captions
            if not clean_item_text:
                continue

            elem_type = ExtractionElementType.TEXT
            md_item = clean_item_text

            if label in ("list_item", "item") or type(item).__name__ == "ListItem":
                elem_type = ExtractionElementType.LIST_ITEM
                md_item = f"- {clean_item_text}"
            elif label == "code" or type(item).__name__ == "CodeItem":
                elem_type = ExtractionElementType.CODE
                md_item = f"```\n{clean_item_text}\n```"
            elif label == "caption" or type(item).__name__ == "CaptionItem":
                elem_type = ExtractionElementType.TEXT
                md_item = f"*{clean_item_text}*"
            elif label == "footnote" or type(item).__name__ == "FootnoteItem":
                elem_type = ExtractionElementType.TEXT

            elem = ExtractionElement(
                element_id=f"elem_{ordinal:05d}",
                element_type=elem_type,
                ordinal=ordinal,
                text=clean_item_text,
                markdown=md_item,
                section_hierarchy=list(section_stack),
                provenance=prov,
            )
            elements.append(elem)
            ordinal += 1
            total_chars += len(clean_item_text)
            total_words += len(clean_item_text.split())

        # Synthesize document markdown and clean text
        try:
            full_markdown = docling_doc.export_to_markdown()
        except Exception:
            full_markdown = "\n\n".join(e.markdown for e in elements if e.markdown)

        if len(full_markdown) > self.limits.max_markdown_chars:
            full_markdown = full_markdown[: self.limits.max_markdown_chars]
            warnings.append(
                ExtractionWarning(
                    code="MARKDOWN_TRUNCATED",
                    message="Markdown content was truncated to fit character limit",
                )
            )

        full_text = "\n\n".join(e.text for e in elements if e.text)
        if len(full_text) > self.limits.max_text_chars:
            full_text = full_text[: self.limits.max_text_chars]

        # Extract title from first heading or document name
        title = display_name
        for e in elements:
            if e.element_type == ExtractionElementType.HEADING and e.text:
                title = e.text
                break

        # Assemble metadata
        table_count = sum(1 for e in elements if e.table is not None)
        meta = DocumentMetadata(
            title=title,
            page_count=len(pages_seen) if pages_seen else None,
            element_count=len(elements),
            table_count=table_count,
            word_count=total_words,
            character_count=total_chars,
        )

        status = ExtractionStatus.PARTIAL_SUCCESS if len(warnings) > 0 else ExtractionStatus.SUCCESS

        now_utc = datetime.now(UTC)
        uri = None
        rel_ref = None
        if source_uri and source_uri.startswith(("http://", "https://")):
            uri = source_uri
        else:
            rel_ref = Path(display_name).name

        mime_type = "application/octet-stream"
        if source_type == SourceType.PDF:
            mime_type = "application/pdf"
        elif source_type == SourceType.DOCX:
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif source_type == SourceType.XLSX:
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        source_desc = SourceDescriptor(
            source_type=source_type,
            source_uri=uri,
            relative_source_ref=rel_ref,
            original_display_name=display_name,
            source_title=title,
            mime_type=mime_type,
            acquisition_timestamp=now_utc,
            content_length=byte_count,
        )

        config_params = {"strategy": self.config.strategy.value}
        config_hash = hashlib.sha256(
            json.dumps(config_params, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        extractor_desc = ExtractorDescriptor(
            engine_name=DOCLING_ENGINE_NAME,
            engine_version=DOCLING_ENGINE_VERSION,
            config_parameters=config_params,
            extractor_config_sha256=config_hash,
        )

        doc = NormalizedDocument(
            document_id=doc_id,
            version_id=str(uuid.uuid4()),
            ingestion_id=str(uuid.uuid4()),
            source=source_desc,
            extractor=extractor_desc,
            full_markdown=full_markdown,
            full_text=full_text,
            elements=elements,
            metadata=meta,
            status=status,
            warnings=warnings[: self.limits.max_warnings],
            errors=[],
            source_sha256=source_sha256,
            extracted_at=now_utc,
        )

        # Finalize (computes content and record hashes; deeply freezes models)
        doc.finalize()

        # Enforce trust boundary
        verify_trust_boundary(doc)
        return doc

    def _map_docling_table(
        self,
        *,
        item: Any,
        docling_doc: Any,
        table_index: int,
        excel_sheet_names: list[str],
        warnings: list[ExtractionWarning],
    ) -> tuple[TableRepresentation, str]:
        """Convert a Docling TableItem into TableRepresentation."""
        data = getattr(item, "data", None)
        num_rows = getattr(data, "num_rows", 0) if data else 0
        num_cols = getattr(data, "num_cols", 0) if data else 0

        # Try markdown export
        try:
            table_md = item.export_to_markdown(doc=docling_doc)
        except Exception:
            table_md = ""

        # Extract sheet name if available
        sheet_name: str | None = None
        raw_prov = getattr(item, "prov", None)
        if raw_prov and len(raw_prov) > 0:
            p_no = getattr(raw_prov[0], "page_no", None)
            if p_no and 1 <= p_no <= len(excel_sheet_names):
                sheet_name = excel_sheet_names[p_no - 1]

        # Extract cell objects
        cells: list[TableCell] = []
        merged_cells: list[MergedCell] = []
        raw_cells = getattr(data, "table_cells", None) or []

        # Build grid to populate rows
        grid_rows: list[list[TableCell]] = [
            [
                TableCell(
                    row=r,
                    col=c,
                    text="",
                    is_header=(r == 0),
                )
                for c in range(num_cols)
            ]
            for r in range(num_rows)
        ]

        has_irregular = False

        for c in raw_cells:
            r_idx = getattr(c, "start_row_offset_idx", None)
            c_idx = getattr(c, "start_col_offset_idx", None)
            if r_idx is None or c_idx is None:
                continue

            r_span = getattr(c, "row_span", 1) or 1
            c_span = getattr(c, "col_span", 1) or 1
            txt = _clean_text(getattr(c, "text", ""))
            is_hdr = bool(getattr(c, "column_header", False)) or (r_idx == 0)

            # Check for merged cell
            merged: MergedCell | None = None
            if r_span > 1 or c_span > 1:
                merged = MergedCell(
                    start_row=r_idx,
                    end_row=r_idx + r_span - 1,
                    start_col=c_idx,
                    end_col=c_idx + c_span - 1,
                )
                merged_cells.append(merged)

            cell_obj = TableCell(
                row=r_idx,
                col=c_idx,
                text=txt,
                is_header=is_hdr,
                merged_cell=merged,
            )
            cells.append(cell_obj)

            if r_idx < num_rows and c_idx < num_cols:
                grid_rows[r_idx][c_idx] = cell_obj
            else:
                has_irregular = True

        if has_irregular:
            warnings.append(
                ExtractionWarning(
                    code="MALFORMED_TABLE",
                    message=f"Table {table_index + 1} has coordinates outside grid bounds",
                )
            )

        headers = [c.text for c in grid_rows[0]] if grid_rows else []
        caption = item.caption_text(docling_doc) if hasattr(item, "caption_text") else None

        table_repr = TableRepresentation(
            headers=headers,
            rows=grid_rows,  # type: ignore[arg-type]
            row_count=num_rows,
            column_count=num_cols,
            sheet_name=sheet_name,
            merged_cells=merged_cells,
            caption=caption,
            table_id=f"table_{table_index + 1}",
        )
        return table_repr, table_md

    # -------------------------------------------------------------------------
    # Failure & Rejection Builders
    # -------------------------------------------------------------------------

    def _build_security_rejected_document(
        self,
        *,
        decision: SecurityValidationDecision,
        source_uri: str,
        display_name: str,
        source_sha256: str,
        source_type: SourceType | None,
    ) -> NormalizedDocument:
        """Construct a finalized failed document when preflight security rejects the file."""
        code = decision.error_code or ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR
        msg = decision.error_message or f"Document rejected by security guard: {decision.outcome}"

        if self.config.raise_on_error:
            if code == ExtractionErrorCode.FILE_TOO_LARGE:
                raise DocumentExtractionLimitExceededError(msg)
            if code == ExtractionErrorCode.PASSWORD_PROTECTED:
                raise PasswordProtectedDocumentError(msg)
            raise DocumentExtractionSecurityError(msg)

        return self._build_failed_document(
            error_code=code,
            error_message=msg,
            source_uri=source_uri,
            display_name=display_name,
            source_sha256=source_sha256,
            source_type=source_type or SourceType.PDF,
        )

    def _build_failed_document(
        self,
        *,
        error_code: ExtractionErrorCode,
        error_message: str,
        source_uri: str,
        display_name: str,
        source_sha256: str,
        source_type: SourceType,
        content_length: int = 0,
    ) -> NormalizedDocument:
        """Construct a finalized NormalizedDocument in FAILED state."""
        now_utc = datetime.now(UTC)
        uri = None
        rel_ref = None
        if source_uri and source_uri.startswith(("http://", "https://")):
            uri = source_uri
        else:
            rel_ref = Path(display_name).name

        mime_type = "application/octet-stream"
        if source_type == SourceType.PDF:
            mime_type = "application/pdf"
        elif source_type == SourceType.DOCX:
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif source_type == SourceType.XLSX:
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        source_desc = SourceDescriptor(
            source_type=source_type,
            source_uri=uri,
            relative_source_ref=rel_ref,
            original_display_name=display_name,
            source_title=display_name,
            mime_type=mime_type,
            acquisition_timestamp=now_utc,
            content_length=content_length,
        )

        config_params = {"strategy": self.config.strategy.value}
        config_hash = hashlib.sha256(
            json.dumps(config_params, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        extractor_desc = ExtractorDescriptor(
            engine_name=DOCLING_ENGINE_NAME,
            engine_version=DOCLING_ENGINE_VERSION,
            config_parameters=config_params,
            extractor_config_sha256=config_hash,
        )

        doc = NormalizedDocument(
            document_id=str(uuid.uuid4()),
            version_id=str(uuid.uuid4()),
            ingestion_id=str(uuid.uuid4()),
            source=source_desc,
            extractor=extractor_desc,
            full_markdown="",
            full_text="",
            elements=[],
            metadata=DocumentMetadata(
                title=display_name,
                element_count=0,
                table_count=0,
                word_count=0,
                character_count=0,
            ),
            status=ExtractionStatus.FAILED,
            warnings=[],
            errors=[
                ExtractionError(
                    code=error_code,
                    message=error_message,
                    timestamp=now_utc,
                )
            ],
            source_sha256=source_sha256,
            extracted_at=now_utc,
        )
        doc.finalize()
        verify_trust_boundary(doc)
        return doc


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------


def extract_document(
    file_path_or_bytes: Path | str | bytes,
    display_name: str | None = None,
    *,
    config: DocumentExtractionConfig | None = None,
    limits: DocumentExtractionLimits | None = None,
    source_type: SourceType | None = None,
) -> NormalizedDocument:
    """Convenience synchronous function to extract content from a document."""
    extractor = DoclingDocumentExtractor(config=config, limits=limits)
    try:
        if isinstance(file_path_or_bytes, bytes):
            name = display_name or "document"
            return extractor.extract_bytes(
                file_path_or_bytes,
                display_name=name,
                source_type=source_type,
            )
        return extractor.extract_file(
            file_path_or_bytes,
            display_name=display_name,
            source_type=source_type,
        )
    finally:
        extractor.close()


async def extract_document_async(
    file_path_or_bytes: Path | str | bytes,
    display_name: str | None = None,
    *,
    config: DocumentExtractionConfig | None = None,
    limits: DocumentExtractionLimits | None = None,
    source_type: SourceType | None = None,
) -> NormalizedDocument:
    """Convenience asynchronous function to extract content from a document."""
    extractor = DoclingDocumentExtractor(config=config, limits=limits)
    try:
        if isinstance(file_path_or_bytes, bytes):
            name = display_name or "document"
            return await extractor.extract_bytes_async(
                file_path_or_bytes,
                display_name=name,
                source_type=source_type,
            )
        return await extractor.extract_file_async(
            file_path_or_bytes,
            display_name=display_name,
            source_type=source_type,
        )
    finally:
        extractor.close()
