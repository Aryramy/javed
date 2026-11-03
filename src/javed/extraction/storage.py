"""Storage Manager, Deduplication & Metadata Registry for BRICK-007 Phase 6.

Provides:
1. SQLite relational registry for canonical documents, extraction runs, and tables.
2. Cryptographic deduplication (source content SHA-256 and normalized content SHA-256).
3. Monotonic document versioning for evolving URLs and re-extracted sources.
4. Raw artifact retention and atomic promotion from quarantine staging.
5. Canonical NormalizedDocument JSON persistence with trust boundary validation.
6. Structured table exports (CSV and JSON).
7. Thread-safe synchronous and async-compatible SQLite access with WAL mode.
8. Zero process/thread leaks and strict idempotent teardown.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from pydantic import BaseModel, Field

from javed.extraction.schema import (
    ExtractionBaseModel,
    ExtractionError,
    ExtractionStatus,
    ExtractionWarning,
    HashIntegrityError,
    NormalizedDocument,
    SourceType,
    TableRepresentation,
    _deep_freeze_model,
    verify_trust_boundary,
)
from javed.extraction.security import QuarantineManager

logger = logging.getLogger("javed.extraction.storage")

# -----------------------------------------------------------------------------
# DDL Definitions
# -----------------------------------------------------------------------------

CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS extraction_documents (
    document_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_uri TEXT,
    relative_source_ref TEXT,
    original_display_name TEXT NOT NULL,
    source_title TEXT,
    mime_type TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    normalized_content_sha256 TEXT NOT NULL,
    first_ingested_at TEXT NOT NULL,
    last_ingested_at TEXT NOT NULL,
    version_count INTEGER NOT NULL DEFAULT 1,
    current_version_id TEXT NOT NULL,
    current_extraction_id TEXT NOT NULL,
    raw_artifact_path TEXT,
    metadata_json TEXT NOT NULL
);
"""

CREATE_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS extraction_records (
    extraction_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES extraction_documents(document_id) ON DELETE CASCADE,
    version_id TEXT NOT NULL,
    ingestion_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    normalized_content_sha256 TEXT NOT NULL,
    extraction_record_sha256 TEXT NOT NULL,
    normalized_output_sha256 TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    extractor_name TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    extractor_strategy TEXT NOT NULL,
    extractor_config_sha256 TEXT NOT NULL,
    element_count INTEGER NOT NULL,
    table_count INTEGER NOT NULL,
    word_count INTEGER,
    character_count INTEGER,
    page_count INTEGER,
    warning_count INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    canonical_json_path TEXT,
    full_text TEXT,
    full_markdown TEXT,
    warnings_json TEXT,
    errors_json TEXT
);
"""

CREATE_TABLES_TABLE = """
CREATE TABLE IF NOT EXISTS extraction_tables (
    table_id TEXT PRIMARY KEY,
    extraction_id TEXT NOT NULL REFERENCES extraction_records(extraction_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES extraction_documents(document_id) ON DELETE CASCADE,
    sheet_name TEXT,
    caption TEXT,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    csv_path TEXT,
    json_path TEXT
);
"""

CREATE_INDICES = """
CREATE INDEX IF NOT EXISTS idx_docs_source_hash ON extraction_documents(source_sha256);
CREATE INDEX IF NOT EXISTS idx_docs_content_hash ON extraction_documents(normalized_content_sha256);
CREATE INDEX IF NOT EXISTS idx_docs_source_uri ON extraction_documents(source_uri);
CREATE INDEX IF NOT EXISTS idx_records_doc_id ON extraction_records(document_id);
CREATE INDEX IF NOT EXISTS idx_records_exec_hash ON extraction_records(extraction_record_sha256);
CREATE INDEX IF NOT EXISTS idx_records_version ON extraction_records(version_id);
CREATE INDEX IF NOT EXISTS idx_records_ingestion ON extraction_records(ingestion_id);
CREATE INDEX IF NOT EXISTS idx_records_status ON extraction_records(status);
CREATE INDEX IF NOT EXISTS idx_tables_extraction ON extraction_tables(extraction_id);
"""


# -----------------------------------------------------------------------------
# Configuration & Exceptions
# -----------------------------------------------------------------------------


class StorageConfig(BaseModel):
    """Configuration for extraction storage, directories, and database settings."""

    db_path: str = Field(default="data/extraction.db")
    sources_dir: str = Field(default="data/sources")
    extractions_dir: str = Field(default="data/extractions")
    tables_dir: str = Field(default="data/tables")
    enable_wal: bool = Field(default=True)
    busy_timeout_ms: int = Field(default=5000)
    store_raw_artifacts: bool = Field(default=True)
    store_canonical_json: bool = Field(default=True)
    store_table_artifacts: bool = Field(default=True)


class ExtractionStorageError(Exception):
    """Base exception for extraction storage failures."""


class DocumentNotFoundError(ExtractionStorageError):
    """Raised when a requested document is not found."""


class DocumentIntegrityError(ExtractionStorageError):
    """Raised when trust boundary validation fails or stored data is tampered."""


class StorageCorruptionError(ExtractionStorageError):
    """Raised when storage artifacts or database records are corrupt."""


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------


class StoredDocumentSummary(ExtractionBaseModel):
    """Authoritative snapshot of a stored document entity."""

    document_id: str
    source_type: SourceType
    source_uri: str | None = None
    relative_source_ref: str | None = None
    original_display_name: str
    source_title: str | None = None
    mime_type: str
    source_sha256: str
    normalized_content_sha256: str
    first_ingested_at: datetime
    last_ingested_at: datetime
    version_count: int = 1
    current_version_id: str
    current_extraction_id: str
    artifact_available: bool = False
    artifact_id: str | None = None
    metadata_json: str
    element_count: int = 0
    table_count: int = 0


class StoredExtractionRecord(ExtractionBaseModel):
    """Detailed record of an individual extraction run."""

    extraction_id: str
    document_id: str
    version_id: str
    ingestion_id: str
    source_sha256: str
    normalized_content_sha256: str
    extraction_record_sha256: str
    normalized_output_sha256: str
    extracted_at: datetime
    status: ExtractionStatus
    extractor_name: str
    extractor_version: str
    extractor_strategy: str
    extractor_config_sha256: str
    element_count: int
    table_count: int
    word_count: int | None = None
    character_count: int | None = None
    page_count: int | None = None
    warning_count: int = 0
    error_count: int = 0
    canonical_json_available: bool = False
    canonical_json_id: str | None = None
    full_text: str | None = None
    full_markdown: str | None = None
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    errors: list[ExtractionError] = Field(default_factory=list)


class StoredTableInfo(ExtractionBaseModel):
    """Metadata describing an exported table artifact."""

    table_id: str
    extraction_id: str
    document_id: str
    sheet_name: str | None = None
    caption: str | None = None
    row_count: int
    column_count: int
    csv_available: bool = False
    json_available: bool = False


class IngestionResult(ExtractionBaseModel):
    """Outcome of storing a NormalizedDocument."""

    document_id: str
    extraction_id: str
    version_id: str
    ingestion_id: str
    is_duplicate: bool
    is_new_version: bool
    source_sha256: str
    normalized_content_sha256: str
    extraction_record_sha256: str
    stored_at: datetime
    document: NormalizedDocument


# -----------------------------------------------------------------------------
# Storage Manager Implementation
# -----------------------------------------------------------------------------


_DB_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCK_MUTEX = threading.Lock()


def _get_db_path_lock(db_path: Path) -> threading.Lock:
    """Retrieve or create a process-wide thread lock for a specific SQLite database path."""
    key = str(db_path.resolve())
    with _PATH_LOCK_MUTEX:
        if key not in _DB_PATH_LOCKS:
            _DB_PATH_LOCKS[key] = threading.Lock()
        return _DB_PATH_LOCKS[key]


class ExtractionStorageManager:
    """Manages persistent SQLite registry and canonical disk artifacts for extracted documents."""

    def __init__(self, config: StorageConfig | None = None) -> None:
        self.config = config or StorageConfig()
        self.db_path = Path(self.config.db_path).resolve()
        self.sources_dir = Path(self.config.sources_dir).resolve()
        self.extractions_dir = Path(self.config.extractions_dir).resolve()
        self.tables_dir = Path(self.config.tables_dir).resolve()
        self._is_initialized = False
        self._lock = asyncio.Lock()
        self._sync_init_lock = threading.Lock()
        self._closed = False

    def initialize(self) -> None:
        """Synchronously initialize storage directories and SQLite tables."""
        if self._is_initialized:
            return
        path_lock = _get_db_path_lock(self.db_path)
        with path_lock:
            if self._is_initialized:
                return
            self._ensure_directories()
            import sqlite3

            with sqlite3.connect(
                self.db_path, timeout=max(self.config.busy_timeout_ms / 1000.0, 10.0)
            ) as conn:
                conn.execute(f"PRAGMA busy_timeout = {max(self.config.busy_timeout_ms, 10000)};")
                if self.config.enable_wal:
                    conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute(CREATE_DOCUMENTS_TABLE)
                conn.execute(CREATE_RECORDS_TABLE)
                conn.execute(CREATE_TABLES_TABLE)
                conn.executescript(CREATE_INDICES)
                conn.commit()
            self._is_initialized = True

    async def initialize_async(self) -> None:
        """Asynchronously initialize storage directories and SQLite tables."""
        if self._is_initialized:
            return
        async with self._lock:
            if self._is_initialized:
                return
            self._ensure_directories()
            async with aiosqlite.connect(
                self.db_path, timeout=self.config.busy_timeout_ms / 1000.0
            ) as db:
                if self.config.enable_wal:
                    await db.execute("PRAGMA journal_mode = WAL;")
                await db.execute(f"PRAGMA busy_timeout = {self.config.busy_timeout_ms};")
                await db.execute(CREATE_DOCUMENTS_TABLE)
                await db.execute(CREATE_RECORDS_TABLE)
                await db.execute(CREATE_TABLES_TABLE)
                await db.executescript(CREATE_INDICES)
                await db.commit()
            self._is_initialized = True

    def _ensure_directories(self) -> None:
        """Create required directories safely."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.extractions_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        """Close storage resources."""
        self._closed = True

    async def close_async(self) -> None:
        """Asynchronously close storage resources."""
        self._closed = True

    def __enter__(self) -> ExtractionStorageManager:
        self.initialize()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> ExtractionStorageManager:
        await self.initialize_async()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close_async()

    # -------------------------------------------------------------------------
    # Core Document Storage & Deduplication
    # -------------------------------------------------------------------------

    def store_document(
        self,
        document: NormalizedDocument,
        *,
        raw_bytes: bytes | None = None,
        quarantine_path: str | Path | None = None,
        quarantine_manager: QuarantineManager | None = None,
    ) -> IngestionResult:
        """Synchronously persist a finalized NormalizedDocument."""
        self.initialize()
        self._verify_document_contract(document)

        import sqlite3

        with sqlite3.connect(self.db_path, timeout=self.config.busy_timeout_ms / 1000.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Check exact execution record duplicate
            cursor.execute(
                "SELECT extraction_id, document_id FROM extraction_records "
                "WHERE extraction_record_sha256 = ?",
                (document.extraction_record_sha256,),
            )
            existing_rec = cursor.fetchone()
            if existing_rec:
                logger.info(
                    "Exact extraction record duplicate detected: %s",
                    document.extraction_record_sha256,
                )
                return IngestionResult(
                    document_id=existing_rec["document_id"],
                    extraction_id=existing_rec["extraction_id"],
                    version_id=document.version_id,
                    ingestion_id=document.ingestion_id,
                    is_duplicate=True,
                    is_new_version=False,
                    source_sha256=document.source_sha256,
                    normalized_content_sha256=document.normalized_content_sha256 or "",
                    extraction_record_sha256=document.extraction_record_sha256 or "",
                    stored_at=datetime.now(UTC),
                    document=document,
                )

            # 2. Check content duplicate by normalized_content_sha256 or source_sha256
            cursor.execute(
                "SELECT * FROM extraction_documents WHERE normalized_content_sha256 = ? "
                "OR source_sha256 = ?",
                (document.normalized_content_sha256, document.source_sha256),
            )
            existing_doc = cursor.fetchone()

            # 3. Check versioning by source_uri (same URI, different content)
            cursor.execute(
                "SELECT * FROM extraction_documents WHERE source_uri IS NOT NULL "
                "AND source_uri = ? AND source_sha256 != ?",
                (document.source.source_uri, document.source_sha256),
            )
            version_doc = cursor.fetchone()

            is_duplicate = existing_doc is not None
            is_new_version = not is_duplicate and version_doc is not None

            # Handle raw artifact promotion / persistence
            raw_artifact_path: str | None = None
            if self.config.store_raw_artifacts:
                raw_artifact_path = self._persist_raw_source(
                    source_sha256=document.source_sha256,
                    source_type=document.source.source_type,
                    raw_bytes=raw_bytes,
                    quarantine_path=quarantine_path,
                    quarantine_manager=quarantine_manager,
                )

            # Handle canonical JSON persistence
            canonical_json_path: str | None = None
            if self.config.store_canonical_json:
                canonical_json_path = self._persist_canonical_json(document)

            now_iso = datetime.now(UTC).isoformat()
            target_doc_id = document.document_id
            target_version_id = document.version_id

            if is_duplicate and existing_doc:
                target_doc_id = existing_doc["document_id"]
                # Update last ingested timestamp on existing document
                cursor.execute(
                    "UPDATE extraction_documents SET last_ingested_at = ? WHERE document_id = ?",
                    (now_iso, target_doc_id),
                )
            elif is_new_version and version_doc:
                target_doc_id = version_doc["document_id"]
                new_version_count = version_doc["version_count"] + 1
                cursor.execute(
                    "UPDATE extraction_documents SET "
                    "source_sha256 = ?, "
                    "normalized_content_sha256 = ?, "
                    "last_ingested_at = ?, "
                    "version_count = ?, "
                    "current_version_id = ?, "
                    "current_extraction_id = ?, "
                    "raw_artifact_path = COALESCE(?, raw_artifact_path), "
                    "metadata_json = ? "
                    "WHERE document_id = ?",
                    (
                        document.source_sha256,
                        document.normalized_content_sha256,
                        now_iso,
                        new_version_count,
                        target_version_id,
                        document.ingestion_id,
                        raw_artifact_path,
                        document.metadata.model_dump_json(),
                        target_doc_id,
                    ),
                )
            else:
                # Completely new document
                cursor.execute(
                    "INSERT INTO extraction_documents ("
                    "document_id, source_type, source_uri, relative_source_ref, "
                    "original_display_name, source_title, mime_type, source_sha256, "
                    "normalized_content_sha256, first_ingested_at, last_ingested_at, "
                    "version_count, current_version_id, current_extraction_id, "
                    "raw_artifact_path, metadata_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        target_doc_id,
                        document.source.source_type.value,
                        document.source.source_uri,
                        document.source.relative_source_ref,
                        document.source.original_display_name,
                        document.source.source_title,
                        document.source.mime_type,
                        document.source_sha256,
                        document.normalized_content_sha256,
                        now_iso,
                        now_iso,
                        1,
                        target_version_id,
                        document.ingestion_id,
                        raw_artifact_path,
                        document.metadata.model_dump_json(),
                    ),
                )

            # Insert extraction record
            cursor.execute(
                "INSERT INTO extraction_records ("
                "extraction_id, document_id, version_id, ingestion_id, "
                "source_sha256, normalized_content_sha256, extraction_record_sha256, "
                "normalized_output_sha256, extracted_at, status, extractor_name, "
                "extractor_version, extractor_strategy, extractor_config_sha256, "
                "element_count, table_count, word_count, character_count, "
                "page_count, warning_count, error_count, canonical_json_path, "
                "full_text, full_markdown, warnings_json, errors_json"
                ") VALUES ("
                "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
                ")",
                (
                    document.ingestion_id,
                    target_doc_id,
                    target_version_id,
                    document.ingestion_id,
                    document.source_sha256,
                    document.normalized_content_sha256,
                    document.extraction_record_sha256,
                    document.normalized_output_sha256,
                    document.extracted_at.isoformat(),
                    document.status.value,
                    document.extractor.engine_name,
                    document.extractor.engine_version,
                    document.extractor.config_parameters.get("strategy", "default"),
                    document.extractor.extractor_config_sha256,
                    len(document.elements),
                    sum(1 for e in document.elements if e.table is not None),
                    document.metadata.word_count,
                    document.metadata.character_count,
                    document.metadata.page_count,
                    len(document.warnings),
                    len(document.errors),
                    canonical_json_path,
                    document.full_text,
                    document.full_markdown,
                    json.dumps([w.model_dump(mode="json") for w in document.warnings]),
                    json.dumps([err.model_dump(mode="json") for err in document.errors]),
                ),
            )

            # Export table artifacts
            if self.config.store_table_artifacts:
                for idx, elem in enumerate(document.elements):
                    if elem.table is not None:
                        self._persist_table_artifacts(
                            cursor=cursor,
                            document_id=target_doc_id,
                            extraction_id=document.ingestion_id,
                            table=elem.table,
                            table_index=idx,
                        )

            conn.commit()

        return IngestionResult(
            document_id=target_doc_id,
            extraction_id=document.ingestion_id,
            version_id=target_version_id,
            ingestion_id=document.ingestion_id,
            is_duplicate=is_duplicate,
            is_new_version=is_new_version,
            source_sha256=document.source_sha256,
            normalized_content_sha256=document.normalized_content_sha256 or "",
            extraction_record_sha256=document.extraction_record_sha256 or "",
            stored_at=datetime.now(UTC),
            document=document,
        )

    async def store_document_async(
        self,
        document: NormalizedDocument,
        *,
        raw_bytes: bytes | None = None,
        quarantine_path: str | Path | None = None,
        quarantine_manager: QuarantineManager | None = None,
    ) -> IngestionResult:
        """Asynchronously persist a finalized NormalizedDocument."""
        await self.initialize_async()
        return await asyncio.to_thread(
            self.store_document,
            document,
            raw_bytes=raw_bytes,
            quarantine_path=quarantine_path,
            quarantine_manager=quarantine_manager,
        )

    # -------------------------------------------------------------------------
    # Retrieval & Query APIs
    # -------------------------------------------------------------------------

    def get_document(self, document_id: str) -> StoredDocumentSummary | None:
        """Retrieve authoritative metadata summary for a document."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT d.*, "
                "(SELECT COUNT(*) FROM extraction_records WHERE document_id = d.document_id) "
                "AS total_runs "
                "FROM extraction_documents d WHERE d.document_id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_document_summary(row)

    async def get_document_async(self, document_id: str) -> StoredDocumentSummary | None:
        """Asynchronously retrieve document summary."""
        await self.initialize_async()
        return await asyncio.to_thread(self.get_document, document_id)

    def get_document_by_content_hash(
        self, normalized_content_sha256: str
    ) -> StoredDocumentSummary | None:
        """Lookup document by canonical normalized content SHA-256."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_documents WHERE normalized_content_sha256 = ?",
                (normalized_content_sha256,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_document_summary(row)

    def get_document_by_source_hash(self, source_sha256: str) -> StoredDocumentSummary | None:
        """Lookup document by raw source SHA-256."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_documents WHERE source_sha256 = ?",
                (source_sha256,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_document_summary(row)

    def get_document_by_uri(self, source_uri: str) -> StoredDocumentSummary | None:
        """Lookup document by original source URI."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_documents WHERE source_uri = ?",
                (source_uri,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_document_summary(row)

    def get_extraction_record(self, extraction_id: str) -> StoredExtractionRecord | None:
        """Retrieve execution telemetry for an extraction run."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_records WHERE extraction_id = ?",
                (extraction_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_extraction_record(row)

    def load_normalized_document(self, extraction_id: str) -> NormalizedDocument | None:
        """Load and verify a stored NormalizedDocument from its canonical JSON artifact."""
        self.initialize()
        p = self.get_canonical_json_path(extraction_id)
        if not p or not p.is_file():
            return None

        record = self.get_extraction_record(extraction_id)
        if not record:
            return None

        raw_json = p.read_text(encoding="utf-8")
        try:
            data = json.loads(raw_json)
            doc = NormalizedDocument(**data)
        except Exception as e:
            raise HashIntegrityError(
                f"Failed to load or validate canonical extraction JSON: {e}"
            ) from e

        if record.extraction_record_sha256 != doc.extraction_record_sha256:
            raise HashIntegrityError(
                f"Stored record hash '{record.extraction_record_sha256}' does not match "
                f"loaded document hash '{doc.extraction_record_sha256}'"
            )

        # Freeze deserialized model into immutable graph and enforce trust boundary
        _deep_freeze_model(doc)
        verify_trust_boundary(doc)
        return doc

    async def load_normalized_document_async(self, extraction_id: str) -> NormalizedDocument | None:
        """Asynchronously load and verify a stored NormalizedDocument."""
        await self.initialize_async()
        return await asyncio.to_thread(self.load_normalized_document, extraction_id)

    def list_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        source_type: SourceType | None = None,
    ) -> list[StoredDocumentSummary]:
        """List stored documents ordered by last ingested timestamp."""
        self.initialize()
        import sqlite3

        query = "SELECT * FROM extraction_documents"
        params: list[Any] = []
        if source_type:
            query += " WHERE source_type = ?"
            params.append(source_type.value)
        query += " ORDER BY last_ingested_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_document_summary(r) for r in rows]

    async def list_documents_async(
        self,
        limit: int = 50,
        offset: int = 0,
        source_type: SourceType | None = None,
    ) -> list[StoredDocumentSummary]:
        """List stored documents asynchronously ordered by last ingested timestamp."""
        return await asyncio.to_thread(
            self.list_documents,
            limit=limit,
            offset=offset,
            source_type=source_type,
        )

    def list_extractions(self, document_id: str) -> list[StoredExtractionRecord]:
        """List all extraction runs for a document ordered chronologically."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_records WHERE document_id = ? ORDER BY extracted_at DESC",
                (document_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_extraction_record(r) for r in rows]

    async def list_extractions_async(self, document_id: str) -> list[StoredExtractionRecord]:
        """Asynchronously list all extraction runs for a document."""
        return await asyncio.to_thread(self.list_extractions, document_id)

    def list_tables(self, identifier: str) -> list[StoredTableInfo]:
        """List exported tables for an extraction run or document."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_tables WHERE extraction_id = ? OR document_id = ?",
                (identifier, identifier),
            )
            rows = cursor.fetchall()
            return [
                StoredTableInfo(
                    table_id=r["table_id"],
                    extraction_id=r["extraction_id"],
                    document_id=r["document_id"],
                    sheet_name=r["sheet_name"],
                    caption=r["caption"],
                    row_count=r["row_count"],
                    column_count=r["column_count"],
                    csv_available=bool(r["csv_path"] and Path(r["csv_path"]).is_file()),
                    json_available=bool(r["json_path"] and Path(r["json_path"]).is_file()),
                )
                for r in rows
            ]

    async def list_tables_async(self, identifier: str) -> list[StoredTableInfo]:
        """Asynchronously list exported tables for an extraction run or document."""
        return await asyncio.to_thread(self.list_tables, identifier)

    def get_table(self, table_id: str) -> StoredTableInfo | None:
        """Retrieve stored table metadata by table_id."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM extraction_tables WHERE table_id = ?",
                (table_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return StoredTableInfo(
                table_id=row["table_id"],
                extraction_id=row["extraction_id"],
                document_id=row["document_id"],
                sheet_name=row["sheet_name"],
                caption=row["caption"],
                row_count=row["row_count"],
                column_count=row["column_count"],
                csv_available=bool(row["csv_path"] and Path(row["csv_path"]).is_file()),
                json_available=bool(row["json_path"] and Path(row["json_path"]).is_file()),
            )

    async def get_table_async(self, table_id: str) -> StoredTableInfo | None:
        """Asynchronously retrieve stored table metadata by table_id."""
        return await asyncio.to_thread(self.get_table, table_id)

    def count_documents(self, source_type: SourceType | None = None) -> int:
        """Count total stored documents matching optional source_type filter."""
        self.initialize()
        import sqlite3

        query = "SELECT COUNT(*) FROM extraction_documents"
        params: list[Any] = []
        if source_type:
            query += " WHERE source_type = ?"
            params.append(source_type.value)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return int(cursor.fetchone()[0])

    async def count_documents_async(self, source_type: SourceType | None = None) -> int:
        """Asynchronously count total stored documents."""
        return await asyncio.to_thread(self.count_documents, source_type)

    def count_extractions(self) -> int:
        """Count total extraction runs."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM extraction_records")
            return int(cursor.fetchone()[0])

    async def count_extractions_async(self) -> int:
        """Asynchronously count total extraction runs."""
        return await asyncio.to_thread(self.count_extractions)

    def count_tables(self) -> int:
        """Count total extracted table records."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM extraction_tables")
            return int(cursor.fetchone()[0])

    async def count_tables_async(self) -> int:
        """Asynchronously count total extracted tables."""
        return await asyncio.to_thread(self.count_tables)

    def get_raw_artifact_path(self, document_id: str) -> Path | None:
        """Internal lookup for raw artifact path on filesystem."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT raw_artifact_path FROM extraction_documents WHERE document_id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            if not row or not row["raw_artifact_path"]:
                return None
            p = Path(row["raw_artifact_path"])
            return p if p.is_file() else None

    def get_canonical_json_path(self, extraction_id: str) -> Path | None:
        """Internal lookup for canonical JSON artifact path on filesystem."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT canonical_json_path FROM extraction_records WHERE extraction_id = ?",
                (extraction_id,),
            )
            row = cursor.fetchone()
            if not row or not row["canonical_json_path"]:
                return None
            p = Path(row["canonical_json_path"])
            return p if p.is_file() else None

    def get_table_artifact_path(self, table_id: str, format: str = "json") -> Path | None:
        """Internal lookup for table CSV or JSON artifact path on filesystem."""
        self.initialize()
        import sqlite3

        col = "csv_path" if format.lower() == "csv" else "json_path"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {col} FROM extraction_tables WHERE table_id = ?",
                (table_id,),
            )
            row = cursor.fetchone()
            if not row or not row[col]:
                return None
            p = Path(row[col])
            return p if p.is_file() else None

    def get_raw_source_bytes(self, document_id: str) -> bytes | None:
        """Retrieve raw canonical source bytes for a document."""
        p = self.get_raw_artifact_path(document_id)
        if not p or not p.is_file():
            return None
        return p.read_bytes()

    def delete_document(self, document_id: str, delete_artifacts: bool = True) -> bool:
        """Delete a document, its extraction records, and optionally disk artifacts."""
        self.initialize()
        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM extraction_documents WHERE document_id = ?",
                (document_id,),
            )
            doc_row = cursor.fetchone()
            if not doc_row:
                return False

            if delete_artifacts:
                # 1. Delete raw source artifact
                if doc_row["raw_artifact_path"]:
                    p_raw = Path(doc_row["raw_artifact_path"])
                    if p_raw.is_file():
                        try:
                            p_raw.unlink(missing_ok=True)
                        except Exception as e:
                            logger.warning("Failed to unlink raw source %s: %s", p_raw, e)

                # 2. Delete canonical JSON artifacts and tables
                cursor.execute(
                    "SELECT canonical_json_path FROM extraction_records WHERE document_id = ?",
                    (document_id,),
                )
                rec_rows = cursor.fetchall()
                for rec in rec_rows:
                    if rec["canonical_json_path"]:
                        p_json = Path(rec["canonical_json_path"])
                        if p_json.is_file():
                            try:
                                p_json.unlink(missing_ok=True)
                            except Exception as e:
                                logger.warning("Failed to unlink canonical JSON %s: %s", p_json, e)

                cursor.execute(
                    "SELECT csv_path, json_path FROM extraction_tables WHERE document_id = ?",
                    (document_id,),
                )
                tbl_rows = cursor.fetchall()
                for tbl in tbl_rows:
                    for key in ("csv_path", "json_path"):
                        if tbl[key]:
                            p_tbl = Path(tbl[key])
                            if p_tbl.is_file():
                                try:
                                    p_tbl.unlink(missing_ok=True)
                                except Exception as e:
                                    logger.warning("Failed to unlink table file %s: %s", p_tbl, e)

            # Delete cascades from documents -> records -> tables
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("DELETE FROM extraction_documents WHERE document_id = ?", (document_id,))
            conn.commit()
            return True

    async def delete_document_async(self, document_id: str, delete_artifacts: bool = True) -> bool:
        """Asynchronously delete document and records."""
        await self.initialize_async()
        return await asyncio.to_thread(self.delete_document, document_id, delete_artifacts)

    # -------------------------------------------------------------------------
    # Internal Helpers & Artifact Persistence
    # -------------------------------------------------------------------------

    def _verify_document_contract(self, doc: NormalizedDocument) -> None:
        """Enforce strict trust boundary before persistence."""
        if not doc.is_finalized:
            raise DocumentIntegrityError("Cannot store unfinalized NormalizedDocument")
        try:
            verify_trust_boundary(doc)
        except Exception as e:
            raise DocumentIntegrityError(f"Trust boundary verification failed: {e}") from e

    def _persist_raw_source(
        self,
        *,
        source_sha256: str,
        source_type: SourceType,
        raw_bytes: bytes | None,
        quarantine_path: str | Path | None,
        quarantine_manager: QuarantineManager | None,
    ) -> str | None:
        """Atomically persist raw source content to sources_dir avoiding duplicates."""
        ext = f".{source_type.value}" if source_type != SourceType.WEB_PAGE else ".html"
        target_path = self.sources_dir / f"{source_sha256}{ext}"

        if target_path.is_file():
            # Already exists (content deduplicated)
            if quarantine_path and quarantine_manager:
                quarantine_manager.cleanup(quarantine_path)
            return str(target_path)

        # 1. Promote from quarantine if available
        if quarantine_path and Path(quarantine_path).is_file():
            q_p = Path(quarantine_path).resolve()
            tmp_target = self.sources_dir / f"{source_sha256}.tmp"
            try:
                # Copy or rename to temporary file in sources_dir then replace
                with open(q_p, "rb") as src, open(tmp_target, "wb") as dst:
                    while chunk := src.read(65536):
                        dst.write(chunk)
                os.replace(tmp_target, target_path)
                if quarantine_manager:
                    quarantine_manager.cleanup(quarantine_path)
                return str(target_path)
            except Exception as e:
                if tmp_target.is_file():
                    tmp_target.unlink(missing_ok=True)
                logger.error("Failed promoting quarantine file %s: %s", quarantine_path, e)

        # 2. Write raw bytes if provided
        if raw_bytes is not None:
            tmp_target = self.sources_dir / f"{source_sha256}.tmp"
            try:
                with open(tmp_target, "wb") as f:
                    f.write(raw_bytes)
                os.replace(tmp_target, target_path)
                return str(target_path)
            except Exception as e:
                if tmp_target.is_file():
                    tmp_target.unlink(missing_ok=True)
                logger.error("Failed persisting raw bytes for %s: %s", source_sha256, e)

        return None

    def _persist_canonical_json(self, doc: NormalizedDocument) -> str:
        """Atomically persist canonical deterministic NormalizedDocument JSON."""
        record_hash = doc.extraction_record_sha256 or doc.compute_record_sha256()
        target_path = self.extractions_dir / f"{record_hash}.json"

        if target_path.is_file():
            return str(target_path)

        tmp_path = self.extractions_dir / f"{record_hash}.tmp"
        canonical_json = doc.model_dump_json(indent=2)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(canonical_json)
            os.replace(tmp_path, target_path)
            return str(target_path)
        except Exception as e:
            if tmp_path.is_file():
                tmp_path.unlink(missing_ok=True)
            raise StorageCorruptionError(f"Failed writing canonical JSON: {e}") from e

    def _persist_table_artifacts(
        self,
        *,
        cursor: Any,
        document_id: str,
        extraction_id: str,
        table: TableRepresentation,
        table_index: int,
    ) -> None:
        """Export table to CSV and JSON files and record in database."""
        table_id = f"{extraction_id}_tbl_{table_index + 1}"
        csv_file = self.tables_dir / f"{table_id}.csv"
        json_file = self.tables_dir / f"{table_id}.json"

        # 1. Export CSV
        try:
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            if table.headers:
                writer.writerow(table.headers)
            for row in table.rows:
                writer.writerow([getattr(c, "text", str(c)) for c in row])
            csv_file.write_text(buf.getvalue(), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed exporting table CSV for %s: %s", table_id, e)

        # 2. Export JSON
        try:
            table_dict = table.model_dump(mode="json")
            json_file.write_text(
                json.dumps(table_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed exporting table JSON for %s: %s", table_id, e)

        cursor.execute(
            "INSERT OR REPLACE INTO extraction_tables ("
            "table_id, extraction_id, document_id, sheet_name, caption, "
            "row_count, column_count, csv_path, json_path"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                table_id,
                extraction_id,
                document_id,
                table.sheet_name,
                table.caption,
                table.row_count,
                table.column_count,
                str(csv_file) if csv_file.is_file() else None,
                str(json_file) if json_file.is_file() else None,
            ),
        )

    def _row_to_document_summary(self, row: Any) -> StoredDocumentSummary:
        """Convert SQLite row to StoredDocumentSummary with safe opaque artifact metadata."""
        raw_p = row["raw_artifact_path"] if "raw_artifact_path" in row.keys() else None
        artifact_avail = bool(raw_p and Path(raw_p).is_file())
        artifact_id_val = str(row["source_sha256"]) if artifact_avail else None

        return StoredDocumentSummary(
            document_id=row["document_id"],
            source_type=SourceType(row["source_type"]),
            source_uri=row["source_uri"],
            relative_source_ref=row["relative_source_ref"],
            original_display_name=row["original_display_name"],
            source_title=row["source_title"],
            mime_type=row["mime_type"],
            source_sha256=row["source_sha256"],
            normalized_content_sha256=row["normalized_content_sha256"],
            first_ingested_at=datetime.fromisoformat(row["first_ingested_at"]),
            last_ingested_at=datetime.fromisoformat(row["last_ingested_at"]),
            version_count=row["version_count"],
            current_version_id=row["current_version_id"],
            current_extraction_id=row["current_extraction_id"],
            artifact_available=artifact_avail,
            artifact_id=artifact_id_val,
            metadata_json=row["metadata_json"],
        )

    def _row_to_extraction_record(self, row: Any) -> StoredExtractionRecord:
        """Convert SQLite row to StoredExtractionRecord with safe opaque artifact metadata."""
        raw_warn = row["warnings_json"]
        warnings = [ExtractionWarning(**w) for w in json.loads(raw_warn)] if raw_warn else []
        raw_err = row["errors_json"]
        errors = [ExtractionError(**e) for e in json.loads(raw_err)] if raw_err else []

        canon_p = row["canonical_json_path"] if "canonical_json_path" in row.keys() else None
        canon_avail = bool(canon_p and Path(canon_p).is_file())
        canon_id_val = str(row["extraction_record_sha256"]) if canon_avail else None

        return StoredExtractionRecord(
            extraction_id=row["extraction_id"],
            document_id=row["document_id"],
            version_id=row["version_id"],
            ingestion_id=row["ingestion_id"],
            source_sha256=row["source_sha256"],
            normalized_content_sha256=row["normalized_content_sha256"],
            extraction_record_sha256=row["extraction_record_sha256"],
            normalized_output_sha256=row["normalized_output_sha256"],
            extracted_at=datetime.fromisoformat(row["extracted_at"]),
            status=ExtractionStatus(row["status"]),
            extractor_name=row["extractor_name"],
            extractor_version=row["extractor_version"],
            extractor_strategy=row["extractor_strategy"],
            extractor_config_sha256=row["extractor_config_sha256"],
            element_count=row["element_count"],
            table_count=row["table_count"],
            word_count=row["word_count"],
            character_count=row["character_count"],
            page_count=row["page_count"],
            warning_count=row["warning_count"],
            error_count=row["error_count"],
            canonical_json_available=canon_avail,
            canonical_json_id=canon_id_val,
            full_text=row["full_text"],
            full_markdown=row["full_markdown"],
            warnings=warnings,
            errors=errors,
        )
