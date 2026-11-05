"""Tests for document preview bounded offset pagination, duration, and timestamp mapping."""

from datetime import UTC, datetime

import pytest

from javed.extraction.schema import (
    DocumentMetadata,
    ExtractionStatus,
    ExtractorDescriptor,
    NormalizedDocument,
    SourceDescriptor,
    SourceType,
)
from javed.extraction.storage import (
    ExtractionStorageManager,
    StorageConfig,
    StoredExtractionRecord,
)


@pytest.fixture
def temp_storage(tmp_path):
    config = StorageConfig(
        db_path=str(tmp_path / "extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    storage = ExtractionStorageManager(config)
    storage.initialize()
    return storage


def test_stored_extraction_record_duration_and_timestamp():
    """Verify StoredExtractionRecord fields duration_ms and extraction_timestamp."""
    dt = datetime(2026, 11, 3, 13, 43, 5, tzinfo=UTC)
    rec = StoredExtractionRecord(
        extraction_id="ext-123",
        document_id="doc-456",
        version_id="ver-789",
        ingestion_id="ing-012",
        source_sha256="a" * 64,
        normalized_content_sha256="b" * 64,
        extraction_record_sha256="c" * 64,
        normalized_output_sha256="d" * 64,
        extracted_at=dt,
        extraction_timestamp=dt.isoformat(),
        duration_ms=842,
        status=ExtractionStatus.SUCCESS,
        extractor_name="docling",
        extractor_version="2.0.0",
        extractor_strategy="default",
        extractor_config_sha256="e" * 64,
        element_count=10,
        table_count=1,
    )
    assert rec.duration_ms == 842
    assert rec.extraction_timestamp == "2026-11-03T13:43:05+00:00"
    assert rec.status == ExtractionStatus.SUCCESS

    # Verify model_dump contains duration_ms and extraction_timestamp without raw paths
    dump = rec.model_dump(mode="json")
    assert dump["duration_ms"] == 842
    assert dump["extraction_timestamp"] == "2026-11-03T13:43:05+00:00"
    assert "raw_artifact_path" not in dump


def test_storage_preserves_duration_ms(temp_storage: ExtractionStorageManager):
    """Verify storage preserves duration_ms in SQLite extraction_records table."""
    now = datetime.now(UTC)
    doc = NormalizedDocument(
        document_id="doc-test-1",
        version_id="ver-1",
        ingestion_id="ing-1",
        source=SourceDescriptor(
            source_type=SourceType.PDF,
            original_display_name="test.pdf",
            relative_source_ref="test.pdf",
            mime_type="application/pdf",
            acquisition_timestamp=now,
            content_length=100,
        ),
        extractor=ExtractorDescriptor(
            engine_name="docling",
            engine_version="2.0.0",
            config_parameters={"duration_ms": 1250},
            extractor_config_sha256="f" * 64,
        ),
        full_text="Hello world " * 50,
        full_markdown="# Hello world\n\n" * 50,
        elements=[],
        metadata=DocumentMetadata(
            title="Test Doc",
            custom_attributes={"duration_ms": 1250},
        ),
        status=ExtractionStatus.SUCCESS,
        source_sha256="1" * 64,
        extracted_at=now,
    )
    doc.finalize()
    res = temp_storage.store_document(doc)
    assert res.document_id == "doc-test-1"

    extractions = temp_storage.list_extractions("doc-test-1")
    assert len(extractions) == 1
    assert extractions[0].duration_ms == 1250
    assert extractions[0].extraction_timestamp is not None
    assert extractions[0].extracted_at == now


@pytest.mark.asyncio
async def test_document_detail_offset_pagination(temp_storage: ExtractionStorageManager):
    """Verify offset pagination slices text and markdown previews with total char counts."""
    from javed.api.v1.extraction import get_document_details

    now = datetime.now(UTC)
    # Generate 1000 characters of text
    sample_text = "ABCDEFGHIJ" * 100  # 1000 chars
    sample_md = "# Title\n\n" + ("* List item\n" * 50)  # ~650 chars

    doc = NormalizedDocument(
        document_id="doc-paging-1",
        version_id="ver-paging-1",
        ingestion_id="ing-paging-1",
        source=SourceDescriptor(
            source_type=SourceType.PDF,
            original_display_name="pagedoc.pdf",
            relative_source_ref="pagedoc.pdf",
            mime_type="application/pdf",
            acquisition_timestamp=now,
            content_length=len(sample_text),
        ),
        extractor=ExtractorDescriptor(
            engine_name="docling",
            engine_version="2.0.0",
            config_parameters={"strategy": "default"},
            extractor_config_sha256="a" * 64,
        ),
        full_text=sample_text,
        full_markdown=sample_md,
        elements=[],
        metadata=DocumentMetadata(
            title="Page Doc",
            word_count=len(sample_text.split()),
            character_count=len(sample_text),
            custom_attributes={"duration_ms": 750},
        ),
        status=ExtractionStatus.SUCCESS,
        source_sha256="2" * 64,
        extracted_at=now,
    )
    doc.finalize()
    temp_storage.store_document(doc)

    # Page 1: offset=0, max_chars=200
    page1 = await get_document_details(
        document_id="doc-paging-1",
        storage=temp_storage,
        offset_chars=0,
        max_chars=200,
    )
    assert page1.offset_chars == 0
    assert page1.total_text_chars == 1000
    assert page1.total_markdown_chars == len(sample_md)
    assert len(page1.text_preview) == 200
    assert page1.text_preview == sample_text[:200]
    assert page1.is_truncated is True

    # Page 2: offset=200, max_chars=200
    page2 = await get_document_details(
        document_id="doc-paging-1",
        storage=temp_storage,
        offset_chars=200,
        max_chars=200,
    )
    assert page2.offset_chars == 200
    assert len(page2.text_preview) == 200
    assert page2.text_preview == sample_text[200:400]
    assert page2.is_truncated is True

    # Final slice: offset=900, max_chars=200
    page_last = await get_document_details(
        document_id="doc-paging-1",
        storage=temp_storage,
        offset_chars=900,
        max_chars=200,
    )
    assert page_last.offset_chars == 900
    assert len(page_last.text_preview) == 100  # only 100 chars left
    assert page_last.text_preview == sample_text[900:1000]

    # Verify duration and timestamp mapped in extractions list
    assert len(page1.extractions) == 1
    assert page1.extractions[0].duration_ms == 750
    assert page1.extractions[0].extraction_timestamp is not None
