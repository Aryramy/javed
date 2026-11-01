"""Deterministic unit tests for ExtractionSecurityGuard and QuarantineManager.

Verifies zero-trust defensive ingestion boundary conforming to BRICK-007 Phase 3:
1. File size enforcement and governance maximum ceiling.
2. Magic signature, MIME, and extension whitelist validation.
3. UUID quarantine staging, path containment, atomic exclusive creation, cleanup.
4. Office ZIP container inspection (entries, compression ratios, expanded size, traversal).
5. PyPDFium2 lightweight PDF preflight (pages, corruption, password, active content).
6. Local HTML active script classification and binary null byte rejection.
7. Plain text, markdown, and CSV validation.
8. Filename sanitization (device names, traversal, UNC, NTFS ADS, trailing spaces/dots).
9. Confidentiality verification of safe_log_dict() (no contents, no paths).
10. Concurrency semaphore timeout.
"""

from __future__ import annotations

import io
import re
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

import pypdfium2
import pytest

from javed.extraction.schema import (
    ExtractionErrorCode,
    SourceType,
)
from javed.extraction.security import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    MAX_GOVERNANCE_FILE_SIZE_BYTES,
    ExtractionSecurityGuard,
    QuarantineManager,
    SecurityDecisionOutcome,
    SecurityGuardConfig,
    SecurityValidationDecision,
    sanitize_and_validate_display_name,
)

# -----------------------------------------------------------------------------
# Test Fixtures & Synthetic Builders
# -----------------------------------------------------------------------------


def make_minimal_pdf(pages: int = 1, active_marker: bytes | None = None) -> bytes:
    """Generate a minimal valid synthetic PDF with the requested page count."""
    doc = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(100, 100)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    data = buf.getvalue()
    if active_marker:
        data += active_marker
    return data


def make_office_zip(
    subsystem: str,  # "word", "xl", or "ppt"
    entries: dict[str, bytes] | None = None,
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    """Generate a synthetic OpenXML Office container."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        if subsystem == "word":
            zf.writestr("word/document.xml", b"<w:document/>")
        elif subsystem == "xl":
            zf.writestr("xl/workbook.xml", b"<workbook/>")
        elif subsystem == "ppt":
            zf.writestr("ppt/presentation.xml", b"<presentation/>")
        if entries:
            for name, content in entries.items():
                zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def temp_quarantine(tmp_path: Path) -> Path:
    q_dir = tmp_path / "quarantine"
    q_dir.mkdir(parents=True, exist_ok=True)
    return q_dir


@pytest.fixture
def guard(temp_quarantine: Path) -> ExtractionSecurityGuard:
    config = SecurityGuardConfig(quarantine_root=str(temp_quarantine))
    return ExtractionSecurityGuard(config)


# -----------------------------------------------------------------------------
# Configuration & Governance Limit Tests
# -----------------------------------------------------------------------------


def test_security_guard_config_defaults_and_governance():
    """Verify default configurations and strict 50 MB governance maximum ceiling."""
    cfg = SecurityGuardConfig()
    assert cfg.max_file_size_bytes == DEFAULT_MAX_FILE_SIZE_BYTES
    assert cfg.max_pdf_pages == 200
    assert cfg.max_office_entries == 1000
    assert cfg.max_office_compression_ratio == 100.0

    # Configs exceeding 50 MB governance ceiling must be rejected
    with pytest.raises(ValueError, match="governance ceiling"):
        SecurityGuardConfig(max_file_size_bytes=MAX_GOVERNANCE_FILE_SIZE_BYTES + 1)

    # Configs with non-positive values must be rejected
    with pytest.raises(ValueError, match="strictly positive"):
        SecurityGuardConfig(max_file_size_bytes=0)

    with pytest.raises(ValueError, match="strictly positive"):
        SecurityGuardConfig(max_pdf_pages=0)

    with pytest.raises(ValueError, match="at least 1.0"):
        SecurityGuardConfig(max_office_compression_ratio=0.5)


# -----------------------------------------------------------------------------
# Filename & Path Sanitization Tests
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_name",
    [
        "annual_report.pdf",
        "financials_2026.xlsx",
        "presentation.pptx",
        "memo.docx",
        "notes.txt",
        "README.md",
        "dataset.csv",
        "index.html",
    ],
)
def test_sanitize_display_name_valid(valid_name: str):
    """Verify clean, valid filenames pass sanitization unmodified."""
    assert sanitize_and_validate_display_name(valid_name) == valid_name


@pytest.mark.parametrize(
    ("bad_name", "error_match"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("file\x00.pdf", "control characters"),
        ("file\x1f.pdf", "control characters"),
        ("file\x7f.pdf", "control characters"),
        ("dir/file.pdf", "path separator"),
        ("dir\\file.pdf", "path separator"),
        ("..", "Path traversal segments"),
        ("dir/../file.pdf", "path separator"),
        ("file..pdf", "Path traversal segments"),
        ("\\\\server\\share\\file.pdf", "path separator"),
        ("//server/share/file.pdf", "path separator"),
        ("C:file.pdf", "Drive letter"),
        ("D:file.docx", "Drive letter"),
        ("file.pdf:stream", "NTFS Alternate Data Stream"),
        ("file.pdf.", "Trailing dots and spaces"),
        ("file.pdf ", "Trailing dots and spaces"),
        ("con", "Reserved Windows device name"),
        ("CON.pdf", "Reserved Windows device name"),
        ("prn.txt", "Reserved Windows device name"),
        ("aux.docx", "Reserved Windows device name"),
        ("nul.xlsx", "Reserved Windows device name"),
        ("com1.pdf", "Reserved Windows device name"),
        ("com9.csv", "Reserved Windows device name"),
        ("lpt1.txt", "Reserved Windows device name"),
        ("lpt9.html", "Reserved Windows device name"),
        ("a" * 256 + ".pdf", "exceeds 255 characters"),
    ],
)
def test_sanitize_display_name_rejections(bad_name: str, error_match: str):
    """Verify malicious, ambiguous, and illegal filenames are rejected fail-closed."""
    with pytest.raises(ValueError, match=error_match):
        sanitize_and_validate_display_name(bad_name)


# -----------------------------------------------------------------------------
# Quarantine Manager Tests
# -----------------------------------------------------------------------------


def test_quarantine_manager_uuid_and_containment(temp_quarantine: Path):
    """Verify quarantine files use UUID names, contain within root, and cleanup."""
    mgr = QuarantineManager(temp_quarantine)
    data = b"synthetic quarantine test payload"

    target, count, sha256_hex = mgr.stage_bytes(data, ".pdf", max_bytes=1024)
    assert target.is_relative_to(temp_quarantine)
    assert target.is_file()
    assert count == len(data)
    # Target filename must be UUID format, never the original name
    stem = target.stem
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", stem)

    # Cleanup must delete the file
    mgr.cleanup(target)
    assert not target.exists()


def test_quarantine_manager_empty_and_oversize(temp_quarantine: Path):
    """Verify 0 bytes and oversize inputs are immediately rejected and cleaned up."""
    mgr = QuarantineManager(temp_quarantine)

    with pytest.raises(ValueError, match="empty"):
        mgr.stage_bytes(b"", ".pdf", max_bytes=1024)

    with pytest.raises(ValueError, match="exceeds maximum limit"):
        mgr.stage_bytes(b"x" * 200, ".pdf", max_bytes=100)

    # Verify no stray files remained in quarantine directory
    assert list(temp_quarantine.iterdir()) == []


# -----------------------------------------------------------------------------
# PDF Preflight Tests
# -----------------------------------------------------------------------------


def test_pdf_preflight_accepted(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify valid synthetic PDF is accepted with verified metadata."""
    pdf_bytes = make_minimal_pdf(pages=2)
    decision = guard.validate_file(pdf_bytes, "valid_report.pdf")

    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.PDF
    assert decision.verified_mime_type == "application/pdf"
    assert decision.byte_count == len(pdf_bytes)
    assert decision.page_count == 2
    assert decision.error_code is None
    assert decision.quarantine_path is not None
    assert Path(decision.quarantine_path).is_file()

    # Clean up quarantined file
    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_pdf_preflight_active_content_warnings(guard: ExtractionSecurityGuard):
    """Verify PDF with active script indicators produces warnings but accepts."""
    pdf_bytes = make_minimal_pdf(pages=1, active_marker=b"/JavaScript << /JS (app.alert(1);) >>")
    decision = guard.validate_file(pdf_bytes, "report_with_js.pdf")

    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.PDF
    assert len(decision.warnings) >= 1
    assert any("JavaScript" in w for w in decision.warnings)

    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_pdf_preflight_corrupted(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify malformed PDF signature or structure is rejected with CORRUPTED_DOCUMENT."""
    corrupted_data = b"%PDF-1.4\ncorrupted non-pdf binary content garbage"
    decision = guard.validate_file(corrupted_data, "bad.pdf")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.CORRUPTED_DOCUMENT
    assert "malformed or corrupted" in decision.error_message
    # Quarantine file must be removed after rejection
    assert list(temp_quarantine.iterdir()) == []


def test_pdf_preflight_password_protected(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify password protected PDF triggers PASSWORD_PROTECTED error."""
    pdf_bytes = make_minimal_pdf(pages=1)

    with patch(
        "pypdfium2.PdfDocument", side_effect=pypdfium2.PdfiumError("Password required to decrypt")
    ):
        decision = guard.validate_file(pdf_bytes, "encrypted.pdf")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.PASSWORD_PROTECTED
    assert list(temp_quarantine.iterdir()) == []


def test_pdf_preflight_page_limit_exceeded(temp_quarantine: Path):
    """Verify PDF exceeding maximum page count is rejected with PAGE_LIMIT_EXCEEDED."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_pdf_pages=3,
    )
    custom_guard = ExtractionSecurityGuard(config)
    pdf_bytes = make_minimal_pdf(pages=4)

    decision = custom_guard.validate_file(pdf_bytes, "too_long.pdf")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.PAGE_LIMIT_EXCEEDED
    assert decision.page_count == 4
    assert list(temp_quarantine.iterdir()) == []


def test_pdf_preflight_extension_and_mime_mismatch(guard: ExtractionSecurityGuard):
    """Verify PDF signature with non-PDF extension or mismatched MIME is rejected."""
    pdf_bytes = make_minimal_pdf(pages=1)

    # Extension mismatch: PDF content in .docx filename
    dec1 = guard.validate_file(pdf_bytes, "disguised.docx")
    assert dec1.outcome == SecurityDecisionOutcome.REJECTED
    assert dec1.error_code == ExtractionErrorCode.MIME_MISMATCH

    # Declared MIME mismatch: PDF content declared as text/plain
    dec2 = guard.validate_file(pdf_bytes, "mismatched.pdf", declared_mime="text/plain")
    assert dec2.outcome == SecurityDecisionOutcome.REJECTED
    assert dec2.error_code == ExtractionErrorCode.MIME_MISMATCH


# -----------------------------------------------------------------------------
# Office ZIP Container Tests
# -----------------------------------------------------------------------------


def test_docx_container_accepted(guard: ExtractionSecurityGuard):
    """Verify valid DOCX container is accepted."""
    docx_bytes = make_office_zip("word")
    decision = guard.validate_file(docx_bytes, "document.docx")

    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.DOCX
    assert (
        decision.verified_mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_xlsx_container_accepted(guard: ExtractionSecurityGuard):
    """Verify valid XLSX container is accepted."""
    xlsx_bytes = make_office_zip("xl")
    decision = guard.validate_file(xlsx_bytes, "sheet.xlsx")

    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.XLSX
    assert (
        decision.verified_mime_type
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_pptx_container_accepted(guard: ExtractionSecurityGuard):
    """Verify valid PPTX container is accepted."""
    pptx_bytes = make_office_zip("ppt")
    decision = guard.validate_file(pptx_bytes, "slides.pptx")

    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.PPTX
    assert (
        decision.verified_mime_type
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_office_zip_entry_count_limit(temp_quarantine: Path):
    """Verify Office container exceeding entry count limit is rejected."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_office_entries=5,
    )
    custom_guard = ExtractionSecurityGuard(config)
    extra_entries = {f"word/entry_{i}.xml": b"<xml/>" for i in range(6)}
    data = make_office_zip("word", entries=extra_entries)

    decision = custom_guard.validate_file(data, "too_many_entries.docx")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_single_entry_size_limit(temp_quarantine: Path):
    """Verify Office container with single entry exceeding limit is rejected."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_office_entry_uncompressed_bytes=500,
    )
    custom_guard = ExtractionSecurityGuard(config)
    extra_entries = {"word/big_entry.xml": b"A" * 600}
    data = make_office_zip("word", entries=extra_entries)

    decision = custom_guard.validate_file(data, "big_entry.docx")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_total_size_limit(temp_quarantine: Path):
    """Verify Office container with aggregate uncompressed size exceeding limit is rejected."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_office_total_uncompressed_bytes=1000,
    )
    custom_guard = ExtractionSecurityGuard(config)
    extra_entries = {
        "word/part1.xml": b"A" * 600,
        "word/part2.xml": b"B" * 600,
    }
    data = make_office_zip("word", entries=extra_entries)

    decision = custom_guard.validate_file(data, "total_too_big.docx")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_compression_ratio_limit(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container exceeding 100:1 compression ratio (zip bomb) is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/document.xml", b"<w:document/>")
        # 100,000 zeros compress to ~115 bytes (ratio ~870:1)
        zf.writestr("word/huge_zeros.xml", b"0" * 100000)
    data = buf.getvalue()

    decision = guard.validate_file(data, "zipbomb.docx")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "compression ratio" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_path_traversal_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container with traversal segment ('..') in entry name is rejected."""
    data = make_office_zip("word", entries={"../evil.xml": b"<evil/>"})
    decision = guard.validate_file(data, "traversal.docx")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "Path traversal" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_absolute_path_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container with absolute path in entry name is rejected."""
    data = make_office_zip("word", entries={"/absolute/evil.xml": b"<evil/>"})
    decision = guard.validate_file(data, "absolute.docx")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "Absolute path" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_ntfs_stream_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container with NTFS stream in member name is rejected."""
    data = make_office_zip("word", entries={"word/document.xml:hidden": b"<evil/>"})
    decision = guard.validate_file(data, "stream.docx")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "NTFS stream" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_reserved_device_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container with Windows reserved device name in member is rejected."""
    data = make_office_zip("word", entries={"word/CON.xml": b"<evil/>"})
    decision = guard.validate_file(data, "reserved.docx")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "Reserved device name" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_nested_executable_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify Office container with nested executable or archive member is rejected."""
    data = make_office_zip("word", entries={"word/payload.exe": b"MZ\x90\x00"})
    decision = guard.validate_file(data, "nested_exe.docx")

    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED
    assert "Nested archive or executable" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_encrypted_member(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify encrypted Office ZIP container entry triggers PASSWORD_PROTECTED."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/document.xml", b"<w:document/>")
        zf.writestr("word/secret.xml", b"encrypted")
    data = bytearray(buf.getvalue())
    # Set encryption flag (bit 0) in central directory record for secret.xml
    cd_pos = data.find(b"PK\x01\x02")
    while cd_pos != -1:
        if b"word/secret.xml" in data[cd_pos : cd_pos + 100]:
            data[cd_pos + 8] |= 0x1
            break
        cd_pos = data.find(b"PK\x01\x02", cd_pos + 1)

    decision = guard.validate_file(bytes(data), "encrypted.docx")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.PASSWORD_PROTECTED
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_generic_zip_without_content_types(
    guard: ExtractionSecurityGuard, temp_quarantine: Path
):
    """Verify generic standalone ZIP archives without OpenXML structure are prohibited."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"Generic zip archive content")
    data = buf.getvalue()

    decision = guard.validate_file(data, "generic.zip")
    assert decision.outcome == SecurityDecisionOutcome.REJECTED
    assert decision.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT
    assert "without OpenXML structure" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


def test_office_zip_extension_and_mime_mismatches(guard: ExtractionSecurityGuard):
    """Verify cross-format extension and declared MIME mismatches are rejected."""
    # Word content inside .xlsx file
    word_bytes = make_office_zip("word")
    dec1 = guard.validate_file(word_bytes, "mismatched.xlsx")
    assert dec1.outcome == SecurityDecisionOutcome.REJECTED
    assert dec1.error_code == ExtractionErrorCode.MIME_MISMATCH

    # Excel content declared as PDF
    xl_bytes = make_office_zip("xl")
    dec2 = guard.validate_file(xl_bytes, "sheet.xlsx", declared_mime="application/pdf")
    assert dec2.outcome == SecurityDecisionOutcome.REJECTED
    assert dec2.error_code == ExtractionErrorCode.MIME_MISMATCH


# -----------------------------------------------------------------------------
# Prohibited Formats & Executables Tests
# -----------------------------------------------------------------------------


def test_prohibited_executables_and_archives(guard: ExtractionSecurityGuard, temp_quarantine: Path):
    """Verify MZ executables, ELF binaries, 7z, RAR, and GZIP are rejected."""
    # MZ executable
    dec_mz = guard.validate_file(b"MZ\x90\x00\x03\x00\x00\x00", "payload.exe")
    assert dec_mz.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_mz.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT
    assert "Executable binaries" in dec_mz.error_message

    # ELF binary
    dec_elf = guard.validate_file(b"\x7fELF\x02\x01\x01\x00", "payload.bin")
    assert dec_elf.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_elf.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT

    # 7z archive
    dec_7z = guard.validate_file(b"7z\xbc\xaf\x27\x1c\x00\x00", "archive.7z")
    assert dec_7z.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_7z.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT
    assert "Standalone archive formats" in dec_7z.error_message

    # RAR archive
    dec_rar = guard.validate_file(b"Rar!\x1a\x07\x00\x00", "archive.rar")
    assert dec_rar.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_rar.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT

    # GZIP archive
    dec_gz = guard.validate_file(b"\x1f\x8b\x08\x00\x00\x00", "archive.tar.gz")
    assert dec_gz.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_gz.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT

    # Unsupported generic binary
    dec_bin = guard.validate_file(b"\xde\xad\xbe\xef\x01\x02\x03\x04", "unknown.bin")
    assert dec_bin.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_bin.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT

    assert list(temp_quarantine.iterdir()) == []


# -----------------------------------------------------------------------------
# HTML and Plain Text Preflight Tests
# -----------------------------------------------------------------------------


def test_html_preflight_clean_and_active(guard: ExtractionSecurityGuard):
    """Verify clean HTML accepted; script tags trigger warning; null bytes rejected."""
    clean_html = b"<!DOCTYPE html><html><body><h1>Hello World</h1></body></html>"
    dec_clean = guard.validate_file(clean_html, "page.html")
    assert dec_clean.outcome == SecurityDecisionOutcome.ACCEPTED
    assert dec_clean.source_type == SourceType.WEB_PAGE
    assert dec_clean.verified_mime_type == "text/html"
    assert len(dec_clean.warnings) == 0
    guard.quarantine_mgr.cleanup(dec_clean.quarantine_path)

    # Active script marker triggers warning
    active_html = b"<html><body><script>alert('xss');</script><h1>Hi</h1></body></html>"
    dec_active = guard.validate_file(active_html, "active.html")
    assert dec_active.outcome == SecurityDecisionOutcome.ACCEPTED
    assert len(dec_active.warnings) >= 1
    assert any("script" in w.lower() for w in dec_active.warnings)
    guard.quarantine_mgr.cleanup(dec_active.quarantine_path)

    # Binary null bytes in HTML must be rejected
    null_html = b"<html><body>\x00malicious binary</body></html>"
    dec_null = guard.validate_file(null_html, "null.html")
    assert dec_null.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_null.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT


def test_plain_text_markdown_csv(guard: ExtractionSecurityGuard):
    """Verify text, markdown, and CSV formats are correctly classified and accepted."""
    txt_bytes = b"Simple plain text file"
    dec_txt = guard.validate_file(txt_bytes, "notes.txt")
    assert dec_txt.outcome == SecurityDecisionOutcome.ACCEPTED
    assert dec_txt.verified_mime_type == "text/plain"
    guard.quarantine_mgr.cleanup(dec_txt.quarantine_path)

    md_bytes = b"# Header\n\nMarkdown body text."
    dec_md = guard.validate_file(md_bytes, "readme.md")
    assert dec_md.outcome == SecurityDecisionOutcome.ACCEPTED
    assert dec_md.verified_mime_type == "text/markdown"
    guard.quarantine_mgr.cleanup(dec_md.quarantine_path)

    csv_bytes = b"col1,col2\nval1,val2"
    dec_csv = guard.validate_file(csv_bytes, "data.csv")
    assert dec_csv.outcome == SecurityDecisionOutcome.ACCEPTED
    assert dec_csv.verified_mime_type == "text/csv"
    guard.quarantine_mgr.cleanup(dec_csv.quarantine_path)

    # Binary null bytes in text file must be rejected
    null_txt = b"Text with \x00 null bytes"
    dec_null = guard.validate_file(null_txt, "binary.txt")
    assert dec_null.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_null.error_code == ExtractionErrorCode.UNSUPPORTED_FORMAT


# -----------------------------------------------------------------------------
# Size Boundary & Declared Size Integrity Tests
# -----------------------------------------------------------------------------


def test_size_boundary_and_declared_integrity(temp_quarantine: Path):
    """Verify exact file size boundaries and declared size integrity checks."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_file_size_bytes=100,
    )
    custom_guard = ExtractionSecurityGuard(config)

    # Exactly 100 bytes is accepted
    exact_data = b"x" * 100
    dec_exact = custom_guard.validate_file(exact_data, "exact.txt")
    assert dec_exact.outcome == SecurityDecisionOutcome.ACCEPTED
    assert dec_exact.byte_count == 100
    custom_guard.quarantine_mgr.cleanup(dec_exact.quarantine_path)

    # 101 bytes is rejected as FILE_TOO_LARGE
    over_data = b"x" * 101
    dec_over = custom_guard.validate_file(over_data, "over.txt")
    assert dec_over.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_over.error_code == ExtractionErrorCode.FILE_TOO_LARGE

    # Declared size mismatch vs actual byte count
    dec_mismatch = custom_guard.validate_file(b"x" * 50, "test.txt", declared_size=80)
    assert dec_mismatch.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_mismatch.error_code == ExtractionErrorCode.CORRUPTED_DOCUMENT

    # Declared size exceeding limit rejected upfront before staging
    dec_declared_over = custom_guard.validate_file(b"x" * 10, "test.txt", declared_size=200)
    assert dec_declared_over.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_declared_over.error_code == ExtractionErrorCode.FILE_TOO_LARGE


def test_file_path_source_handling(guard: ExtractionSecurityGuard, tmp_path: Path):
    """Verify Path and string sources are inspected cleanly."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Hello from file on disk", encoding="utf-8")

    decision = guard.validate_file(file_path, "sample.txt")
    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.byte_count == file_path.stat().st_size
    guard.quarantine_mgr.cleanup(decision.quarantine_path)

    # Nonexistent path rejected
    nonexistent = tmp_path / "does_not_exist.txt"
    dec_nonexistent = guard.validate_file(nonexistent, "ghost.txt")
    assert dec_nonexistent.outcome == SecurityDecisionOutcome.REJECTED
    assert dec_nonexistent.error_code == ExtractionErrorCode.CORRUPTED_DOCUMENT


# -----------------------------------------------------------------------------
# Confidentiality & Concurrency Tests
# -----------------------------------------------------------------------------


def test_safe_log_dict_confidentiality(guard: ExtractionSecurityGuard):
    """Verify safe_log_dict() excludes document contents and local file paths."""
    pdf_bytes = make_minimal_pdf(pages=1)
    decision = guard.validate_file(pdf_bytes, "confidential.pdf")

    log_dict = decision.safe_log_dict()
    assert "quarantine_path" not in log_dict
    assert "content" not in log_dict
    assert "text" not in log_dict
    assert log_dict["outcome"] == "accepted"
    assert log_dict["verified_mime_type"] == "application/pdf"
    assert log_dict["byte_count"] == len(pdf_bytes)
    assert log_dict["sanitized_display_name"] == "confidential.pdf"

    guard.quarantine_mgr.cleanup(decision.quarantine_path)


def test_concurrency_semaphore_timeout(temp_quarantine: Path):
    """Verify semaphore saturation returns INSPECTION_FAILED with EXTRACTION_TIMEOUT."""
    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        max_concurrent_inspections=1,
        preflight_timeout_seconds=0.1,
    )
    custom_guard = ExtractionSecurityGuard(config)

    # Acquire the single permit in a background lock
    permit_acquired = threading.Event()
    release_permit = threading.Event()

    def lock_worker():
        custom_guard._semaphore.acquire()
        permit_acquired.set()
        release_permit.wait()
        custom_guard._semaphore.release()

    t = threading.Thread(target=lock_worker, daemon=True)
    t.start()
    permit_acquired.wait()

    try:
        decision = custom_guard.validate_file(b"content", "test.txt")
        assert decision.outcome == SecurityDecisionOutcome.INSPECTION_FAILED
        assert decision.error_code == ExtractionErrorCode.EXTRACTION_TIMEOUT
        assert "timed out" in decision.error_message
    finally:
        release_permit.set()
        t.join()


def test_blocking_pdf_inspection_timeout_and_cleanup(temp_quarantine: Path):
    """Prove that a blocking PDF preflight inspection triggers timeout and cleans up."""
    import time

    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        preflight_timeout_seconds=0.1,
    )
    custom_guard = ExtractionSecurityGuard(config)
    pdf_bytes = make_minimal_pdf(pages=1)

    def slow_preflight(*args, **kwargs):
        time.sleep(0.3)
        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=SourceType.PDF,
            verified_mime_type="application/pdf",
            byte_count=len(pdf_bytes),
            content_sha256="",
            sanitized_display_name="slow.pdf",
        )

    with patch.object(custom_guard, "_preflight_pdf", side_effect=slow_preflight):
        decision = custom_guard.validate_file(pdf_bytes, "slow.pdf")

    assert decision.outcome == SecurityDecisionOutcome.INSPECTION_FAILED
    assert decision.error_code == ExtractionErrorCode.EXTRACTION_TIMEOUT
    assert "timed out" in decision.error_message
    # Proves no quarantined file is leaked on disk when an inspection blocks
    assert list(temp_quarantine.iterdir()) == []


def test_blocking_zip_inspection_timeout_and_cleanup(temp_quarantine: Path):
    """Prove that a blocking Office ZIP preflight inspection triggers timeout and cleans up."""
    import time

    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        preflight_timeout_seconds=0.1,
    )
    custom_guard = ExtractionSecurityGuard(config)
    docx_bytes = make_office_zip("word")

    def slow_zip_preflight(*args, **kwargs):
        time.sleep(0.3)
        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=SourceType.DOCX,
            verified_mime_type="application/zip",
            byte_count=len(docx_bytes),
            content_sha256="",
            sanitized_display_name="slow.docx",
        )

    with patch.object(custom_guard, "_preflight_zip_container", side_effect=slow_zip_preflight):
        decision = custom_guard.validate_file(docx_bytes, "slow.docx")

    assert decision.outcome == SecurityDecisionOutcome.INSPECTION_FAILED
    assert decision.error_code == ExtractionErrorCode.EXTRACTION_TIMEOUT
    assert "timed out" in decision.error_message
    assert list(temp_quarantine.iterdir()) == []


@pytest.mark.asyncio
async def test_async_validation_success_and_timeout(temp_quarantine: Path):
    """Prove that validate_file_async executes off-thread and honors timeout & cleanup."""
    import time

    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        preflight_timeout_seconds=0.2,
    )
    custom_guard = ExtractionSecurityGuard(config)
    pdf_bytes = make_minimal_pdf(pages=1)

    # 1. Successful async execution
    decision = await custom_guard.validate_file_async(pdf_bytes, "report.pdf")
    assert decision.outcome == SecurityDecisionOutcome.ACCEPTED
    assert decision.source_type == SourceType.PDF
    custom_guard.quarantine_mgr.cleanup(decision.quarantine_path)
    assert list(temp_quarantine.iterdir()) == []

    # 2. Blocking async inspection triggers timeout and cleans up
    def blocking_inspection(*args, **kwargs):
        time.sleep(0.4)
        return decision

    with patch.object(custom_guard, "_preflight_pdf", side_effect=blocking_inspection):
        timeout_dec = await custom_guard.validate_file_async(pdf_bytes, "slow_async.pdf")

    assert timeout_dec.outcome == SecurityDecisionOutcome.INSPECTION_FAILED
    assert timeout_dec.error_code == ExtractionErrorCode.EXTRACTION_TIMEOUT
    assert list(temp_quarantine.iterdir()) == []


@pytest.mark.asyncio
async def test_async_validation_cancellation_cleanup(temp_quarantine: Path):
    """Prove that cancelling an async validation task immediately cleans up quarantine files."""
    import asyncio
    import time

    config = SecurityGuardConfig(
        quarantine_root=str(temp_quarantine),
        preflight_timeout_seconds=5.0,
    )
    custom_guard = ExtractionSecurityGuard(config)
    pdf_bytes = make_minimal_pdf(pages=1)

    started_event = asyncio.Event()

    def sleeping_preflight(*args, **kwargs):
        started_event.set()
        time.sleep(1.0)
        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=SourceType.PDF,
            verified_mime_type="application/pdf",
            byte_count=len(pdf_bytes),
            content_sha256="",
            sanitized_display_name="cancelled.pdf",
        )

    with patch.object(custom_guard, "_preflight_pdf", side_effect=sleeping_preflight):
        task = asyncio.create_task(custom_guard.validate_file_async(pdf_bytes, "cancelled.pdf"))
        await started_event.wait()
        # Cancel the active task while inspection is running
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Cleanup must be guaranteed even after task cancellation
    assert list(temp_quarantine.iterdir()) == []
    # Semaphore must be released so subsequent calls do not deadlock
    assert custom_guard._semaphore.acquire(timeout=0.1)
    custom_guard._semaphore.release()
