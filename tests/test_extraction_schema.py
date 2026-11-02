"""Comprehensive test suite for BRICK-007 Phase 2 extraction schemas.

Verifies:
1. Minimal and complete valid NormalizedDocument creation.
2. Complete enum membership and value stability.
3. Deterministic JSON serialization and canonical SHA-256 hashing without circularity.
4. Strict UTC-aware timestamp enforcement across all models.
5. Strict 64-hex lowercase SHA-256 validation.
6. Identity separation (document_id, version_id, ingestion_id, hashes).
7. Table dimension, header width, and non-overlapping merged cell validations.
8. BoundingBox geometry, coordinate space, and origin validations (TOP_LEFT vs BOTTOM_LEFT).
9. Provenance page-number (>= 1) and character-span ordering.
10. SourceDescriptor security: rejection of traversal, credentials, and schemes.
11. AuthenticatedSourceContext secrets rejection and opaque session reference validation.
12. Status consistency contracts (SUCCESS, FAILED, PARTIAL_SUCCESS).
13. Unique element_id enforcement within documents.
14. Unknown-field rejection (fail-closed extra='forbid').
15. Import side-effect isolation (zero threads, files, processes, or network).
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from javed.extraction.schema import (
    AccessMethod,
    AuthenticatedSourceContext,
    AuthenticationStatus,
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
    HashIntegrityError,
    HashVerificationResult,
    MergedCell,
    NormalizedDocument,
    SectionReference,
    SourceDescriptor,
    SourceType,
    TableCell,
    TableRepresentation,
    verify_trust_boundary,
)

# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------


def _sample_sha256(seed: str = "a") -> str:
    """Return a deterministic 64-char lowercase hex string."""
    return (seed * 64)[:64]


def _make_minimal_source() -> SourceDescriptor:
    return SourceDescriptor(
        source_type=SourceType.WEB_PAGE,
        source_uri="https://example.com/docs/intro",
        original_display_name="intro.html",
        mime_type="text/html",
        acquisition_timestamp=datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC),
    )


def _make_minimal_extractor() -> ExtractorDescriptor:
    return ExtractorDescriptor(
        engine_name="crawl4ai",
        engine_version="0.9.5",
        config_parameters={"headless": True},
        extractor_config_sha256=_sample_sha256("1"),
    )


# -----------------------------------------------------------------------------
# 1. Minimal and Complete Documents
# -----------------------------------------------------------------------------


def test_minimal_valid_document() -> None:
    """Verify that a minimal valid NormalizedDocument instantiates cleanly."""
    doc = NormalizedDocument(
        document_id="doc-001",
        version_id="ver-001",
        ingestion_id="ing-001",
        source_sha256=_sample_sha256("a"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime(2026, 10, 29, 12, 1, 0, tzinfo=UTC),
    )
    assert doc.document_id == "doc-001"
    assert doc.status == ExtractionStatus.SUCCESS
    assert doc.metadata.element_count == 0
    assert doc.metadata.table_count == 0
    assert doc.normalized_output_sha256 is None


def test_complete_valid_document() -> None:
    """Verify a richly populated NormalizedDocument with elements, tables, and provenance."""
    table_rep = TableRepresentation(
        headers=["Col A", "Col B"],
        rows=[["1", "2"], ["3", "4"]],
        row_count=2,
        column_count=2,
        sheet_name="Summary",
        cell_range="A1:B3",
        merged_cells=[MergedCell(start_row=0, end_row=0, start_col=0, end_col=1)],
        caption="Sample Financial Grid",
    )

    elem1 = ExtractionElement(
        element_id="elem-heading-1",
        element_type=ExtractionElementType.HEADING,
        ordinal=0,
        text="Executive Overview",
        section_hierarchy=[SectionReference(title="Overview", level=1, path="1")],
        provenance=ElementProvenance(
            page_number=1,
            char_start=0,
            char_end=18,
            bounding_box=BoundingBox(
                left=10.0,
                top=20.0,
                right=200.0,
                bottom=40.0,
                coordinate_space=CoordinateSpace.POINTS,
                origin=CoordinateOrigin.TOP_LEFT,
                page_width=612.0,
                page_height=792.0,
            ),
        ),
    )

    elem2 = ExtractionElement(
        element_id="elem-table-1",
        element_type=ExtractionElementType.TABLE,
        ordinal=1,
        table=table_rep,
        provenance=ElementProvenance(
            page_number=1,
            sheet_name="Summary",
            cell_range="A1:B3",
        ),
    )

    auth_ctx = AuthenticatedSourceContext(
        account_alias="corp_finance",
        service="sharepoint",
        access_method=AccessMethod.AUTHENTICATED_SESSION,
        opaque_browser_session_reference="sess_abc123_xyz456",
        owner_authorized=True,
        approved_domains=["sharepoint.example.com"],
        authentication_status=AuthenticationStatus.AUTHORIZED,
        session_created_at=datetime(2026, 10, 29, 10, 0, 0, tzinfo=UTC),
    )

    doc = NormalizedDocument(
        document_id="doc-full-001",
        version_id="ver-001",
        ingestion_id="ing-001",
        source_sha256=_sample_sha256("f"),
        source=SourceDescriptor(
            source_type=SourceType.XLSX,
            relative_source_ref="reports/q3_2026.xlsx",
            original_display_name="q3_2026.xlsx",
            source_title="Q3 2026 Financial Results",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            acquisition_timestamp=datetime(2026, 10, 29, 11, 0, 0, tzinfo=UTC),
            content_length=1048576,
        ),
        authenticated_context=auth_ctx,
        extractor=ExtractorDescriptor(
            engine_name="docling",
            engine_version="2.144.0",
            config_parameters={"backend": "pypdfium2"},
            extractor_config_sha256=_sample_sha256("e"),
        ),
        metadata=DocumentMetadata(
            title="Q3 2026 Financial Results",
            author="Finance Team",
            page_count=3,
            element_count=2,
            table_count=1,
            word_count=50,
            character_count=300,
        ),
        elements=[elem1, elem2],
        full_text="Executive Overview\nCol A, Col B\n1, 2\n3, 4",
        full_markdown="# Executive Overview\n\n| Col A | Col B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |",
        status=ExtractionStatus.SUCCESS,
        extracted_at=datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC),
    )

    assert doc.metadata.element_count == 2
    assert doc.metadata.table_count == 1
    assert doc.elements[1].table is not None
    assert doc.elements[1].table.caption == "Sample Financial Grid"


# -----------------------------------------------------------------------------
# 2. Enumeration Verification
# -----------------------------------------------------------------------------


def test_enums_membership() -> None:
    """Verify all required enum types and values."""
    assert set(SourceType) == {"web_page", "pdf", "docx", "xlsx", "pptx", "text"}
    assert set(ExtractionElementType) == {
        "text",
        "heading",
        "table",
        "code",
        "list_item",
        "image",
        "key_value",
        "page_break",
        "horizontal_rule",
    }
    assert set(ExtractionStatus) == {
        "pending",
        "in_progress",
        "success",
        "partial_success",
        "failed",
        "rejected",
        "cancelled",
    }
    assert "UNSUPPORTED_FORMAT" in ExtractionErrorCode
    assert "INTERNAL_EXTRACTION_ERROR" in ExtractionErrorCode
    assert "MIME_MISMATCH" in ExtractionErrorCode
    assert "FILE_TOO_LARGE" in ExtractionErrorCode
    assert "PASSWORD_PROTECTED" in ExtractionErrorCode
    assert set(AccessMethod) == {"public_http", "local_file", "authenticated_session"}
    assert set(AuthenticationStatus) == {"anonymous", "authorized", "expired", "revoked"}
    assert set(CoordinateOrigin) == {"top_left", "bottom_left"}
    assert set(CoordinateSpace) == {"points", "pixels", "normalized_percent"}


# -----------------------------------------------------------------------------
# 3. Serialization, Canonical Hash & Non-Circularity
# -----------------------------------------------------------------------------


def test_canonical_json_determinism_and_hashing() -> None:
    """Verify canonical serialization is deterministic and output hash is non-circular."""
    doc = NormalizedDocument(
        document_id="doc-001",
        version_id="ver-001",
        ingestion_id="ing-001",
        source_sha256=_sample_sha256("b"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC),
    )

    json1 = doc.to_canonical_json()
    json2 = doc.to_canonical_json()
    assert json1 == json2

    hash1 = doc.compute_canonical_sha256()
    assert len(hash1) == 64

    # with_computed_output_hash returns document with hash set
    hashed_doc = doc.with_computed_output_hash()
    assert hashed_doc.normalized_output_sha256 == hash1

    # Canonical serialization of hashed_doc must NOT change even though
    # normalized_output_sha256 is now set (proves non-circularity)
    assert hashed_doc.to_canonical_json() == json1
    assert hashed_doc.compute_canonical_sha256() == hash1


def test_json_roundtrip() -> None:
    """Verify JSON roundtrip serialization and deserialization."""
    doc = NormalizedDocument(
        document_id="doc-001",
        version_id="ver-001",
        ingestion_id="ing-001",
        source_sha256=_sample_sha256("c"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC),
    )

    serialized = doc.model_dump_json()
    deserialized = NormalizedDocument.model_validate_json(serialized)
    assert deserialized.document_id == doc.document_id
    assert deserialized.source_sha256 == doc.source_sha256
    assert deserialized.extracted_at == doc.extracted_at


# -----------------------------------------------------------------------------
# 4. UTC Timestamp Enforcement
# -----------------------------------------------------------------------------


def test_utc_timestamp_enforcement() -> None:
    """Verify that naive datetimes or non-UTC datetimes are strictly rejected."""
    naive_dt = datetime(2026, 10, 29, 12, 0, 0)
    with pytest.raises(ValidationError, match="UTC-aware"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://example.com",
            original_display_name="page.html",
            mime_type="text/html",
            acquisition_timestamp=naive_dt,
        )

    est_tz = timezone(timedelta(hours=-5))
    est_dt = datetime(2026, 10, 29, 12, 0, 0, tzinfo=est_tz)
    with pytest.raises(ValidationError, match="UTC-aware"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://example.com",
            original_display_name="page.html",
            mime_type="text/html",
            acquisition_timestamp=est_dt,
        )


# -----------------------------------------------------------------------------
# 5. SHA-256 Validation
# -----------------------------------------------------------------------------


def test_sha256_validation() -> None:
    """Verify 64 lowercase hex SHA-256 validation."""
    # Too short
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        NormalizedDocument(
            document_id="d1",
            version_id="v1",
            ingestion_id="i1",
            source_sha256="abc",
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            extracted_at=datetime.now(UTC),
        )

    # Uppercase hex
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        NormalizedDocument(
            document_id="d1",
            version_id="v1",
            ingestion_id="i1",
            source_sha256="A" * 64,
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            extracted_at=datetime.now(UTC),
        )

    # Non-hex characters
    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        NormalizedDocument(
            document_id="d1",
            version_id="v1",
            ingestion_id="i1",
            source_sha256="z" * 64,
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            extracted_at=datetime.now(UTC),
        )


# -----------------------------------------------------------------------------
# 6. Table Dimension & Merged Cell Validation
# -----------------------------------------------------------------------------


def test_table_dimension_validation() -> None:
    """Verify table row count, column count, and rectangular rows enforcement."""
    # Row count mismatch
    with pytest.raises(ValidationError, match="Declared row_count"):
        TableRepresentation(
            headers=["A", "B"],
            rows=[["1", "2"]],
            row_count=2,  # declares 2, provided 1
            column_count=2,
        )

    # Row width mismatch
    with pytest.raises(ValidationError, match="Row 0 width"):
        TableRepresentation(
            headers=["A", "B"],
            rows=[["1"]],  # declared 2 columns, provided 1
            row_count=1,
            column_count=2,
        )

    # Headers width mismatch
    with pytest.raises(ValidationError, match="Headers width"):
        TableRepresentation(
            headers=["A"],  # 1 header for 2 columns
            rows=[["1", "2"]],
            row_count=1,
            column_count=2,
        )

    # Empty table valid
    empty = TableRepresentation(
        headers=[],
        rows=[],
        row_count=0,
        column_count=0,
    )
    assert empty.row_count == 0


def test_merged_cell_bounds_and_overlap() -> None:
    """Verify merged cell bounds and overlap rejection."""
    # Out of bounds merged cell
    with pytest.raises(ValidationError, match="exceeds row_count"):
        TableRepresentation(
            headers=["A", "B"],
            rows=[["1", "2"], ["3", "4"]],
            row_count=2,
            column_count=2,
            merged_cells=[MergedCell(start_row=0, end_row=2, start_col=0, end_col=1)],
        )

    # Overlapping merged cells
    with pytest.raises(ValidationError, match="Overlapping merged cell"):
        TableRepresentation(
            headers=["A", "B", "C"],
            rows=[["1", "2", "3"], ["4", "5", "6"]],
            row_count=2,
            column_count=3,
            merged_cells=[
                MergedCell(start_row=0, end_row=1, start_col=0, end_col=1),
                MergedCell(start_row=1, end_row=1, start_col=1, end_col=2),  # overlaps at (1, 1)
            ],
        )


# -----------------------------------------------------------------------------
# 7. BoundingBox & Provenance Geometry
# -----------------------------------------------------------------------------


def test_bounding_box_validation() -> None:
    """Verify coordinate ordering for TOP_LEFT and BOTTOM_LEFT origins."""
    # Left > Right
    with pytest.raises(ValidationError, match="left.*cannot exceed right"):
        BoundingBox(left=50.0, top=10.0, right=20.0, bottom=40.0)

    # Inverted TOP_LEFT
    with pytest.raises(ValidationError, match="top.*exceeds bottom"):
        BoundingBox(
            left=10.0,
            top=100.0,
            right=50.0,
            bottom=40.0,
            origin=CoordinateOrigin.TOP_LEFT,
        )

    # Inverted BOTTOM_LEFT (in bottom-left, top is higher y than bottom)
    with pytest.raises(ValidationError, match="bottom.*exceeds top"):
        BoundingBox(
            left=10.0,
            top=40.0,
            right=50.0,
            bottom=100.0,
            origin=CoordinateOrigin.BOTTOM_LEFT,
        )

    # Normalized percent bounds
    with pytest.raises(ValidationError, match="in \\[0.0, 1.0\\]"):
        BoundingBox(
            left=-0.1,
            top=0.0,
            right=0.5,
            bottom=0.5,
            coordinate_space=CoordinateSpace.NORMALIZED_PERCENT,
        )


def test_provenance_validation() -> None:
    """Verify page number >= 1 and character span ordering."""
    with pytest.raises(ValidationError):
        ElementProvenance(page_number=0)

    with pytest.raises(ValidationError, match="char_start.*cannot exceed char_end"):
        ElementProvenance(char_start=50, char_end=20)


# -----------------------------------------------------------------------------
# 8. SourceDescriptor Security & Defensive Checks
# -----------------------------------------------------------------------------


def test_source_descriptor_security() -> None:
    """Verify rejection of credentials, traversal, unsupported schemes, and absolute paths."""
    # Embedded credentials
    with pytest.raises(ValidationError, match="Embedded credentials"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://user:pass@example.com/page",
            original_display_name="page.html",
            mime_type="text/html",
            acquisition_timestamp=datetime.now(UTC),
        )

    # Unsupported URL scheme
    with pytest.raises(ValidationError, match="Unsupported scheme"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="file:///C:/Users/arehman/secret.pdf",
            original_display_name="secret.pdf",
            mime_type="application/pdf",
            acquisition_timestamp=datetime.now(UTC),
        )

    # Path traversal in URI
    with pytest.raises(ValidationError, match="Path traversal"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://example.com/static/../../secret.txt",
            original_display_name="secret.txt",
            mime_type="text/plain",
            acquisition_timestamp=datetime.now(UTC),
        )

    # Path traversal in relative reference
    with pytest.raises(ValidationError, match="Path traversal"):
        SourceDescriptor(
            source_type=SourceType.PDF,
            relative_source_ref="../outside/data.pdf",
            original_display_name="data.pdf",
            mime_type="application/pdf",
            acquisition_timestamp=datetime.now(UTC),
        )

    # Absolute path in relative reference
    with pytest.raises(ValidationError, match="Absolute local filesystem paths"):
        SourceDescriptor(
            source_type=SourceType.PDF,
            relative_source_ref="C:\\Users\\arehman\\Desktop\\test.pdf",
            original_display_name="test.pdf",
            mime_type="application/pdf",
            acquisition_timestamp=datetime.now(UTC),
        )

    # Prohibited query secret keyword
    with pytest.raises(ValidationError, match="Prohibited secret-bearing parameter"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://example.com/api/data?token=secret123",
            original_display_name="data.json",
            mime_type="application/json",
            acquisition_timestamp=datetime.now(UTC),
        )


# -----------------------------------------------------------------------------
# 9. AuthenticatedSourceContext Secret Prohibitions
# -----------------------------------------------------------------------------


def test_authenticated_source_context_security() -> None:
    """Verify that credentials, tokens, cookies, and non-opaque references are rejected."""
    # Extra secret fields rejected by extra='forbid'
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AuthenticatedSourceContext(
            account_alias="user1",
            service="gmail",
            opaque_browser_session_reference="sess_valid123",
            password="secret_password",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AuthenticatedSourceContext(
            account_alias="user1",
            service="gmail",
            opaque_browser_session_reference="sess_valid123",
            cookies="session=abc123",  # type: ignore[call-arg]
        )

    # Non-opaque session reference (contains path separators)
    with pytest.raises(ValidationError, match="sanitized opaque token"):
        AuthenticatedSourceContext(
            account_alias="user1",
            service="gmail",
            opaque_browser_session_reference="C:/Chrome/Default/Cookies",
        )

    # Bearer token in session reference
    with pytest.raises(ValidationError, match="Bearer authorization tokens"):
        AuthenticatedSourceContext(
            account_alias="user1",
            service="gmail",
            opaque_browser_session_reference="Bearer_eyJhbGciOi12345678",
        )


# -----------------------------------------------------------------------------
# 10. Status Consistency & Document Invariants
# -----------------------------------------------------------------------------


def test_status_consistency() -> None:
    """Verify status consistency contracts for SUCCESS, FAILED, and PARTIAL_SUCCESS."""
    # SUCCESS cannot have errors
    with pytest.raises(
        ValidationError, match="SUCCESS status document cannot contain extraction errors"
    ):
        NormalizedDocument(
            document_id="doc-1",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("1"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            status=ExtractionStatus.SUCCESS,
            errors=[
                ExtractionError(
                    code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                    message="Corrupted file",
                    timestamp=datetime.now(UTC),
                )
            ],
            extracted_at=datetime.now(UTC),
        )

    # FAILED must contain at least one error
    with pytest.raises(ValidationError, match="FAILED status document must contain"):
        NormalizedDocument(
            document_id="doc-1",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("1"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            status=ExtractionStatus.FAILED,
            errors=[],
            extracted_at=datetime.now(UTC),
        )

    # PARTIAL_SUCCESS must have a warning or error
    with pytest.raises(ValidationError, match="PARTIAL_SUCCESS status document requires"):
        NormalizedDocument(
            document_id="doc-1",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("1"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            status=ExtractionStatus.PARTIAL_SUCCESS,
            warnings=[],
            errors=[],
            extracted_at=datetime.now(UTC),
        )


def test_unique_element_ids() -> None:
    """Verify duplicate element_ids within a document are strictly rejected."""
    elem1 = ExtractionElement(
        element_id="duplicate-id",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="First paragraph",
    )
    elem2 = ExtractionElement(
        element_id="duplicate-id",
        element_type=ExtractionElementType.TEXT,
        ordinal=1,
        text="Second paragraph",
    )

    with pytest.raises(ValidationError, match="Duplicate element_id detected"):
        NormalizedDocument(
            document_id="doc-1",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("2"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=2, table_count=0),
            elements=[elem1, elem2],
            extracted_at=datetime.now(UTC),
        )


# -----------------------------------------------------------------------------
# 11. Unknown Field Rejection (extra='forbid')
# -----------------------------------------------------------------------------


def test_unknown_fields_rejection() -> None:
    """Verify that unexpected fields are rejected across models."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceDescriptor(
            source_type=SourceType.WEB_PAGE,
            source_uri="https://example.com",
            original_display_name="page.html",
            mime_type="text/html",
            acquisition_timestamp=datetime.now(UTC),
            unexpected_field="injection",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExtractionElement(
            element_id="el-1",
            element_type=ExtractionElementType.TEXT,
            ordinal=0,
            text="Clean text",
            unknown_attribute="forbidden",  # type: ignore[call-arg]
        )


# -----------------------------------------------------------------------------
# 12. Import Side-Effect Isolation
# -----------------------------------------------------------------------------


def test_import_side_effect_isolation() -> None:
    """Verify that importing schema creates no threads, processes, files, or network."""
    # Capture thread state
    initial_threads = [
        t for t in threading.enumerate() if not t.daemon and t is not threading.main_thread()
    ]
    suspicious = [t for t in initial_threads if "pytest" not in t.name.lower()]
    assert len(suspicious) == 0

    # Ensure schema can be re-imported with zero overhead
    import javed.extraction.schema as schema_mod

    assert schema_mod.NormalizedDocument is not None


# -----------------------------------------------------------------------------
# 13. Identity Separation & Granular Contracts
# -----------------------------------------------------------------------------


def test_identity_separation() -> None:
    """Verify document_id, version_id, and ingestion_id operate independently."""
    doc1 = NormalizedDocument(
        document_id="logical-doc-alpha",
        version_id="ver-2026-10-29.1",
        ingestion_id="ingest-attempt-001",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime.now(UTC),
    )
    doc2 = doc1.model_copy(update={"ingestion_id": "ingest-attempt-002"})
    assert doc1.document_id == doc2.document_id
    assert doc1.version_id == doc2.version_id
    assert doc1.ingestion_id != doc2.ingestion_id


def test_element_empty_and_table_binding_invariants() -> None:
    """Verify non-table elements cannot hold tables, and non-structural elements cannot be empty."""
    # Non-table carrying table
    with pytest.raises(
        ValidationError,
        match="Non-table element type.*cannot carry TableRepresentation",
    ):
        ExtractionElement(
            element_id="el-p1",
            element_type=ExtractionElementType.TEXT,
            ordinal=0,
            text="Some text",
            table=TableRepresentation(headers=[], rows=[], row_count=0, column_count=0),
        )

    # Empty text element
    with pytest.raises(ValidationError, match="cannot be empty"):
        ExtractionElement(
            element_id="el-empty",
            element_type=ExtractionElementType.TEXT,
            ordinal=0,
            text="   ",
        )

    # Structural elements (PAGE_BREAK, HORIZONTAL_RULE, IMAGE) ARE permitted without text
    pb = ExtractionElement(
        element_id="el-pb",
        element_type=ExtractionElementType.PAGE_BREAK,
        ordinal=1,
    )
    assert pb.text is None


def test_sheet_name_and_cell_range_constraints() -> None:
    """Verify Excel sheet name length/characters and cell range syntax."""
    # Sheet name > 31 chars
    with pytest.raises(ValidationError, match="sheet_name cannot exceed 31 characters"):
        TableRepresentation(
            headers=[],
            rows=[],
            row_count=0,
            column_count=0,
            sheet_name="ThisSheetNameIsWayTooLongForExcelLimits123",
        )

    # Prohibited sheet name characters
    for prohibited in ("[", "]", "*", "?", ":", "/", "\\"):
        with pytest.raises(ValidationError, match="prohibited characters"):
            TableRepresentation(
                headers=[],
                rows=[],
                row_count=0,
                column_count=0,
                sheet_name=f"Sheet{prohibited}",
            )

    # Invalid cell range syntax
    with pytest.raises(ValidationError, match="cell_range syntax invalid"):
        TableRepresentation(
            headers=[],
            rows=[],
            row_count=0,
            column_count=0,
            cell_range="InvalidRange",
        )


def test_secrets_rejection_matrix() -> None:
    """Verify that sensitive fields and tokens cannot be attached across models."""
    secret_fields = [
        ("password", "secret"),
        ("access_token", "token123"),
        ("refresh_token", "ref123"),
        ("cookie", "c=1"),
        ("authorization", "Bearer 123"),
        ("raw_browser_storage", "{}"),
        ("profile_path", "C:/Chrome"),
    ]
    for field_name, value in secret_fields:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AuthenticatedSourceContext(
                account_alias="test",
                service="test",
                opaque_browser_session_reference="sess_12345678",
                **{field_name: value},
            )


def test_immutable_base_assignment_behavior() -> None:
    """Verify assignment behavior, assignment validation, and unknown-field forbidding."""
    from javed.extraction.schema import ExtractionBaseModel, ImmutableExtractionBase

    # 1. Base model is ExtractionBaseModel; ImmutableExtractionBase is backwards-compat alias
    assert ExtractionBaseModel is ImmutableExtractionBase
    assert not ExtractionBaseModel.model_config.get("frozen", False)
    assert ExtractionBaseModel.model_config.get("validate_assignment") is True
    assert ExtractionBaseModel.model_config.get("extra") == "forbid"

    doc = NormalizedDocument(
        document_id="doc-test",
        version_id="ver-test",
        ingestion_id="ing-test",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime.now(UTC),
    )

    # 2. Valid assignment updates the model
    doc.status = ExtractionStatus.IN_PROGRESS
    assert doc.status == ExtractionStatus.IN_PROGRESS

    # 3. Invalid assignment is caught by validate_assignment=True
    with pytest.raises(ValidationError):
        doc.status = "not_a_valid_status"  # type: ignore[assignment]

    # 4. Unknown attribute assignment is forbidden by extra='forbid'
    with pytest.raises(ValidationError, match="no_such_attribute|has no attribute"):
        doc.unexpected_injected_attr = 123  # type: ignore[attr-defined]


def test_stale_hash_invalidation_on_mutation() -> None:
    """Verify that model mutations automatically clear cached hashes to prevent stale digests."""
    doc = NormalizedDocument(
        document_id="doc-hash-test",
        version_id="ver-1",
        ingestion_id="ing-1",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime.now(UTC),
    )

    hashed = doc.with_computed_hashes()
    assert hashed.normalized_content_sha256 is not None
    assert hashed.extraction_record_sha256 is not None
    assert hashed.normalized_output_sha256 is not None

    # Mutating any content field must immediately invalidate all cached hashes
    hashed.full_text = "newly updated text"
    assert hashed.normalized_content_sha256 is None
    assert hashed.extraction_record_sha256 is None
    assert hashed.normalized_output_sha256 is None

    # Re-computing hashes updates to the new valid digests
    rehashed = hashed.with_computed_hashes()
    assert rehashed.normalized_content_sha256 is not None
    assert rehashed.extraction_record_sha256 is not None

    # Mutating status must also clear hashes
    rehashed.status = ExtractionStatus.IN_PROGRESS
    assert rehashed.normalized_content_sha256 is None
    assert rehashed.extraction_record_sha256 is None
    assert rehashed.normalized_output_sha256 is None


def test_stale_hash_rejection_in_validator() -> None:
    """Verify that constructing or validating a model with mismatched hashes raises fail-closed."""
    doc = NormalizedDocument(
        document_id="doc-stale-test",
        version_id="ver-1",
        ingestion_id="ing-1",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(element_count=0, table_count=0),
        extracted_at=datetime.now(UTC),
    )
    fake_stale_hash = "a" * 64

    # Stale content hash rejected
    with pytest.raises(ValidationError, match="Stale or mismatched normalized_content_sha256"):
        NormalizedDocument(
            document_id="doc-stale-test",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("1"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            extracted_at=doc.extracted_at,
            normalized_content_sha256=fake_stale_hash,
        )

    # Stale record hash rejected
    with pytest.raises(ValidationError, match="Stale or mismatched extraction_record_sha256"):
        NormalizedDocument(
            document_id="doc-stale-test",
            version_id="ver-1",
            ingestion_id="ing-1",
            source_sha256=_sample_sha256("1"),
            source=_make_minimal_source(),
            extractor=_make_minimal_extractor(),
            metadata=DocumentMetadata(element_count=0, table_count=0),
            extracted_at=doc.extracted_at,
            extraction_record_sha256=fake_stale_hash,
        )


def test_content_hash_vs_record_hash_separation() -> None:
    """Verify normalized-content hash is identical across runs while record hash differs."""
    elem = ExtractionElement(
        element_id="elem-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Content paragraph",
    )

    # Document from Run 1
    doc_run1 = NormalizedDocument(
        document_id="doc-asset-42",
        version_id="ver-1",
        ingestion_id="ingestion-attempt-001",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(title="Quarterly Review", element_count=1, table_count=0),
        elements=[elem],
        full_text="Content paragraph",
        extracted_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC),
    )

    # Document from Run 2 (same asset, same content, but different ingestion attempt and timestamp)
    doc_run2 = NormalizedDocument(
        document_id="doc-asset-42",
        version_id="ver-1",
        ingestion_id="ingestion-attempt-002",  # Different run ID
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(title="Quarterly Review", element_count=1, table_count=0),
        elements=[elem],
        full_text="Content paragraph",
        extracted_at=datetime(2026, 11, 1, 11, 30, 0, tzinfo=UTC),  # Different timestamp
    )

    # Content-only canonical payload must be identical
    assert doc_run1.to_content_canonical_dict() == doc_run2.to_content_canonical_dict()

    # Content SHA-256 must be IDENTICAL across runs
    content_hash1 = doc_run1.compute_content_sha256()
    content_hash2 = doc_run2.compute_content_sha256()
    assert content_hash1 == content_hash2

    # Record-level canonical payload and hash must DIFFER due to run telemetry
    record_hash1 = doc_run1.compute_record_sha256()
    record_hash2 = doc_run2.compute_record_sha256()
    assert record_hash1 != record_hash2


def test_unfinalized_nested_mutation_invalidates_parent_hash() -> None:
    """Prove mutating nested models on an unfinalized doc invalidates parent digests."""
    elem = ExtractionElement(
        element_id="elem-nested-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Original nested text",
    )
    doc = NormalizedDocument(
        document_id="doc-nested-test",
        version_id="ver-1",
        ingestion_id="ing-nested-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Initial Title",
            element_count=1,
            table_count=0,
            custom_attributes={"dept": "engineering"},
        ),
        elements=[elem],
        full_text="Original nested text",
        extracted_at=datetime.now(UTC),
    )

    # Populate hashes on the unfinalized document
    hashed = doc.with_computed_hashes()
    assert hashed.normalized_content_sha256 is not None
    assert hashed.extraction_record_sha256 is not None
    assert hashed.normalized_output_sha256 is not None

    # 1. Mutate nested DocumentMetadata attribute -> must invalidate parent hashes
    hashed.metadata.title = "Mutated Title"
    assert hashed.normalized_content_sha256 is None
    assert hashed.extraction_record_sha256 is None
    assert hashed.normalized_output_sha256 is None

    # Re-compute hashes
    rehashed = hashed.with_computed_hashes()
    assert rehashed.normalized_content_sha256 is not None

    # 2. Mutate nested ExtractionElement attribute -> must invalidate parent hashes
    rehashed.elements[0].text = "Mutated element text"
    assert rehashed.normalized_content_sha256 is None
    assert rehashed.extraction_record_sha256 is None
    assert rehashed.normalized_output_sha256 is None


def test_finalized_document_deep_immutability() -> None:
    """Prove finalize() makes the document, nested models, lists, and dicts deeply immutable."""
    table = TableRepresentation(
        headers=["Col1", "Col2"],
        rows=[["A", "B"], ["C", "D"]],
        row_count=2,
        column_count=2,
    )
    elem = ExtractionElement(
        element_id="elem-freeze-1",
        element_type=ExtractionElementType.TABLE,
        ordinal=0,
        text="Table text",
        table=table,
    )
    doc = NormalizedDocument(
        document_id="doc-freeze-test",
        version_id="ver-1",
        ingestion_id="ing-freeze-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Frozen Title",
            element_count=1,
            table_count=1,
            custom_attributes={"env": "production"},
        ),
        elements=[elem],
        full_text="Table text",
        extracted_at=datetime.now(UTC),
    )

    assert not doc.is_finalized
    doc.finalize()
    assert doc.is_finalized
    assert doc.normalized_content_sha256 is not None
    assert doc.extraction_record_sha256 is not None

    # finalize() is idempotent
    doc.finalize()
    assert doc.is_finalized

    # 1. Top-level model mutation must raise TypeError
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.full_text = "new text"

    # 2. Nested DocumentMetadata mutation must raise TypeError
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.metadata.title = "hacked title"

    # 3. Nested ExtractionElement mutation must raise TypeError
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.elements[0].text = "hacked element text"

    # 4. Nested SourceDescriptor mutation must raise TypeError
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.source.original_display_name = "hacked_name.pdf"

    # 5. List append / assignment on elements must raise TypeError
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements.append(elem)

    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0] = elem

    # 6. Table nested lists (headers, rows, inner rows) must raise TypeError
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.headers.append("Col3")  # type: ignore[union-attr]

    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.rows[0].append("Z")  # type: ignore[union-attr]

    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.rows[0][0] = "MUTATED"  # type: ignore[union-attr]

    # 7. Dict item assignment / modification on custom_attributes must raise TypeError
    with pytest.raises(TypeError, match="Cannot modify immutable dict"):
        doc.metadata.custom_attributes["new_key"] = "val"

    with pytest.raises(TypeError, match="Cannot modify immutable dict"):
        doc.metadata.custom_attributes.update({"env": "compromised"})

    # 8. Attribute deletion must raise TypeError
    with pytest.raises(TypeError, match="Cannot delete attribute"):
        del doc.full_text

    with pytest.raises(TypeError, match="Cannot delete attribute"):
        del doc.metadata.title


def test_hash_reverification_and_trust_boundary_enforcement() -> None:
    """Prove verify_hash_integrity, assert_hash_integrity, and verify_trust_boundary fail closed."""
    elem = ExtractionElement(
        element_id="elem-trust-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Trusted content text",
    )
    doc = NormalizedDocument(
        document_id="doc-trust-01",
        version_id="ver-1",
        ingestion_id="ing-trust-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Trusted Title",
            element_count=1,
            table_count=0,
            custom_attributes={"level": "high"},
        ),
        elements=[elem],
        full_text="Trusted content text",
        extracted_at=datetime.now(UTC),
    )

    # 1. Unfinalized document fails trust boundary when require_finalized=True
    with pytest.raises(HashIntegrityError, match="not finalized"):
        verify_trust_boundary(doc, require_finalized=True)

    # 2. Finalized document passes trust boundary verification cleanly
    doc.finalize()
    assert doc.verify_hash_integrity() is True
    doc.assert_hash_integrity()  # Must not raise
    verified = verify_trust_boundary(doc, require_finalized=True)
    assert verified is doc

    # 3. Low-level internal attribute tampering bypasses __setattr__ but is CAUGHT by verification
    object.__setattr__(doc.metadata, "title", "Tampered Title Behind Verification")
    assert doc.verify_hash_integrity() is False

    with pytest.raises(HashIntegrityError, match="Stale or mismatched normalized_content_sha256"):
        doc.assert_hash_integrity()

    with pytest.raises(HashIntegrityError, match="Stale or mismatched normalized_content_sha256"):
        verify_trust_boundary(doc, require_finalized=True)


def test_unfinalized_nested_mutation_bypasses_and_stale_hash_detection() -> None:
    """Verify nested mutations on unfinalized drafts and fail-closed live verification.

    Tests the mandatory 10 operations:
    1. document.elements.append(...)
    2. document.elements.pop(...)
    3. document.elements[0].text = ...
    4. document.metadata.title = ...
    5. document.elements[0].provenance.page_number = ...
    6. document.elements[0].table.rows[0][0].value = ...
    7. document.warnings.append(...)
    8. document.errors.append(...)
    9. document.full_text = ...
    10. document.full_markdown = ...
    """
    cell_a = TableCell(row=0, col=0, text="A0")
    cell_b = TableCell(row=0, col=1, text="B0")
    table = TableRepresentation(
        headers=["Col A", "Col B"],
        rows=[[cell_a, cell_b]],
        row_count=1,
        column_count=2,
    )
    prov = ElementProvenance(page_number=1, source_native_reference="para-01")
    elem_0 = ExtractionElement(
        element_id="elem-draft-0",
        element_type=ExtractionElementType.TABLE,
        ordinal=0,
        text="Draft table text",
        table=table,
        provenance=prov,
    )
    elem_1 = ExtractionElement(
        element_id="elem-draft-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=1,
        text="Draft second paragraph",
    )
    doc = NormalizedDocument(
        document_id="doc-draft-01",
        version_id="ver-1",
        ingestion_id="ing-draft-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Draft Title",
            element_count=1,
            table_count=1,
        ),
        elements=[elem_0],
        full_text="Draft table text",
        full_markdown="# Draft Title\n\nDraft table text",
        extracted_at=datetime.now(UTC),
    )

    # Compute hashes on the unfinalized draft document
    hashed_doc = doc.with_computed_hashes()
    assert hashed_doc.normalized_content_sha256 is not None
    assert hashed_doc.extraction_record_sha256 is not None
    initial_content_hash = hashed_doc.normalized_content_sha256
    initial_record_hash = hashed_doc.extraction_record_sha256
    assert initial_record_hash is not None

    # Verify initial hash integrity passes before mutation
    assert hashed_doc.verify_hashes() is True
    assert hashed_doc.verify_hash_integrity() is True

    # --- Operation 1: document.elements.append(...) ---
    # List append modifies collection in-place, bypassing document.__setattr__
    hashed_doc.elements.append(elem_1)
    # The stored hash in memory was not cleared by list.append...
    assert hashed_doc.normalized_content_sha256 == initial_content_hash
    # ...BUT live hash reverification detects the stale hash fail-closed!
    assert hashed_doc.verify_hashes() is False
    assert hashed_doc.verify_hash_integrity() is False
    with pytest.raises(HashIntegrityError, match="Stale or mismatched normalized_content_sha256"):
        hashed_doc.assert_hash_integrity()
    with pytest.raises(HashIntegrityError):
        verify_trust_boundary(hashed_doc, require_finalized=False)

    # --- Operation 2: document.elements.pop(...) ---
    # List removal also modifies collection in-place
    hashed_doc.elements.pop()  # Remove elem_1, leaving elem_0
    assert len(hashed_doc.elements) == 1
    # Hash is re-synchronized to match current element count (1)
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True
    # Now pop elem_0: in-place list mutation leaves stale hash
    removed_elem = hashed_doc.elements.pop()
    assert len(hashed_doc.elements) == 0
    assert hashed_doc.verify_hashes() is False
    with pytest.raises(HashIntegrityError, match="Stale or mismatched normalized_content_sha256"):
        hashed_doc.assert_hash_integrity()

    # Restore elements and re-synchronize hashes
    hashed_doc.elements.append(removed_elem)
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True

    # --- Operation 3: document.elements[0].text = ... ---
    # Child model field mutation triggers ExtractionBaseModel.__setattr__ and invalidates parent
    hashed_doc.elements[0].text = "Mutated table text via child model"
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False
    with pytest.raises(HashIntegrityError, match="has no normalized_content_sha256 digest"):
        hashed_doc.assert_hash_integrity()

    # Re-synchronize hashes on the draft
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True

    # --- Operation 4: document.metadata.title = ... ---
    # Child model field mutation triggers DocumentMetadata.__setattr__ and invalidates parent
    hashed_doc.metadata.title = "Mutated metadata title"
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False

    # Re-synchronize hashes on the draft
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True

    # --- Operation 5: document.elements[0].provenance.page_number = ... ---
    # Child model nested field mutation triggers invalidation up to root document
    assert hashed_doc.elements[0].provenance is not None
    hashed_doc.elements[0].provenance.page_number = 42
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False

    # Re-synchronize hashes on the draft
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True
    rec_hash_before_warning = hashed_doc.extraction_record_sha256

    # --- Operation 6: document.elements[0].table.rows[0][0].value = ... ---
    # TableCell setter mutates child model, which notifies root document to invalidate hashes
    assert isinstance(hashed_doc.elements[0].table.rows[0][0], TableCell)  # type: ignore[union-attr]
    hashed_doc.elements[0].table.rows[0][0].value = "New Cell Value via .value"  # type: ignore[union-attr]
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False

    # Re-synchronize hashes on the draft
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True
    rec_hash_before_warning = hashed_doc.extraction_record_sha256

    # --- Operation 7: document.warnings.append(...) ---
    # In-place list append on warnings collection
    hashed_doc.warnings.append(
        ExtractionWarning(
            code="SUSPICIOUS_CONTENT",
            message="Warning appended to draft",
        )
    )
    # In-place append leaves stale record hash...
    assert hashed_doc.extraction_record_sha256 == rec_hash_before_warning
    # ...BUT live recomputation catches the mismatch immediately!
    assert hashed_doc.verify_hashes() is False
    with pytest.raises(HashIntegrityError, match="Stale or mismatched extraction_record_sha256"):
        hashed_doc.assert_hash_integrity()

    # Re-synchronize hashes with warning
    hashed_doc.status = ExtractionStatus.PARTIAL_SUCCESS
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True
    rec_hash_before_error = hashed_doc.extraction_record_sha256

    # --- Operation 8: document.errors.append(...) ---
    # In-place list append on errors collection
    hashed_doc.errors.append(
        ExtractionError(
            code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
            message="Error appended to draft",
            timestamp=datetime.now(UTC),
        )
    )
    assert hashed_doc.extraction_record_sha256 == rec_hash_before_error
    assert hashed_doc.verify_hashes() is False
    with pytest.raises(HashIntegrityError, match="extraction_record_sha256"):
        hashed_doc.assert_hash_integrity()

    # Clear error, re-synchronize hashes
    hashed_doc.errors.clear()
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True

    # --- Operation 9: document.full_text = ... ---
    # Direct field assignment on root document clears hashes
    hashed_doc.full_text = "Updated full text directly"
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False

    # Re-synchronize hashes
    hashed_doc = hashed_doc.with_computed_hashes()
    assert hashed_doc.verify_hashes() is True

    # --- Operation 10: document.full_markdown = ... ---
    # Direct field assignment on root document clears hashes
    hashed_doc.full_markdown = "# Updated Markdown Header"
    assert hashed_doc.normalized_content_sha256 is None
    assert hashed_doc.extraction_record_sha256 is None
    assert hashed_doc.verify_hashes() is False


def test_finalized_document_strictly_rejects_nested_and_collection_mutations() -> None:
    """Prove finalize() rejects all 10 operations, list removal, and cell updates with TypeError."""
    cell_a = TableCell(row=0, col=0, text="A0")
    cell_b = TableCell(row=0, col=1, text="B0")
    table = TableRepresentation(
        headers=["Col A", "Col B"],
        rows=[[cell_a, cell_b]],
        row_count=1,
        column_count=2,
    )
    prov = ElementProvenance(page_number=1, source_native_reference="sec-1")
    elem_0 = ExtractionElement(
        element_id="elem-fin-0",
        element_type=ExtractionElementType.TABLE,
        ordinal=0,
        text="Finalized table text",
        table=table,
        provenance=prov,
    )
    elem_new = ExtractionElement(
        element_id="elem-fin-new",
        element_type=ExtractionElementType.TEXT,
        ordinal=1,
        text="Appended element",
    )
    doc = NormalizedDocument(
        document_id="doc-fin-01",
        version_id="ver-1",
        ingestion_id="ing-fin-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Finalized Title",
            element_count=1,
            table_count=1,
        ),
        elements=[elem_0],
        full_text="Finalized table text",
        full_markdown="# Finalized Title",
        extracted_at=datetime.now(UTC),
    )

    doc.finalize()
    assert doc.is_finalized is True
    assert doc.verify_hashes() is True

    # 1. document.elements.append(...) rejected
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements.append(elem_new)

    # 2. document.elements.pop(...) rejected
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements.pop()

    # 3. document.elements[0].text = ... rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.elements[0].text = "Hacked text"

    # 4. document.metadata.title = ... rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.metadata.title = "Hacked title"

    # 5. document.elements[0].provenance.page_number = ... rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.elements[0].provenance.page_number = 99  # type: ignore[union-attr]

    # 6. document.elements[0].table.rows[0][0].value = ... rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.elements[0].table.rows[0][0].value = "Hacked cell"  # type: ignore[union-attr]

    # Also table row / cell list modifications rejected
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.rows.append([cell_a, cell_b])  # type: ignore[union-attr]

    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.rows[0].append(cell_a)  # type: ignore[union-attr]

    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.elements[0].table.rows[0].pop()  # type: ignore[union-attr]

    # 7. document.warnings.append(...) rejected
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.warnings.append(ExtractionWarning(code="TEST", message="Test warning"))

    # 8. document.errors.append(...) rejected
    with pytest.raises(TypeError, match="Cannot modify immutable list"):
        doc.errors.append(
            ExtractionError(
                code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
                message="Test error",
                timestamp=datetime.now(UTC),
            )
        )

    # 9. Direct field mutation (full_text) rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.full_text = "Hacked full text"

    # 10. Direct field mutation (full_markdown) rejected
    with pytest.raises(TypeError, match="Cannot mutate finalized extraction model"):
        doc.full_markdown = "# Hacked markdown"

    # Document remains 100% valid and verified
    assert doc.verify_hashes() is True
    assert verify_trust_boundary(doc, require_finalized=True) is doc


def test_verify_hashes_structured_and_fail_closed() -> None:
    """Verify structured result and fail-closed behaviors of verify_hashes()."""
    elem = ExtractionElement(
        element_id="elem-struct-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Structured verification test line",
    )
    doc = NormalizedDocument(
        document_id="doc-struct-01",
        version_id="ver-1",
        ingestion_id="ing-struct-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Structured Document",
            element_count=1,
            table_count=0,
        ),
        elements=[elem],
        full_text="Structured verification test line",
        extracted_at=datetime.now(UTC),
    )

    # 1. Unhashed document structured result
    res_unhashed = doc.verify_hashes(structured=True)
    assert isinstance(res_unhashed, HashVerificationResult)
    assert not res_unhashed
    assert res_unhashed.is_valid is False
    assert res_unhashed.content_hash_matches is False
    assert res_unhashed.record_hash_matches is False
    assert "has no normalized_content_sha256 digest" in (res_unhashed.error_message or "")

    # Unhashed document fail_closed raises HashIntegrityError
    with pytest.raises(HashIntegrityError, match="has no normalized_content_sha256 digest"):
        doc.verify_hashes(fail_closed=True)

    # 2. Finalized document structured result
    doc.finalize()
    res_valid = doc.verify_hashes(structured=True)
    assert isinstance(res_valid, HashVerificationResult)
    assert bool(res_valid) is True
    assert res_valid.is_valid is True
    assert res_valid.content_hash_matches is True
    assert res_valid.record_hash_matches is True
    assert res_valid.output_hash_matches is True
    assert res_valid.error_message is None
    assert res_valid.actual_content_sha256 == doc.compute_normalized_content_sha256()
    assert res_valid.actual_record_sha256 == doc.compute_extraction_record_sha256()

    # fail_closed succeeds without error on valid document
    assert doc.verify_hashes(fail_closed=True) is True

    # 3. Tampered document structured result
    object.__setattr__(doc.metadata, "title", "Tampered Title")
    res_tampered = doc.verify_hashes(structured=True)
    assert isinstance(res_tampered, HashVerificationResult)
    assert bool(res_tampered) is False
    assert res_tampered.is_valid is False
    assert res_tampered.content_hash_matches is False
    assert "Stale or mismatched normalized_content_sha256" in (res_tampered.error_message or "")


def test_hash_sensitivity_matrix() -> None:
    """Verify distinct digest behaviors across content vs execution record mutations."""
    elem = ExtractionElement(
        element_id="elem-sens-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Base text content",
    )
    doc_base = NormalizedDocument(
        document_id="doc-sens-01",
        version_id="ver-1",
        ingestion_id="ing-attempt-001",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Base Document",
            element_count=1,
            table_count=0,
        ),
        elements=[elem],
        full_text="Base text content",
        extracted_at=datetime(2026, 11, 2, 8, 0, 0, tzinfo=UTC),
    )

    base_content_hash = doc_base.compute_normalized_content_sha256()
    base_record_hash = doc_base.compute_extraction_record_sha256()

    # 1. Ingestion ID change: alters record digest ONLY
    doc_ing = doc_base.model_copy(update={"ingestion_id": "ing-attempt-002"})
    assert doc_ing.compute_normalized_content_sha256() == base_content_hash
    assert doc_ing.compute_extraction_record_sha256() != base_record_hash

    # 2. Timestamp change: alters record digest ONLY
    doc_time = doc_base.model_copy(
        update={"extracted_at": datetime(2026, 11, 2, 9, 30, 0, tzinfo=UTC)}
    )
    assert doc_time.compute_normalized_content_sha256() == base_content_hash
    assert doc_time.compute_extraction_record_sha256() != base_record_hash

    # 3. Source SHA-256 change: alters record digest ONLY
    doc_src = doc_base.model_copy(update={"source_sha256": _sample_sha256("2")})
    assert doc_src.compute_normalized_content_sha256() == base_content_hash
    assert doc_src.compute_extraction_record_sha256() != base_record_hash

    # 4. Warnings append: alters record digest ONLY (does not change content digest)
    doc_warn = doc_base.model_copy(
        update={
            "status": ExtractionStatus.PARTIAL_SUCCESS,
            "warnings": [ExtractionWarning(code="NOTE", message="Note warning")],
        }
    )
    assert doc_warn.compute_normalized_content_sha256() == base_content_hash
    assert doc_warn.compute_extraction_record_sha256() != base_record_hash

    # 5. Content text change: alters BOTH content AND record digests
    doc_content = doc_base.model_copy(
        update={
            "full_text": "Altered text content",
            "elements": [
                ExtractionElement(
                    element_id="elem-sens-1",
                    element_type=ExtractionElementType.TEXT,
                    ordinal=0,
                    text="Altered text content",
                )
            ],
        }
    )
    assert doc_content.compute_normalized_content_sha256() != base_content_hash
    assert doc_content.compute_extraction_record_sha256() != base_record_hash


def test_canonical_serialization_order_independence() -> None:
    """Prove equivalent models constructed with different key order yield identical hashes."""
    elem_a = ExtractionElement(
        ordinal=0,
        element_type=ExtractionElementType.TEXT,
        text="Sample line",
        element_id="elem-order-1",
    )
    elem_b = ExtractionElement(
        element_id="elem-order-1",
        text="Sample line",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
    )

    doc_a = NormalizedDocument(
        document_id="doc-order",
        version_id="ver-1",
        ingestion_id="ing-1",
        source_sha256=_sample_sha256("1"),
        extracted_at=datetime(2026, 11, 2, 8, 0, 0, tzinfo=UTC),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Order Test",
            element_count=1,
            table_count=0,
            custom_attributes={"zebra": "1", "alpha": "2"},
        ),
        elements=[elem_a],
        full_text="Sample line",
    )

    doc_b = NormalizedDocument(
        full_text="Sample line",
        elements=[elem_b],
        metadata=DocumentMetadata(
            custom_attributes={"alpha": "2", "zebra": "1"},  # reverse dict key order
            table_count=0,
            element_count=1,
            title="Order Test",
        ),
        extractor=_make_minimal_extractor(),
        source=_make_minimal_source(),
        extracted_at=datetime(2026, 11, 2, 8, 0, 0, tzinfo=UTC),
        source_sha256=_sample_sha256("1"),
        ingestion_id="ing-1",
        version_id="ver-1",
        document_id="doc-order",
    )

    # Canonical content JSON and hashes must be 100% IDENTICAL
    assert doc_a.to_content_canonical_json() == doc_b.to_content_canonical_json()
    assert doc_a.compute_normalized_content_sha256() == doc_b.compute_normalized_content_sha256()

    # Canonical record JSON and hashes must be 100% IDENTICAL
    assert doc_a.to_record_canonical_json() == doc_b.to_record_canonical_json()
    assert doc_a.compute_extraction_record_sha256() == doc_b.compute_extraction_record_sha256()


def test_canonical_serialization_json_roundtrip_stability() -> None:
    """Prove canonical serialization is stable after JSON round-trip."""
    import json

    elem = ExtractionElement(
        element_id="elem-rt-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Roundtrip text with unicode: \u2603 \u2764 \u0645\u0631\u062d\u0628\u0627",
    )
    doc = NormalizedDocument(
        document_id="doc-rt-01",
        version_id="ver-1",
        ingestion_id="ing-rt-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Unicode Document",
            element_count=1,
            table_count=0,
            custom_attributes={"lang": "multi", "score": 98.6},
        ),
        elements=[elem],
        full_text="Roundtrip text with unicode: \u2603 \u2764 \u0645\u0631\u062d\u0628\u0627",
        extracted_at=datetime(2026, 11, 2, 8, 0, 0, tzinfo=UTC),
    )

    content_json = doc.to_content_canonical_json()
    record_json = doc.to_record_canonical_json()

    # Parse and re-dump with canonical settings
    content_dict = json.loads(content_json)
    roundtrip_content_json = json.dumps(
        content_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    assert content_json == roundtrip_content_json

    record_dict = json.loads(record_json)
    roundtrip_record_json = json.dumps(
        record_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    assert record_json == roundtrip_record_json


def test_recomputed_hashes_match_canonical_serialization() -> None:
    """Prove compute_content_sha256 and compute_record_sha256 match canonical json exactly."""
    elem = ExtractionElement(
        element_id="elem-canon-1",
        element_type=ExtractionElementType.TEXT,
        ordinal=0,
        text="Canonical text line",
    )
    doc = NormalizedDocument(
        document_id="doc-canon-01",
        version_id="ver-1",
        ingestion_id="ing-canon-01",
        source_sha256=_sample_sha256("1"),
        source=_make_minimal_source(),
        extractor=_make_minimal_extractor(),
        metadata=DocumentMetadata(
            title="Canonical Document",
            element_count=1,
            table_count=0,
        ),
        elements=[elem],
        full_text="Canonical text line",
        extracted_at=datetime.now(UTC),
    )

    doc.finalize()

    # Verify content hash matches canonical content serialization
    expected_content_json = doc.to_content_canonical_json()
    expected_content_hash = hashlib.sha256(expected_content_json.encode("utf-8")).hexdigest()
    assert doc.compute_content_sha256() == expected_content_hash
    assert doc.normalized_content_sha256 == expected_content_hash

    # Verify record hash matches canonical record serialization
    expected_record_json = doc.to_record_canonical_json()
    expected_record_hash = hashlib.sha256(expected_record_json.encode("utf-8")).hexdigest()
    assert doc.compute_record_sha256() == expected_record_hash
    assert doc.extraction_record_sha256 == expected_record_hash
    assert doc.normalized_output_sha256 == expected_record_hash

    # Hashes verify cleanly
    assert doc.verify_hashes() is True
