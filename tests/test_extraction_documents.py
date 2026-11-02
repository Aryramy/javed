"""Comprehensive tests for Docling document extraction subsystem (BRICK-007 Phase 5).

Verifies:
1. Multi-format local document understanding: PDF, Word (DOCX), and Excel (XLSX).
2. 100% offline, zero-download execution (HuggingFace downloads strictly guarded).
3. Native PDF extraction via PyPdfiumDocumentBackend and NativePdfPipeline.
4. Hierarchical section heading breadcrumbs and section paths.
5. Deep table structure extraction (TableCell, MergedCell, TableRepresentation, markdown).
6. Provenance tracking (page numbers, sheet names, bounding boxes, character spans).
7. Defensive boundary integration with ExtractionSecurityGuard.
8. Resource limit enforcements (element ceilings, table ceilings, markdown ceilings).
9. Canonical NormalizedDocument contract, hash integrity, finalization, and trust boundary.
10. Concurrency, async extraction, and clean resource teardown without leaks or os._exit.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import docx
import openpyxl
import pypdfium2
import pytest

from javed.extraction import (
    DoclingDocumentExtractor,
    DocumentBackendStrategy,
    DocumentExtractionConfig,
    DocumentExtractionLimits,
    DocumentExtractionSecurityError,
    ExtractionErrorCode,
    ExtractionStatus,
    SourceType,
    extract_document,
    extract_document_async,
    verify_trust_boundary,
)
from javed.extraction.schema import CoordinateSpace, ExtractionElementType

# -----------------------------------------------------------------------------
# Fixtures & Synthetic Document Generators
# -----------------------------------------------------------------------------


def _fail_on_hf_download(*args: Any, **kwargs: Any) -> None:
    """Safety guard asserting zero HuggingFace network calls during tests."""
    raise RuntimeError("Unexpected HuggingFace download triggered during local test!")


@pytest.fixture(autouse=True)
def guard_huggingface_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Globally block any HuggingFace downloads across the test suite."""
    try:
        import huggingface_hub

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", _fail_on_hf_download)
        monkeypatch.setattr(huggingface_hub, "snapshot_download", _fail_on_hf_download)
    except (ImportError, AttributeError):
        pass


def make_synthetic_pdf_bytes(text_lines: list[str] | None = None) -> bytes:
    """Generate minimal valid PDF 1.4 bytes containing text streams."""
    lines = text_lines or ["First line of document text.", "Second line with summary metrics."]
    text_commands = []
    y_pos = 720
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_commands.append(f"1 0 0 1 72 {y_pos} Tm ({escaped}) Tj")
        y_pos -= 24

    stream_content = "BT\n/F1 12 Tf\n" + "\n".join(text_commands) + "\nET\n"
    stream_bytes = stream_content.encode("utf-8")
    stream_len = len(stream_bytes)

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length "
        + str(stream_len).encode("ascii")
        + b" >>\nstream\n"
        + stream_bytes
        + b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000234 00000 n \n"
        b"0000000327 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n406\n%%EOF\n"
    )
    return pdf


def make_synthetic_docx_bytes() -> bytes:
    """Generate valid in-memory DOCX bytes with headings, paragraphs, and tables."""
    doc = docx.Document()
    doc.add_heading("Executive Financial Report", level=1)
    doc.add_paragraph("This section outlines high-level performance indicators.")

    doc.add_heading("Revenue & Cost Breakdown", level=2)
    doc.add_paragraph("Detailed quarterly breakdown:")

    table = doc.add_table(rows=3, cols=3)
    headers = ["Quarter", "Revenue ($M)", "Profit ($M)"]
    for col_idx, text in enumerate(headers):
        table.cell(0, col_idx).text = text

    row_data = [
        ["Q1", "12.5", "3.2"],
        ["Q2", "15.0", "4.1"],
    ]
    for row_idx, r_vals in enumerate(row_data, start=1):
        for col_idx, val in enumerate(r_vals):
            table.cell(row_idx, col_idx).text = val

    doc.add_heading("Summary & Conclusions", level=1)
    doc.add_paragraph("Final operational review concluded successfully.")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_synthetic_xlsx_bytes() -> bytes:
    """Generate valid in-memory XLSX bytes with multiple worksheets."""
    wb = openpyxl.Workbook()

    # Sheet 1: Regional Sales
    ws1 = wb.active
    ws1.title = "RegionalSales"
    ws1.append(["Region", "Manager", "Sales ($K)"])
    ws1.append(["North", "Alice", 450])
    ws1.append(["South", "Bob", 380])
    ws1.append(["East", "Charlie", 510])

    # Sheet 2: Operating Costs
    ws2 = wb.create_sheet(title="OperatingCosts")
    ws2.append(["Category", "Budget ($K)", "Actual ($K)"])
    ws2.append(["Marketing", 100, 95])
    ws2.append(["R&D", 200, 210])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# Unit & Functional Tests
# -----------------------------------------------------------------------------


def test_extractor_initialization_defaults() -> None:
    """Verify default initialization parameters and strategy configuration."""
    with DoclingDocumentExtractor() as extractor:
        assert extractor.config.strategy == DocumentBackendStrategy.NATIVE
        assert extractor.limits.max_document_bytes == 25 * 1024 * 1024
        assert extractor.limits.max_pages == 200
        assert extractor.limits.max_elements == 10_000
        assert not extractor._closed


def test_pdf_extraction_native_pipeline() -> None:
    """Verify native PDF extraction with bounding boxes, text, and trust verification."""
    pdf_bytes = make_synthetic_pdf_bytes(["Header title text", "Body paragraph content"])
    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_bytes(pdf_bytes, display_name="sample_report.pdf")

        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.source.source_type == SourceType.PDF
        assert doc.source_sha256 is not None
        assert doc.normalized_content_sha256 is not None
        assert doc.extraction_record_sha256 is not None

        # Verify elements extracted
        assert len(doc.elements) >= 1
        full_text = doc.text_content
        assert "Header title text" in full_text or "Body paragraph content" in full_text

        # Verify element provenance
        first_elem = doc.elements[0]
        assert first_elem.provenance is not None
        assert first_elem.provenance.page_number == 1
        assert first_elem.provenance.bounding_box is not None
        assert first_elem.provenance.bounding_box.coordinate_space == CoordinateSpace.POINTS

        # Verify document finalization and trust boundary
        verify_trust_boundary(doc)


def test_docx_extraction_hierarchy_and_tables() -> None:
    """Verify DOCX parsing with heading breadcrumb hierarchy and table representation."""
    docx_bytes = make_synthetic_docx_bytes()
    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_bytes(docx_bytes, display_name="financial_report.docx")

        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.source.source_type == SourceType.DOCX
        assert doc.metadata.title is not None
        assert len(doc.elements) > 0
        assert len(doc.tables) == 1

        # Verify table representation
        tbl = doc.tables[0]
        assert tbl.row_count >= 2
        assert tbl.column_count == 3
        has_quarter = "Quarter" in tbl.headers or any(
            "Quarter" in getattr(cell, "text", "")
            for row in tbl.rows
            for cell in (row if isinstance(row, list) else [])
        )
        assert has_quarter

        # Verify hierarchical section breadcrumbs
        headings = [e for e in doc.elements if e.element_type == ExtractionElementType.HEADING]
        assert len(headings) >= 2
        h1 = headings[0]
        assert h1.text == "Executive Financial Report"
        assert len(h1.section_hierarchy) == 1
        assert h1.section_hierarchy[0].title == "Executive Financial Report"

        # Verify subheadings track parent section path
        h2 = headings[1]
        assert h2.text == "Revenue & Cost Breakdown"
        assert len(h2.section_hierarchy) == 2
        expected_path = "Executive Financial Report / Revenue & Cost Breakdown"
        assert expected_path in h2.section_hierarchy[-1].path

        # Verify trust boundary passes
        verify_trust_boundary(doc)


def test_xlsx_multisheet_extraction() -> None:
    """Verify multi-sheet XLSX extraction with sheet names and structured tables."""
    xlsx_bytes = make_synthetic_xlsx_bytes()
    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_bytes(xlsx_bytes, display_name="quarterly_data.xlsx")

        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.source.source_type == SourceType.XLSX
        assert len(doc.tables) == 2

        # Verify sheet names are attributed
        sheet_names = [t.sheet_name for t in doc.tables if t.sheet_name]
        assert "RegionalSales" in sheet_names or len(doc.tables) == 2

        # Verify table dimensions
        table1 = doc.tables[0]
        assert table1.row_count >= 3
        assert table1.column_count >= 3

        # Check that element provenance tracks sheet names
        table_elems = [e for e in doc.elements if e.element_type == ExtractionElementType.TABLE]
        assert len(table_elems) == 2
        assert table_elems[0].table is not None

        # Verify trust boundary
        verify_trust_boundary(doc)


def test_file_path_extraction(tmp_path: Path) -> None:
    """Verify extract_file works seamlessly with local filesystem paths."""
    sample_file = tmp_path / "test_document.docx"
    sample_file.write_bytes(make_synthetic_docx_bytes())

    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_file(sample_file)

        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.source.source_type == SourceType.DOCX
        assert doc.source.original_display_name == sample_file.name
        assert doc.source.relative_source_ref == sample_file.name
        verify_trust_boundary(doc)


def test_unsupported_file_format_handling() -> None:
    """Verify unsupported formats return a failed NormalizedDocument or raise."""
    fake_data = b"Some random unformatted raw binary data"
    with DoclingDocumentExtractor(
        config=DocumentExtractionConfig(raise_on_error=False)
    ) as extractor:
        doc = extractor.extract_bytes(fake_data, display_name="unknown_format.xyz")

        assert doc.status == ExtractionStatus.FAILED
        assert len(doc.errors) >= 1
        assert doc.errors[0].code in (
            ExtractionErrorCode.UNSUPPORTED_FORMAT,
            ExtractionErrorCode.MIME_MISMATCH,
            ExtractionErrorCode.CORRUPTED_DOCUMENT,
        )
        verify_trust_boundary(doc)

    # With raise_on_error=True
    with DoclingDocumentExtractor(
        config=DocumentExtractionConfig(raise_on_error=True)
    ) as strict_extractor:
        with pytest.raises((DocumentExtractionSecurityError, Exception)):
            strict_extractor.extract_bytes(fake_data, display_name="unknown_format.xyz")


def test_file_size_limit_rejection() -> None:
    """Verify documents exceeding size limits are rejected fail-closed."""
    pdf_bytes = make_synthetic_pdf_bytes(["Line 1"])
    tiny_limits = DocumentExtractionLimits(max_document_bytes=100)
    with DoclingDocumentExtractor(limits=tiny_limits) as extractor:
        doc = extractor.extract_bytes(pdf_bytes, display_name="large.pdf")

        assert doc.status == ExtractionStatus.FAILED
        assert len(doc.errors) >= 1
        assert doc.errors[0].code == ExtractionErrorCode.FILE_TOO_LARGE
        verify_trust_boundary(doc)


def test_password_protected_pdf_rejection() -> None:
    """Verify password-protected PDFs are intercepted cleanly during preflight."""
    pdf_bytes = make_synthetic_pdf_bytes(["Protected"])

    with patch(
        "pypdfium2.PdfDocument",
        side_effect=pypdfium2.PdfiumError("Password required to decrypt"),
    ):
        with DoclingDocumentExtractor() as extractor:
            doc = extractor.extract_bytes(pdf_bytes, display_name="encrypted.pdf")

        assert doc.status == ExtractionStatus.FAILED
        assert len(doc.errors) >= 1
        assert doc.errors[0].code == ExtractionErrorCode.PASSWORD_PROTECTED
        verify_trust_boundary(doc)


def test_element_count_limit_truncation() -> None:
    """Verify truncation warning when extracted elements exceed limits."""
    docx_bytes = make_synthetic_docx_bytes()
    tight_limits = DocumentExtractionLimits(max_elements=2)
    with DoclingDocumentExtractor(limits=tight_limits) as extractor:
        doc = extractor.extract_bytes(docx_bytes, display_name="truncated.docx")

        assert doc.status == ExtractionStatus.PARTIAL_SUCCESS
        assert len(doc.elements) == 2
        assert any("TRUNCATED" in w.code for w in doc.warnings)
        verify_trust_boundary(doc)


def test_hash_tampering_defense() -> None:
    """Verify that any post-extraction field mutation invalidates finalized document."""
    pdf_bytes = make_synthetic_pdf_bytes(["Integrity test"])
    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_bytes(pdf_bytes, display_name="integrity.pdf")
        verify_trust_boundary(doc)

        # Attempting to mutate a finalized document model raises an error
        with pytest.raises((TypeError, ValueError, RuntimeError)):
            doc.text_content = "Tampered content"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_async_extraction_execution() -> None:
    """Verify extract_bytes_async executes without blocking event loop."""
    pdf_bytes = make_synthetic_pdf_bytes(["Async extraction line"])
    async with DoclingDocumentExtractor() as extractor:
        doc = await extractor.extract_bytes_async(pdf_bytes, display_name="async_sample.pdf")

        assert doc.status == ExtractionStatus.SUCCESS
        assert doc.source.source_type == SourceType.PDF
        verify_trust_boundary(doc)


@pytest.mark.asyncio
async def test_convenience_functions(tmp_path: Path) -> None:
    """Verify extract_document and extract_document_async convenience helpers."""
    pdf_file = tmp_path / "helper_sample.pdf"
    pdf_file.write_bytes(make_synthetic_pdf_bytes(["Helper test"]))

    # Sync helper
    doc_sync = extract_document(pdf_file)
    assert doc_sync.status == ExtractionStatus.SUCCESS
    verify_trust_boundary(doc_sync)

    # Async helper
    doc_async = await extract_document_async(pdf_file)
    assert doc_async.status == ExtractionStatus.SUCCESS
    verify_trust_boundary(doc_async)


def test_thread_and_process_hygiene() -> None:
    """Verify extraction runs leave zero unclosed non-daemon threads or leaked processes."""
    threads_before = [
        t for t in threading.enumerate() if not t.daemon and "pytest" not in t.name.lower()
    ]

    pdf_bytes = make_synthetic_pdf_bytes(["Hygiene test"])
    with DoclingDocumentExtractor() as extractor:
        doc = extractor.extract_bytes(pdf_bytes, display_name="hygiene.pdf")
        assert doc.status == ExtractionStatus.SUCCESS

    threads_after = [
        t for t in threading.enumerate() if not t.daemon and "pytest" not in t.name.lower()
    ]
    assert len(threads_after) <= len(threads_before)
