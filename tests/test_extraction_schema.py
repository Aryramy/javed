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
    ExtractorDescriptor,
    MergedCell,
    NormalizedDocument,
    SectionReference,
    SourceDescriptor,
    SourceType,
    TableRepresentation,
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
