# BRICK-007: Crawl4AI & Docling Extraction Pipeline

> **Brick ID**: `BRICK-007`<br/>
> **Title**: Crawl4AI & Docling Extraction Pipeline<br/>
> **Status**: `IN PROGRESS` (Phase 0 Preflight & Architecture Completed; Awaiting Phase 1 Authorization)<br/>
> **Author**: Antigravity Full-Stack AI Engineering Team<br/>
> **Date**: 2026-10-29<br/>
> **Baseline Anchor**: Commit `83cdeeac0db71a646cb06c906d59e14e55a56c00` (Verified BRICK-006 synchronized on `master`)<br/>
> **Working Branch**: `feat/brick-007-extraction`<br/>
> **Target Subsystems**: `src/javed/extraction/`, `src/javed/api/v1/extraction.py`, `frontend/src/components/extraction/`

---

## 1. Executive Summary & Objective

**BRICK-007** establishes the foundational content ingestion and extraction engine for Project Javed (JARVIS). It transforms heterogeneous unstructured data sources into high-fidelity, structured, and normalized intermediate representations suitable for agent reasoning, analysis, and downstream persistent memory (BRICK-009).

In accordance with **Rule 1 (FOSS-First & Model-Agnostic Foundation)**, **Rule 2 (Scope Discipline & Anti-Bloat Guardrail)**, and [ADR-006](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-006.md), BRICK-007 implements a dual-engine architecture:
1. **Crawl4AI Web Extraction Subsystem**: Asynchronous, high-performance web crawler optimized for AI agents, executing headless Chromium rendering, dynamic SPA execution, boilerplate stripping, and clean semantic Markdown generation.
2. **Docling Document Understanding Subsystem**: Open-source, local-first multimodal document converter (developed by IBM Research) specialized in deep layout analysis, multi-column reading order reconstruction, structured table parsing (retaining grids, headers, and cell relationships), and precise page/bounding-box provenance tracking for PDF, DOCX, and XLSX formats.

### Core Architectural Invariants:
- **100% Local Processing**: All document parsing (PDF, Word, Excel) occurs strictly in-process on the local workstation. Document bytes never leave the machine.
- **Fail-Closed Defensive Security**: Strict validation on file sizes, page counts, MIME magic bytes, archive expansion blocking, path traversal prevention, and pre-crawl SSRF IP gating (`BrowserSecurityGuard`).
- **Normalized Extraction Schema**: All web and document extractions map into a single canonical Pydantic model (`NormalizedDocument`) with element-level provenance, structured tables, and content hashes.
- **Strict Separation from RAG**: BRICK-007 is strictly an *extraction and normalization* pipeline. Text chunking, tokenization, embeddings calculation, and vector indexing are explicitly deferred to **BRICK-009 (Persistent Memory & Semantic RAG)**.

---

## 2. Technology Audit & Dependency Compatibility Evaluation

### 2.1 Python Environment & Package Compatibility
During Phase 0 preflight, dependency resolution was simulated against the active `.venv` runtime using `uv pip compile`:
- **Python Version**: Python 3.12.15 (Windows x86_64). Both `crawl4ai` (0.9.5) and `docling` (2.144.0) natively support Python 3.12.
- **Dependency Resolution**: Resolved 153 packages in 3.75s with zero dependency conflicts against the existing baseline:
  - `pydantic`: Resolves to Pydantic v2 (v2.12.5 / v2.14.1), Dependency-resolution compatible, pending installation, import, runtime, and teardown verification.
  - `playwright`: Crawl4AI shares `playwright>=1.40.0` (v1.64.1 already verified in BRICK-006).
  - `pypdfium2`: Bundles precompiled PDFium C++ binaries for `win_amd64` (zero external PDF binaries needed).
  - `rapidocr` & `opencv-python-headless`: Provides precompiled Windows wheels for local OCR fallback.
  - `python-docx` & `openpyxl`: Pure-Python parsers for Word and Excel without deep learning overhead.
  - `torch`: PyTorch 2.15.0 was reported during candidate resolution. Because PyTorch 2.15.0 may originate from a prerelease or test package channel, Phase 1 must audit package indices, reject prereleases, and require verified stable CPU wheels (e.g. PyTorch stable 2.5.x/2.6.x or standard PyPI distribution).

### 2.2 System & Hardware Resource Profile
| Subsystem | CPU Impact | Memory Footprint | Disk Storage | Network Behavior |
|---|---|---|---|---|
| **Crawl4AI** | Low-Moderate (Chromium page render) | ~150–300 MB per active tab | Minimal cache | Network-dependent (requires live URL fetch) |
| **Docling (DOCX / XLSX)** | Low (Pure Python parser) | < 150 MB RAM | Minimal | 100% Offline |
| **Docling (Text PDF)** | Moderate (PDFium layout parse) | ~200–400 MB RAM | Minimal | 100% Offline |
| **Docling (Complex Layout / TableFormer)** | High during inference (1–4s per page) | ~1.5–2.5 GB RAM | ~1.2 GB model weights in HF cache | Offline after initial model weight download |

### 2.3 Air-Gapped / Offline Resilience Strategy
- Docling vision models download once from HuggingFace to `%USERPROFILE%/.cache/huggingface/hub`.
- If network access is disabled or HuggingFace is unreachable:
  - The intended lightweight PDF configuration is `PdfFormatOption` plus `PyPdfiumDocumentBackend` with model-backed OCR, layout, table, formula, and picture stages disabled where supported, allowing lightweight text and table extraction without large model downloads.
  - DOCX, XLSX, and plain text processing remain 100% functional without external network connectivity.

---

## 3. Subsystem Architecture & Responsibility Boundaries

```mermaid
flowchart TD
    subgraph InputSources ["Ingestion Sources"]
        URL["Web URL (http/https)"]
        DOC["Local / Uploaded File (.pdf, .docx, .xlsx, .txt)"]
    end

    subgraph SecurityGate ["Security & Validation Layer (src/javed/extraction/security.py)"]
        SSRF["SSRF & IP Guard<br/>(BrowserSecurityGuard)"]
        QUAR["Upload Quarantine & Validation<br/>- File Size (< 25 MB)<br/>- Page Count (< 200)<br/>- MIME Magic Byte Whitelist<br/>- Path Traversal Blocker"]
    end

    subgraph ExtractionEngines ["Extraction Engines (src/javed/extraction/)"]
        CRAWL["Crawl4AI Web Engine<br/>- Headless Chromium<br/>- DOM Boilerplate Stripping<br/>- Clean Markdown Output"]
        DOCLING["Docling Document Engine<br/>- PDF Layout & TableFormer<br/>- DOCX Section Parser<br/>- XLSX Multi-Sheet Grid Parser"]
    end

    subgraph Normalization ["Normalization & Storage (Proposed Phase 2/6: schema.py & storage.py)"]
        NORM["NormalizedDocument Pydantic Model<br/>- document_id & source_uri<br/>- content_hash (SHA-256)<br/>- elements: headings, paragraphs, tables<br/>- provenance: page_no, bbox, sheet_name"]
        STORE["Extraction Storage Manager<br/>- data/sources/ (canonical files)<br/>- data/extractions/ (normalized JSON)<br/>- data/tables/ (CSV / JSON tables)<br/>- data/javed.db (SQLite registry)"]
    end

    subgraph Consumers ["Downstream Consumers"]
        AGENT["LangGraph Agent Runtime<br/>(Structured Tools)"]
        UI["React Web UI<br/>(Extraction Viewer & HUD)"]
        RAG["Future BRICK-009 RAG<br/>(Chunks & Vector Embeddings)"]
    end

    URL --> SSRF --> CRAWL --> NORM
    DOC --> QUAR --> DOCLING --> NORM
    NORM --> STORE
    STORE --> AGENT
    STORE --> UI
    STORE -.-> RAG
```

### 3.1 Crawl4AI vs Docling Clear Boundaries
| Responsibility | Crawl4AI Subsystem | Docling Subsystem |
|---|:---:|:---:|
| **Public Web Page Acquisition** | **PRIMARY** | Disallowed |
| **Dynamic SPA / JavaScript Execution** | **PRIMARY** | Disallowed |
| **HTML Cleanup (Nav, Footer, Cookie Banners)** | **PRIMARY** | Disallowed |
| **Web Link Graph & Metadata** | **PRIMARY** | Disallowed |
| **PDF Extraction & Layout Analysis** | Disallowed | **PRIMARY** |
| **Table Structure & Grid Preservation** | Basic HTML tables | **PRIMARY (Deep TableFormer)** |
| **Word Document (.docx) Parsing** | Disallowed | **PRIMARY** |
| **Excel Spreadsheet (.xlsx) Multi-Sheet** | Disallowed | **PRIMARY** |
| **Element Bounding Box & Page Provenance** | DOM CSS paths | **PRIMARY (Exact BBox & Pages)** |

---

## 4. Normalized Extraction Schema Specification

Every extraction result, regardless of source type, will conform to the canonical `NormalizedDocument` Pydantic model (proposed for Phase 2 implementation in `src/javed/extraction/schema.py`):

```python
from datetime import datetime
from enum import StrEnum
from typing import Any, List, Optional
from pydantic import BaseModel, Field

class SourceType(StrEnum):
    WEB_PAGE = "web_page"
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    TEXT = "text"

class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST_ITEM = "list_item"
    CODE_BLOCK = "code_block"
    CAPTION = "caption"
    FOOTNOTE = "footnote"

class ExtractionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"

class ElementProvenance(BaseModel):
    page_no: Optional[int] = Field(default=None, description="1-based page number")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box [x0, y0, x1, y1]")
    char_span: Optional[List[int]] = Field(default=None, description="Character offset [start, end]")
    sheet_name: Optional[str] = Field(default=None, description="Sheet name for spreadsheets")
    cell_range: Optional[str] = Field(default=None, description="Cell range e.g. A1:D15")

class TableRepresentation(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0
    sheet_name: Optional[str] = None
    cell_range: Optional[str] = None
    markdown_table: str = ""
    csv_table: str = ""

class ExtractionElement(BaseModel):
    element_id: str = Field(description="Deterministic ID e.g. doc_id#el_0")
    block_type: BlockType
    text_content: str
    section_hierarchy: List[str] = Field(default_factory=list)
    provenance: Optional[ElementProvenance] = None
    table_data: Optional[TableRepresentation] = None

class ExtractorInfo(BaseModel):
    name: str = Field(description="'crawl4ai' or 'docling'")
    version: str
    strategy: str

class NormalizedDocument(BaseModel):
    document_id: str = Field(description="UUID4 document record identifier")
    source_type: SourceType
    source_uri: str = Field(description="Original URL or relative file path")
    source_title: Optional[str] = None
    content_hash: str = Field(description="SHA-256 hex digest of raw source content")
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)
    extractor: ExtractorInfo
    mime_type: str
    language: Optional[str] = None
    word_count: int = 0
    page_count: Optional[int] = None
    content_markdown: str = Field(description="Complete normalized markdown representation")
    content_text: str = Field(description="Plain text representation")
    elements: List[ExtractionElement] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS
    error_message: Optional[str] = None
```

---

## 5. Security & Defensive Ingestion Boundaries

| Attack Vector / Failure Mode | Defensive Enforcement Mechanism | Status & Enforcement Layer |
|---|---|---|
| **Server-Side Request Forgery (SSRF)** | Pre-crawl IP validation via `BrowserSecurityGuard`. Blocks RFC 1918, loopbacks (`127.0.0.1`), link-local metadata (`169.254.169.254`), and numeric encoded IPs. | **`Implemented & Verified in BRICK-006`** (`src/javed/browser/security.py`) |
| **Standalone Archive Ingestion** | Strict file type whitelist. Standalone archive formats (`.zip`, `.tar.gz`, `.7z`) are rejected immediately. | **`Planned for Phase 3`** (`src/javed/extraction/security.py`) |
| **OOXML Zip Internals & Decompression Bomb** | Bounded inspection of internal ZIP structures in `.docx`, `.xlsx`, `.pptx`: max single entry <= 20 MB, max total uncompressed <= 50 MB, compression ratio < 100:1, max entry count <= 1,000, entry name traversal sanitization (blocking `../`, `..\\`, absolute paths, device names). | **`Planned for Phase 3`** (`src/javed/extraction/security.py`) |
| **Oversized Document / OOM** | Strict file size cap: **25 MB** default (max 50 MB). Memory check before task acceptance (`psutil.virtual_memory().percent < 90%`). | **`Planned for Phase 3`** (`src/javed/extraction/security.py`) |
| **Page Count Exhaustion** | Maximum PDF page limit: **200 pages**. Documents exceeding this limit are truncated or rejected. | **`Planned for Phase 3`** (`src/javed/extraction/security.py`) |
| **Processing Timeout** | Web crawl capped at 30s; document conversion capped at 60s via `asyncio.wait_for`. | **`Planned for Phase 4/5`** (Async Worker Gateway) |
| **Path Traversal Attacks** | UUID-based sanitized storage in `data/quarantine/` and `data/sources/`. Blocks `..`, absolute paths, and NTFS stream syntax (`::$DATA`). | **`Planned for Phase 3`** (`src/javed/extraction/security.py`) |
| **XML External Entity (XXE)** | XML parsers in `python-docx` and `openpyxl` protected via `defusedxml` and strict entity resolution disabling. | **`Planned for Phase 3/5`** (Parser Configuration) |
| **Password-Protected Documents** | Fail-closed graceful detection. Returns `ErrorCode.PASSWORD_PROTECTED` with status `FAILED` without worker crash. | **`Planned for Phase 5`** (`DoclingDocumentExtractor`) |
| **Corrupted / Malformed Files** | Exception containment. Catches parser failures (`PdfiumError`, `BadZipFile`), records diagnostic warning, flags `FAILED`. | **`Planned for Phase 3/5`** (Ingestion Pipeline) |
| **Active Code / Embedded Scripts** | PDF embedded JavaScript dictionaries (`/JS`) are ignored. Web extractions strip `<script>`, `<style>`, `<iframe>`, and event attributes. | **`Planned for Phase 4/5`** (Parser & Crawler Sanitizer) |
| **Sensitive Content Leaks** | Telemetry and console logging strictly exclude raw document contents. Only document ID, MIME type, page count, and status are logged. | **`Planned for Phase 7/8`** (API & Worker Logging) |

---

## 6. Document Identity, Deduplication & Versioning Lifecycle

1. **Content Hashing**:
   - Every source file or downloaded web page has its raw bytes hashed via `sha256(raw_bytes).hexdigest()`.
2. **Deduplication Logic**:
   - When a document is ingested:
     - Query SQLite `documents` table for `(source_uri, content_hash)`.
     - If an exact match exists with status `SUCCESS`, skip re-extraction and return the cached `NormalizedDocument`.
3. **Incremental Versioning**:
   - If `source_uri` matches an existing document but `content_hash` differs:
     - Mark existing record as `is_latest = False`.
     - Insert new record with `version = previous_version + 1` and `is_latest = True`.
4. **State Transition Machine**:
   - `QUEUED` -> `EXTRACTING` -> `SUCCESS` (or `FAILED` / `PARTIAL_SUCCESS`).
   - Failed extractions preserve failure diagnostics in the database and can be safely retried.

---

## 7. Storage Architecture & Directory Structure

```
data/
  ├── sources/                   # Canonical raw uploaded / acquired source files
  │     └── [doc_id].[ext]       # Stored by UUID filename with original extension
  ├── quarantine/                # Temporary upload staging for pre-validation inspection
  ├── extractions/               # Persisted NormalizedDocument JSON representations
  │     └── [doc_id].json        # Full document JSON with elements and provenance
  ├── tables/                    # Standalone tabular data exports
  │     └── [doc_id]_table_0.csv # Formatted CSV export for fast spreadsheet review
  ├── tmp/                       # Ephemeral scratch files (auto-purged in finally blocks)
  └── javed.db                   # SQLite database (documents & extractions tables)
```

---

## 8. Deterministic Acceptance Fixtures Strategy

To ensure reproducible testing without external network dependencies, a dedicated test fixture suite will be created in `tests/fixtures/extraction/`:
1. `static_page.html`: Semantic HTML5 page with headings, paragraphs, lists, and meta tags.
2. `dynamic_page.html`: Page requiring client-side JS DOM manipulation before content appears.
3. `simple.pdf`: 1-page clean PDF with title and paragraph.
4. `multipage.pdf`: 3-page PDF with multi-level headings and page headers/footers.
5. `table.pdf`: PDF containing a structured financial data table with row/column headers.
6. `sample.docx`: Word document containing Heading 1, Heading 2, bulleted list, and a 3x3 table.
7. `sample.xlsx`: Multi-sheet spreadsheet ("Quarterly_Sales", "Expenses") with headers and data.
8. `unsupported.bin`: Random binary file testing MIME whitelist rejection.
9. `corrupted.pdf`: Truncated, unparseable PDF testing fail-closed exception handling.
10. `oversized.bin`: Synthetic file exceeding 25 MB limit testing 413 rejection.
11. `duplicate.pdf`: Identical copy of `simple.pdf` testing deduplication bypass.
12. `updated_v2.docx`: Modified version of `sample.docx` testing incremental version increment.

---

## 9. Phased Execution Plan (Phases 0 through 10)

| Phase & Task ID | Milestone Phase Description | Key Deliverables & Acceptance Criteria |
|---|---|---|
| **Phase 0 (`TASK-070-P0`)** | **Preflight, Dependency Audit & Architecture Plan** | Author `BRICK-007.md`, evaluate dependencies, design normalized schema, define security boundaries. *(Completed)* |
| **Phase 1 (`TASK-070-P1`)** | **Dependency Installation & Hardware Sandbox** | Install `crawl4ai` and `docling` in `pyproject.toml`; verify Windows CPython 3.12 compatibility; verify zero process leaks. *(Completed & Accepted at `e1ebba9`)* |
| **Phase 2 (`TASK-070-P2`)** | **Normalized Extraction Schema & Pydantic Models** | Implement `src/javed/extraction/schema.py`; full serialization and validation unit tests. *(Completed & Accepted at `3bf1658`)* |
| **Phase 3 (`TASK-070-P3`)** | **Security Guard, Quarantine & Whitelist Validator** | Implement `src/javed/extraction/security.py` (`ExtractionSecurityGuard`, `QuarantineManager`); file size, page count, MIME magic, OOXML zip inspection, active content warnings, path traversal guards; 66/66 targeted tests passed; 317/317 full regression passed. *(Completed)* |
| **Phase 4 (`TASK-070-P4`)** | **Crawl4AI Web Extraction Subsystem** | Implement `src/javed/extraction/web.py` (`Crawl4AIWebExtractor`); SSRF protection, headless Chromium rendering, markdown generation; deterministic mock HTTP server tests. |
| **Phase 5 (`TASK-070-P5`)** | **Docling Document Extraction Subsystem** | Implement `src/javed/extraction/documents.py` (`DoclingDocumentExtractor`); PDF (layout + table extraction), DOCX, XLSX parsers; provenance tracking; fixture tests. |
| **Phase 6 (`TASK-070-P6`)** | **Storage Manager, Deduplication & Metadata Registry** | Implement `src/javed/extraction/storage.py` (`ExtractionStorageManager`); SQLite `documents` and `extractions` tables; SHA-256 deduplication and versioning. |
| **Phase 7 (`TASK-070-P7`)** | **LangChain Agent Tools & HITL Ingestion Gating** | Implement `src/javed/extraction/tools.py` (`extract_web_page`, `extract_document`, `list_ingested_documents`); bind into LangGraph agent runtime; permission tier enforcement. |
| **Phase 8 (`TASK-070-P8`)** | **REST API & Developer Mode Telemetry** | Implement FastAPI endpoints in `src/javed/api/v1/extraction.py` (`/upload`, `/crawl`, `/documents`); streaming progress events; OpenAPI schemas. |
| **Phase 9 (`TASK-070-P9`)** | **React Document Ingestion UI & Extraction Viewer** | Build `DocumentUploadZone.tsx`, `ExtractionViewer.tsx`, and `TableView.tsx` in `frontend/src/components/extraction/`; Vitest component tests. |
| **Phase 10 (`TASK-070-P10`)** | **Full Regression Gate, Hardening & REPORT-007** | Full test sweep (backend pytest, frontend vitest, ruff, oxlint, build); Windows process leak audit; deliver comprehensive `docs/reports/REPORT-007.md`. *(Preserves TASK-080 for BRICK-008)* |

> [!NOTE] Phase 1 Carry-Forward Clarifications (Accepted at commit `e1ebba9`)
> 1. Direct dependencies are bounded in `pyproject.toml`; exact resolution is recorded by `requirements.lock`.
> 2. Top-level Docling import timing (`import docling`) measures module import, not full converter startup timing.
> 3. Zero-download verification applies to the lightweight initialization path (`PyPdfiumDocumentBackend` with model-backed stages disabled).
> 4. Actual extraction performance remains unverified until extractor phases (Phase 4 for Crawl4AI, Phase 5 for Docling).

> [!NOTE] Future OpenCLI Architecture Decision (Roadmap: BRICK-008)
> - **Candidate Evaluated**: `jackwener/OpenCLI`
> - **Roadmap Placement**: Formally assigned to **BRICK-008** (Autonomous Web Navigation & Authenticated Sources). Not part of BRICK-007.
> - **Purpose**: Enable owner-authorized access through a dedicated, logged-in Chrome profile where direct API authorization is unavailable.
> - **Phase 2 Contract**: `AuthenticatedSourceContext` defines zero-trust metadata contracts (opaque session references, service names, approved domains) strictly excluding secrets, cookies, or profile paths. Zero OpenCLI code, daemons, or extensions installed in BRICK-007.

> [!NOTE] Phase 2 Carry-Forward Clarifications (Accepted at commit `3bf1658`)
> 1. **Model Immutability vs Assignment Validation**: `ImmutableExtractionBase` is currently configured with `extra="forbid"`, `validate_assignment=True`, and `populate_by_name=True`. It is intentionally **not** frozen (`frozen=False`), allowing validated attribute assignment during pipeline stage transitions while preventing unknown fields. Output snapshots achieve canonical immutability through `with_computed_output_hash()` and content-addressed SHA-256 serialization.
> 2. **Canonical Hash Payload & Semantics**: The canonical hash payload generated by `to_canonical_json()` serializes the complete `NormalizedDocument` dictionary excluding `normalized_output_sha256` with lexicographically sorted keys (`sort_keys=True`) and minimal separators (`separators=(",", ":")`). Semantics: it produces a deterministic, collision-resistant SHA-256 fingerprint covering document metadata, source descriptors, extractor configuration, elements, structured tables, and text, serving as an immutable cache key and data-integrity verification token.
> 3. **Rejection of Credentials & Secret Parameters**: `SourceDescriptor` strictly **rejects** embedded credentials (`user:pass@`) and secret-bearing query parameters (`token=`, `password=`, etc.) with fail-closed `ValueError` exceptions; it does **not** silently strip or sanitize them.

> [!NOTE] Phase 3B Hardening & Conditional Acceptance (Accepted at commit `5ccc3c3`)
> 1. **Base Model Terminology & Mutation Invalidation**: `ExtractionBaseModel` (aliased as `ImmutableExtractionBase` for backward compatibility) enforces `extra="forbid"`, `validate_assignment=True`, and `frozen=False`. It is a strict validated model, not an immutable instance. To prevent stale digests after model mutation, mutating any field automatically invalidates all computed hash fields (`normalized_content_sha256`, `extraction_record_sha256`, `normalized_output_sha256`), and model validation strictly rejects mismatched/stale digests fail-closed.
> 2. **Content Hash vs Record Hash Separation**: Content identity (`normalized_content_sha256` via `compute_content_sha256()`) hashes purely the normalized content and structure (`metadata`, `elements`, `full_text`, `full_markdown`), remaining identical across duplicate runs. Record identity (`extraction_record_sha256` via `compute_record_sha256()`) hashes the complete execution run (lifecycle IDs, source origin, extractor configuration, timestamps, diagnostics).
> 3. **Blocking Inspections & Timeout/Cleanup Proof**: Preflight deep inspections in `ExtractionSecurityGuard` execute within a managed thread pool executor. Blocking PDF or Office parsing strictly respects `preflight_timeout_seconds`, triggering `EXTRACTION_TIMEOUT` and guaranteeing immediate quarantine file deletion without leaks. Event-loop execution is preserved via non-blocking `validate_file_async()`.
> 4. **Semaphore Release & No Deadlock**: `_semaphore` release is guaranteed in `finally:`, preventing concurrency permit leaks. Subsequent validations succeed immediately without deadlock.
> 5. **Late Promotion Prevention**: Quarantined files are tracked by `inspection_id` in `QuarantineManager._active_files`. On timeout, the file is unlinked immediately. When a slow thread finishes, `_validate_file_internal` verifies `is_inspection_active(inspection_id)`. If inactive, it unlinks any quarantine file and returns `EXTRACTION_TIMEOUT`, strictly preventing late promotion.
> 6. **Explicit Inspection Entry Points**: Dedicated, strongly typed methods (`validate_bytes`, `validate_stream`, `validate_local_file`, `validate_text`, `validate_html`, and async counterparts) prevent ambiguous string inference.
> 7. **Heuristic Raw PDF Marker Detection**: Raw token scanning for active PDF markers (`/JS`, `/Launch`, etc.) is a defense-in-depth heuristic on uncompressed streams; it does not replace sandboxed engine execution, as streams can be compressed (FlateDecode) or encrypted.
> 8. **HTML Preflight Trust Boundary**: Preflight classification and script pattern detection flag untrusted markers; preflight acceptance does not render HTML trusted or safe for unescaped DOM insertion. Crawl4AI SSRF guards and origin controls remain mandatory.
> 9. **Explicit Input Typing**: Input types must be explicitly confirmed by magic signatures, structure validation, and declared MIME contracts rather than trusted from arbitrary user-supplied extension strings.
> 10. **Nested Mutation Prevention & Deep Immutability**:
>     - **Deep Immutability after Finalization (`finalize()`)**: Once `doc.finalize()` is called, all child models (`metadata`, `elements`, `source`, `extractor`, `table`, etc.), lists (`ReadOnlyList`), and dictionaries (`ReadOnlyDict`) are recursively deeply frozen (`_is_finalized = True`). Attempting to mutate or delete any attribute, append/remove/assign list items, or update dict entries raises a fail-closed `TypeError`.
>     - **Parent Invalidation on Unfinalized Child Models**: In unfinalized documents, child models hold weak backreferences (`_root_doc_ref`). Mutating any nested model automatically notifies the parent document to clear all cached hash fields (`normalized_content_sha256`, `extraction_record_sha256`, `normalized_output_sha256`).
>     - **Mandatory Hash Reverification before Trust Boundaries**: `verify_trust_boundary(doc)` and `assert_hash_integrity()` recompute cryptographic digests from scratch against the live object graph. Even if low-level reflection (`object.__setattr__`) bypasses `__setattr__`, any stale or drifted digest is immediately caught and rejected with `HashIntegrityError`. Unfinalized documents are strictly rejected at trust boundaries.

> [!NOTE] Phase 3C Finalization & Nested Mutation Integrity Contract
> 1. **Nested Mutation Analysis & Bypass Findings**:
>    - In unfinalized draft documents, in-place list mutations (`document.elements.append(...)`, `document.elements.pop(...)`, `document.warnings.append(...)`, `document.errors.append(...)`) modify collections directly and bypass `NormalizedDocument.__setattr__`. Stored hashes are therefore explicitly unauthoritative during drafting.
>    - Live cryptographic verification (`verify_hashes()` / `verify_hash_integrity()`) recomputes normalized-content and extraction-record digests from the live object graph using constant-time comparison (`hmac.compare_digest`) without trusting stored fields, immediately catching any direct or nested mutation fail-closed.
>    - Direct nested model attribute mutations (`document.metadata.title = ...`, `document.elements[0].text = ...`, `document.elements[0].provenance.page_number = ...`, `document.elements[0].table.rows[0][0].value = ...`, `document.full_text = ...`, `document.full_markdown = ...`) notify the root document via recursive weak backreferences (`_root_doc_ref`) and immediately invalidate cached digests to `None`.
> 2. **Adopted Integrity Model (Preferred Model)**:
>    - **Draft Phase**: `NormalizedDocument` is mutable during pipeline assembly (`is_finalized == False`). Collections (`elements`, `warnings`, `errors`, `table.rows`, `custom_attributes`) are standard mutable Python `list` and `dict` instances for straightforward extraction builder assembly.
>    - **Explicit Finalization**: Calling `doc.finalize()` validates all document contracts, freshly computes canonical digests from the live content and record, and deeply freezes the entire document hierarchy into immutable representations (`ReadOnlyList`, `ReadOnlyDict`).
>    - **Finalized Immutability**: Finalized documents reject all direct field mutations, nested model mutations, collection appends/modifications, and attribute deletions with `TypeError`.
>    - **Trust Boundary Enforcement**: `verify_trust_boundary(doc, require_finalized=True)` requires `doc.is_finalized is True` and asserts live hash integrity (`assert_hash_integrity()`), failing closed with `HashIntegrityError` on any drift or unfinalized state.
>    - **Mandatory Trust Boundaries**: Successful hash verification is mandatory before future persistence, quarantine promotion into canonical storage, deduplication, cache reuse, version comparison, API response publication, BRICK-009 chunking, embedding generation, vector indexing, or downstream agent handoff.
> 3. **Compatibility-Alias Disposition**:
>    - `ImmutableExtractionBase` is formally deprecated as a compatibility alias for `ExtractionBaseModel` and scheduled for removal in Stage 5 / BRICK-013 (Production Hardening & Release Validation). Unfinalized models are explicitly documented as mutable drafts, not immutable instances.
> 4. **Table Cell Property & API Hardening**:
>    - `TableCell.value` property alias (`@property def value`, `@value.setter def value`) allows cell text access and mutation, cascading hash invalidation up to the parent document during drafting, and rejecting mutation after finalization.
>    - `compute_normalized_content_sha256()` and `compute_extraction_record_sha256()` provide canonical entry points for digest generation.
>    - `verify_hashes(*, fail_closed: bool = False, structured: bool = False)` provides constant-time comparison via `hmac.compare_digest` and returns detailed diagnostic reports (`HashVerificationResult`).

### Hash Field Inclusion Rules

| Field Name | Digest Purpose | Included Fields | Excluded Fields |
|---|---|---|---|
| `normalized_content_sha256` | Content Identity (Stable deduplication across runs) | `metadata` (DocumentMetadata), `elements` (ExtractionElement list), `full_text`, `full_markdown` | `document_id`, `version_id`, `ingestion_id`, `source`, `authenticated_context`, `extractor`, `extracted_at`, `status`, `warnings`, `errors`, `source_sha256`, and all hash fields |
| `extraction_record_sha256` | Execution Record Identity (Full lifecycle provenance) | All model fields (`document_id`, `version_id`, `ingestion_id`, `source`, `authenticated_context`, `extractor`, `metadata`, `elements`, `full_text`, `full_markdown`, `status`, `warnings`, `errors`, `extracted_at`, `source_sha256`) | `normalized_content_sha256`, `extraction_record_sha256`, `normalized_output_sha256` (excludes only hash fields to eliminate circularity) |
| `normalized_output_sha256` | Backward Compatibility | Identical to `extraction_record_sha256` | Same as `extraction_record_sha256` |

---

## 10. Mandatory Stop Points & Acceptance Criteria

In strict accordance with project rules:
1. **Phase 0 Stop Point**: Execution halts upon committing the Phase 0 specification and plan. Await explicit Project Owner review and Phase 1 authorization.
2. **Phase Boundaries**: Advance strictly one phase at a time upon explicit authorization.
3. **Phase 10 Final Stop Point**: Upon completing Phase 10 verification, deliver `docs/reports/REPORT-007.md` and set status to `READY FOR ACCEPTANCE`. Await explicit Project Owner sign-off before merging into `master`.

