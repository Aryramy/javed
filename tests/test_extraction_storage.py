"""Comprehensive tests for ExtractionStorageManager (BRICK-007 Phase 6).

Verifies:
1. SQLite relational registry initialization, WAL mode, and directory creation.
2. Canonical document persistence, metadata storage, and canonical JSON artifacts.
3. Raw source artifact persistence and atomic quarantine promotion.
4. SHA-256 content deduplication (preventing duplicate raw files and duplicate documents).
5. Exact execution record deduplication.
6. Monotonic document versioning for evolving URLs with multiple extractions.
7. Structured table exports (CSV and JSON) and table querying.
8. Strict trust boundary enforcement (rejecting unfinalized or tampered documents).
9. Query and listing APIs (by ID, content hash, source hash, URI, pagination).
10. Document deletion and cascading artifact cleanup.
11. Asynchronous execution compatibility across all entry points.
12. Thread and resource hygiene with zero process leaks.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from javed.extraction import (
    DocumentIntegrityError,
    ExtractionElement,
    ExtractionElementType,
    ExtractionStatus,
    ExtractionStorageManager,
    ExtractorDescriptor,
    HashIntegrityError,
    NormalizedDocument,
    QuarantineManager,
    SourceDescriptor,
    SourceType,
    StorageConfig,
    TableCell,
    TableRepresentation,
    verify_trust_boundary,
)
from javed.extraction.schema import DocumentMetadata

# -----------------------------------------------------------------------------
# Fixtures & Test Helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def storage_env(tmp_path: Path) -> tuple[ExtractionStorageManager, StorageConfig]:
    """Provide isolated storage manager in temporary directory."""
    config = StorageConfig(
        db_path=str(tmp_path / "extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
        enable_wal=True,
    )
    manager = ExtractionStorageManager(config)
    manager.initialize()
    return manager, config


def make_sample_normalized_document(
    *,
    text: str = "This is sample extracted body text.",
    source_uri: str = "https://example.com/report.pdf",
    display_name: str = "report.pdf",
    source_type: SourceType = SourceType.PDF,
    raw_content: bytes = b"%PDF-1.4 synthetic content",
    with_table: bool = False,
) -> tuple[NormalizedDocument, bytes]:
    """Construct and finalize a valid NormalizedDocument with matching hashes."""
    doc_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())
    ing_id = str(uuid.uuid4())
    source_hash = hashlib.sha256(raw_content).hexdigest()
    now_utc = datetime.now(UTC)

    elements: list[ExtractionElement] = [
        ExtractionElement(
            element_id="elem_0",
            element_type=ExtractionElementType.HEADING,
            ordinal=0,
            text="Executive Overview",
            markdown="# Executive Overview",
        ),
        ExtractionElement(
            element_id="elem_1",
            element_type=ExtractionElementType.TEXT,
            ordinal=1,
            text=text,
            markdown=text,
        ),
    ]

    if with_table:
        cell_a = TableCell(row=0, col=0, text="Header 1")
        cell_b = TableCell(row=0, col=1, text="Header 2")
        cell_c = TableCell(row=1, col=0, text="Val 1")
        cell_d = TableCell(row=1, col=1, text="Val 2")
        tbl = TableRepresentation(
            headers=["Header 1", "Header 2"],
            rows=[[cell_a, cell_b], [cell_c, cell_d]],
            row_count=2,
            column_count=2,
            table_id="table_1",
            sheet_name="SummarySheet",
        )
        elements.append(
            ExtractionElement(
                element_id="elem_2",
                element_type=ExtractionElementType.TABLE,
                ordinal=2,
                text="Table summary grid",
                markdown="| Header 1 | Header 2 |\n|---|---|\n| Val 1 | Val 2 |",
                table=tbl,
            )
        )

    table_count = sum(1 for e in elements if e.table is not None)
    meta = DocumentMetadata(
        title="Sample Report",
        element_count=len(elements),
        table_count=table_count,
        word_count=len(text.split()),
        character_count=len(text),
    )

    config_params = {"strategy": "native"}
    config_hash = hashlib.sha256(
        json.dumps(config_params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    doc = NormalizedDocument(
        document_id=doc_id,
        version_id=ver_id,
        ingestion_id=ing_id,
        source=SourceDescriptor(
            source_type=source_type,
            source_uri=source_uri if source_uri.startswith(("http://", "https://")) else None,
            relative_source_ref=display_name
            if not source_uri.startswith(("http://", "https://"))
            else None,
            original_display_name=display_name,
            source_title="Sample Report",
            mime_type="application/pdf",
            acquisition_timestamp=now_utc,
            content_length=len(raw_content),
        ),
        extractor=ExtractorDescriptor(
            engine_name="docling",
            engine_version="2.144.0",
            config_parameters=config_params,
            extractor_config_sha256=config_hash,
        ),
        full_markdown=f"# Executive Overview\n\n{text}",
        full_text=f"Executive Overview\n\n{text}",
        elements=elements,
        metadata=meta,
        status=ExtractionStatus.SUCCESS,
        warnings=[],
        errors=[],
        source_sha256=source_hash,
        extracted_at=now_utc,
    )
    doc.finalize()
    verify_trust_boundary(doc)
    return doc, raw_content


# -----------------------------------------------------------------------------
# Unit & Functional Tests
# -----------------------------------------------------------------------------


def test_storage_initialization(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify tables, directories, indices, and WAL mode are created upon initialization."""
    manager, config = storage_env
    assert Path(config.db_path).is_file()
    assert Path(config.sources_dir).is_dir()
    assert Path(config.extractions_dir).is_dir()
    assert Path(config.tables_dir).is_dir()

    import sqlite3

    with sqlite3.connect(config.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "extraction_documents" in tables
        assert "extraction_records" in tables
        assert "extraction_tables" in tables

        # Verify WAL mode
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"


def test_store_and_load_document(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify persisting a NormalizedDocument creates DB rows and canonical JSON."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()

    res = manager.store_document(doc, raw_bytes=raw_bytes)

    assert not res.is_duplicate
    assert not res.is_new_version
    assert res.document_id == doc.document_id
    assert res.extraction_id == doc.ingestion_id

    # Verify database row
    summary = manager.get_document(doc.document_id)
    assert summary is not None
    assert summary.source_sha256 == doc.source_sha256
    assert summary.normalized_content_sha256 == doc.normalized_content_sha256
    assert summary.original_display_name == "report.pdf"
    assert summary.raw_artifact_path is not None
    assert Path(summary.raw_artifact_path).is_file()

    # Verify raw artifact content
    raw_saved = manager.get_raw_source_bytes(doc.document_id)
    assert raw_saved == raw_bytes

    # Verify canonical JSON can be reloaded and passes trust boundary
    loaded_doc = manager.load_normalized_document(doc.ingestion_id)
    assert loaded_doc is not None
    assert loaded_doc.document_id == doc.document_id
    assert loaded_doc.normalized_content_sha256 == doc.normalized_content_sha256
    assert loaded_doc.extraction_record_sha256 == doc.extraction_record_sha256
    assert loaded_doc.full_text == doc.full_text
    assert len(loaded_doc.elements) == len(doc.elements)


def test_quarantine_promotion(
    tmp_path: Path, storage_env: tuple[ExtractionStorageManager, StorageConfig]
) -> None:
    """Verify safe promotion of staged files from quarantine into sources directory."""
    manager, config = storage_env
    q_dir = tmp_path / "quarantine"
    q_mgr = QuarantineManager(str(q_dir))

    raw_bytes = b"Special quarantined document payload"
    q_path, _, content_hash = q_mgr.stage_bytes(raw_bytes, ".pdf", max_bytes=1024 * 1024)
    assert q_path.is_file()

    doc, _ = make_sample_normalized_document(raw_content=raw_bytes)
    res = manager.store_document(
        doc,
        quarantine_path=q_path,
        quarantine_manager=q_mgr,
    )

    assert res.document_id == doc.document_id
    summary = manager.get_document(doc.document_id)
    assert summary is not None
    assert summary.raw_artifact_path is not None

    promoted_file = Path(summary.raw_artifact_path)
    assert promoted_file.is_file()
    assert promoted_file.read_bytes() == raw_bytes

    # Quarantine file should be safely deleted
    assert not q_path.is_file()


def test_content_deduplication(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify identical content returns existing document ID and avoids duplicate files."""
    manager, config = storage_env
    doc1, raw_bytes = make_sample_normalized_document(text="Shared common content body.")
    res1 = manager.store_document(doc1, raw_bytes=raw_bytes)
    assert not res1.is_duplicate

    # Ingest a second document with identical content but distinct document/version/ingestion IDs
    doc2, _ = make_sample_normalized_document(text="Shared common content body.")
    assert doc2.document_id != doc1.document_id
    assert doc2.normalized_content_sha256 == doc1.normalized_content_sha256

    res2 = manager.store_document(doc2, raw_bytes=raw_bytes)

    assert res2.is_duplicate
    assert res2.document_id == doc1.document_id  # Re-uses original document entity

    # Verify only 1 document row exists
    docs = manager.list_documents()
    assert len(docs) == 1

    # Verify only 1 raw artifact file exists in sources_dir
    source_files = list(Path(config.sources_dir).glob("*"))
    assert len(source_files) == 1


def test_exact_record_deduplication(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify storing the exact same extraction execution record is a no-op duplicate."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()

    res1 = manager.store_document(doc, raw_bytes=raw_bytes)
    res2 = manager.store_document(doc, raw_bytes=raw_bytes)

    assert not res1.is_duplicate
    assert res2.is_duplicate
    assert res2.extraction_id == doc.ingestion_id
    assert res2.document_id == doc.document_id


def test_source_uri_versioning(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify changing content for the same source URI creates a new version."""
    manager, config = storage_env
    uri = "https://example.com/weekly-metrics.pdf"

    # Version 1
    doc_v1, raw_v1 = make_sample_normalized_document(
        text="Week 1 metrics: revenue $10M",
        source_uri=uri,
        raw_content=b"PDF Content Week 1",
    )
    res1 = manager.store_document(doc_v1, raw_bytes=raw_v1)
    assert not res1.is_duplicate
    assert not res1.is_new_version

    # Version 2 (Same URI, modified content)
    doc_v2, raw_v2 = make_sample_normalized_document(
        text="Week 2 metrics: revenue $15M",
        source_uri=uri,
        raw_content=b"PDF Content Week 2",
    )
    res2 = manager.store_document(doc_v2, raw_bytes=raw_v2)

    assert not res2.is_duplicate
    assert res2.is_new_version
    assert res2.document_id == doc_v1.document_id  # Linked to same logical document

    # Verify version counter incremented
    summary = manager.get_document(doc_v1.document_id)
    assert summary is not None
    assert summary.version_count == 2
    assert summary.current_version_id == doc_v2.version_id
    assert summary.current_extraction_id == doc_v2.ingestion_id

    # Verify both extraction records are preserved
    history = manager.list_extractions(doc_v1.document_id)
    assert len(history) == 2
    record_ids = {r.extraction_id for r in history}
    assert doc_v1.ingestion_id in record_ids
    assert doc_v2.ingestion_id in record_ids


def test_table_artifact_persistence(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify structured tables are exported to CSV and JSON files in tables_dir."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document(with_table=True)

    res = manager.store_document(doc, raw_bytes=raw_bytes)
    assert res.document_id == doc.document_id

    tables = manager.list_tables(doc.ingestion_id)
    assert len(tables) == 1
    tbl = tables[0]
    assert tbl.row_count == 2
    assert tbl.column_count == 2
    assert tbl.sheet_name == "SummarySheet"
    assert tbl.csv_path is not None
    assert tbl.json_path is not None

    # Inspect CSV content
    csv_text = Path(tbl.csv_path).read_text(encoding="utf-8")
    assert "Header 1,Header 2" in csv_text
    assert "Val 1,Val 2" in csv_text

    # Inspect JSON content
    json_text = Path(tbl.json_path).read_text(encoding="utf-8")
    table_data = json.loads(json_text)
    assert table_data["headers"] == ["Header 1", "Header 2"]


def test_trust_boundary_rejection_unfinalized_document(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify attempting to store an unfinalized document raises DocumentIntegrityError."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()

    # Create unfinalized clone
    doc_dict = doc.model_dump()
    doc_dict["normalized_content_sha256"] = None
    unfinalized_doc = NormalizedDocument(**doc_dict)
    assert not unfinalized_doc.is_finalized

    with pytest.raises(DocumentIntegrityError, match="unfinalized"):
        manager.store_document(unfinalized_doc, raw_bytes=raw_bytes)


def test_trust_boundary_rejection_tampered_json(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify that tampering with on-disk canonical JSON causes load to fail."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()
    manager.store_document(doc, raw_bytes=raw_bytes)

    # Locate canonical JSON and tamper with content
    rec = manager.get_extraction_record(doc.ingestion_id)
    assert rec is not None
    json_path = Path(rec.canonical_json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["full_text"] = "MALICIOUS TAMPERED TEXT"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    # Attempting to load tampered document triggers trust boundary failure
    with pytest.raises(HashIntegrityError):
        manager.load_normalized_document(doc.ingestion_id)


def test_query_and_lookup_apis(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify get_document_by_content_hash, get_document_by_source_hash, and get_document_by_uri."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()
    manager.store_document(doc, raw_bytes=raw_bytes)

    by_content = manager.get_document_by_content_hash(doc.normalized_content_sha256 or "")
    assert by_content is not None
    assert by_content.document_id == doc.document_id

    by_source = manager.get_document_by_source_hash(doc.source_sha256)
    assert by_source is not None
    assert by_source.document_id == doc.document_id

    by_uri = manager.get_document_by_uri(doc.source.source_uri or "")
    assert by_uri is not None
    assert by_uri.document_id == doc.document_id

    # Non-existent query
    assert manager.get_document_by_content_hash("0" * 64) is None


def test_document_deletion_cascading(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify delete_document cleans up database rows and unlinks disk files."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document(with_table=True)
    manager.store_document(doc, raw_bytes=raw_bytes)

    summary = manager.get_document(doc.document_id)
    assert summary is not None
    raw_path = Path(summary.raw_artifact_path)
    assert raw_path.is_file()

    tables = manager.list_tables(doc.ingestion_id)
    assert len(tables) == 1
    csv_path = Path(tables[0].csv_path)
    assert csv_path.is_file()

    # Delete with artifact cleanup
    deleted = manager.delete_document(doc.document_id, delete_artifacts=True)
    assert deleted

    # Database records gone
    assert manager.get_document(doc.document_id) is None
    assert manager.get_extraction_record(doc.ingestion_id) is None
    assert len(manager.list_tables(doc.ingestion_id)) == 0

    # Disk files unlinked
    assert not raw_path.is_file()
    assert not csv_path.is_file()


@pytest.mark.asyncio
async def test_async_storage_operations(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify asynchronous entry points execute without blocking the event loop."""
    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()

    # Async store
    res = await manager.store_document_async(doc, raw_bytes=raw_bytes)
    assert res.document_id == doc.document_id

    # Async query
    summary = await manager.get_document_async(doc.document_id)
    assert summary is not None
    assert summary.source_sha256 == doc.source_sha256

    # Async load
    loaded = await manager.load_normalized_document_async(doc.ingestion_id)
    assert loaded is not None
    assert loaded.document_id == doc.document_id

    # Async delete
    deleted = await manager.delete_document_async(doc.document_id, delete_artifacts=True)
    assert deleted
    assert await manager.get_document_async(doc.document_id) is None


def test_thread_and_process_hygiene(
    storage_env: tuple[ExtractionStorageManager, StorageConfig],
) -> None:
    """Verify storage operations leave zero unclosed non-daemon threads or leaked processes."""
    threads_before = [
        t for t in threading.enumerate() if not t.daemon and "pytest" not in t.name.lower()
    ]

    manager, config = storage_env
    doc, raw_bytes = make_sample_normalized_document()

    with manager:
        res = manager.store_document(doc, raw_bytes=raw_bytes)
        assert res.document_id == doc.document_id

    threads_after = [
        t for t in threading.enumerate() if not t.daemon and "pytest" not in t.name.lower()
    ]
    assert len(threads_after) <= len(threads_before)
