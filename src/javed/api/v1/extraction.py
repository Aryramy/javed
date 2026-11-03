"""FastAPI endpoints for document and web extraction, persistence, and telemetry."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

from javed.extraction.schema import SourceType
from javed.extraction.security import sanitize_display_name
from javed.extraction.storage import (
    ExtractionStorageManager,
    StoredExtractionRecord,
    StoredTableInfo,
)
from javed.extraction.tools import (
    DEFAULT_PREVIEW_MAX_CHARS,
    PERMITTED_DOCUMENT_EXTENSIONS,
    ExtractionToolsManager,
)
from javed.extraction.web import (
    WebExtractionSecurityError,
    validate_web_url,
)
from javed.schemas.extraction import (
    CrawlRequest,
    DeleteDocumentResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    ExtractionResponse,
    ExtractionTelemetryResponse,
    TableSummary,
)

logger = logging.getLogger("javed.api.v1.extraction")

router = APIRouter(prefix="/extraction", tags=["Extraction"])


# -----------------------------------------------------------------------------
# Dependency Providers
# -----------------------------------------------------------------------------


def get_extraction_tools_manager(request: Request) -> ExtractionToolsManager:
    """Retrieve or lazily initialize ExtractionToolsManager from app state."""
    mgr: ExtractionToolsManager | None = getattr(
        request.app.state,
        "extraction_tools_manager",
        None,
    )
    if mgr is None:
        mgr = ExtractionToolsManager()
        request.app.state.extraction_tools_manager = mgr
    return mgr


def get_extraction_storage(request: Request) -> ExtractionStorageManager:
    """Retrieve ExtractionStorageManager from the extraction tools manager."""
    tools_mgr = get_extraction_tools_manager(request)
    return tools_mgr.storage


# -----------------------------------------------------------------------------
# Extraction Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/upload",
    summary="Upload and extract structured content from a local document",
    response_model=ExtractionResponse,
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="The document file (PDF, DOCX, XLSX).")],
    tools_mgr: Annotated[ExtractionToolsManager, Depends(get_extraction_tools_manager)],
    max_chars: Annotated[
        int,
        Query(
            ge=1,
            le=100000,
            description="Max preview characters to return for text and markdown.",
        ),
    ] = DEFAULT_PREVIEW_MAX_CHARS,
) -> ExtractionResponse:
    """Upload a document file (PDF, DOCX, XLSX), run preflight security checks,
    extract structured content with Docling, and persist into the metadata registry.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    clean_name = sanitize_display_name(file.filename)
    ext = Path(clean_name).suffix.lower()
    if ext not in PERMITTED_DOCUMENT_EXTENSIONS:
        perm_exts = sorted(PERMITTED_DOCUMENT_EXTENSIONS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported document format '{ext}'. Permitted formats: {perm_exts}",
        )

    try:
        content_bytes = await file.read()
    except Exception as exc:
        logger.error("Failed reading uploaded file bytes: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed reading uploaded file: {exc}",
        ) from exc

    if not content_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # 1. Zero-trust Preflight Security Inspection
    security_guard = tools_mgr._security_guard
    decision = await security_guard.validate_bytes_async(
        data=content_bytes,
        original_filename=clean_name,
        declared_mime=file.content_type,
    )
    if decision.outcome.value == "rejected":
        code = decision.error_code.value if decision.error_code else "SECURITY_VIOLATION"
        msg = decision.error_message or "Document failed preflight security inspection"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": code, "message": msg},
        )

    # 2. Extract structured content via Docling
    try:
        doc_extractor = tools_mgr.get_doc_extractor()
        # Stage bytes to temporary file for Docling local ingestion
        quarantine_path = decision.quarantine_path
        if quarantine_path and Path(quarantine_path).is_file():
            extract_target_path = Path(quarantine_path)
        else:
            # Fallback to direct staging in storage directory
            temp_path = tools_mgr.storage.sources_dir / f"temp_{clean_name}"
            temp_path.write_bytes(content_bytes)
            extract_target_path = temp_path

        doc = await doc_extractor.extract_file_async(
            extract_target_path,
            display_name=clean_name,
            source_uri=clean_name,
        )
    except Exception as exc:
        logger.error("Document extraction failed for '%s': %s", clean_name, exc, exc_info=True)
        # Attempt quarantine cleanup
        if decision.quarantine_path:
            try:
                security_guard.cleanup_quarantine(decision.quarantine_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extraction failed: {exc}",
        ) from exc

    # 3. Persist and deduplicate via ExtractionStorageManager
    try:
        ingestion = await tools_mgr.storage.store_document_async(
            document=doc,
            raw_bytes=content_bytes,
        )
    except Exception as exc:
        logger.error("Persistence failed for '%s': %s", clean_name, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document persistence failed: {exc}",
        ) from exc
    finally:
        # Guarantee quarantine cleanup
        if decision.quarantine_path:
            try:
                security_guard.cleanup_quarantine(decision.quarantine_path)
            except Exception:
                pass

    # 4. Construct unified response
    tables_summary = [
        TableSummary(
            table_id=t.table_id or f"table_{idx + 1}",
            row_count=t.row_count,
            column_count=t.column_count,
            headers=t.headers,
            sheet_name=t.sheet_name,
            markdown=t.to_markdown() if hasattr(t, "to_markdown") else "",
        )
        for idx, t in enumerate(doc.tables)
    ]

    full_txt = doc.full_text or ""
    full_md = doc.full_markdown or ""
    is_truncated = len(full_txt) > max_chars or len(full_md) > max_chars

    return ExtractionResponse(
        success=True,
        document_id=ingestion.document_id,
        extraction_id=ingestion.extraction_id,
        version_id=ingestion.version_id,
        source_uri=doc.source.source_uri,
        original_display_name=clean_name,
        mime_type=doc.source.mime_type,
        title=doc.metadata.title,
        is_duplicate=ingestion.is_duplicate,
        is_new_version=ingestion.is_new_version,
        status=doc.status.value,
        element_count=len(doc.elements),
        table_count=doc.metadata.table_count,
        page_count=doc.metadata.page_count,
        word_count=doc.metadata.word_count,
        tables=tables_summary,
        text_preview=full_txt[:max_chars],
        markdown_preview=full_md[:max_chars],
        is_truncated=is_truncated,
        warnings=[w.message for w in doc.warnings],
    )


@router.post(
    "/crawl",
    summary="Crawl and extract structured content from a public web page",
    response_model=ExtractionResponse,
)
async def crawl_web_page(
    crawl_req: CrawlRequest,
    tools_mgr: Annotated[ExtractionToolsManager, Depends(get_extraction_tools_manager)],
) -> ExtractionResponse:
    """Acquire a single public web page via Crawl4AI, extract visible text and tables,
    and persist into the extraction registry under strict SSRF policy.
    """
    try:
        # Pre-validate URL and SSRF before dispatch
        validate_web_url(
            crawl_req.url,
            allow_loopback_for_testing=tools_mgr.allow_loopback_for_testing,
        )
    except WebExtractionSecurityError as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security Policy Violation: {sec_err}",
        ) from sec_err

    res = await tools_mgr.extract_web_page(
        url=crawl_req.url,
        strategy=crawl_req.strategy,
        max_chars=crawl_req.max_chars,
    )

    if not res.get("success"):
        err_msg = res.get("error", "Web extraction failed")
        if "Security" in err_msg or "SSRF" in err_msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=err_msg)

    tables_summary = [
        TableSummary(
            table_id=t.get("table_id") or f"table_{idx + 1}",
            row_count=t.get("row_count", 0),
            column_count=t.get("column_count", 0),
            headers=t.get("headers", []),
            sheet_name=t.get("sheet_name"),
            markdown=t.get("markdown", ""),
        )
        for idx, t in enumerate(res.get("tables", []))
    ]

    return ExtractionResponse(
        success=True,
        document_id=res["document_id"],
        extraction_id=res["extraction_id"],
        version_id=res["version_id"],
        source_uri=res.get("url"),
        original_display_name=res.get("title", crawl_req.url),
        mime_type="text/html",
        title=res.get("title"),
        is_duplicate=res.get("is_duplicate", False),
        is_new_version=res.get("is_new_version", False),
        status="SUCCESS",
        element_count=res.get("element_count", 0),
        table_count=res.get("table_count", 0),
        page_count=1,
        word_count=res.get("word_count"),
        tables=tables_summary,
        text_preview=res.get("text_preview", ""),
        markdown_preview=res.get("markdown_preview", ""),
        is_truncated=res.get("is_truncated", False),
        warnings=res.get("warnings", []),
    )


@router.post(
    "/crawl/stream",
    summary="Stream web crawl progress and structured results via Server-Sent Events (SSE)",
    response_class=StreamingResponse,
)
async def stream_crawl_web_page(
    crawl_req: CrawlRequest,
    request: Request,
    tools_mgr: Annotated[ExtractionToolsManager, Depends(get_extraction_tools_manager)],
) -> StreamingResponse:
    """Stream real-time progress events during web crawling, delivering progress updates
    and a final completed document payload via SSE.
    """

    async def event_generator() -> AsyncIterator[str]:
        try:
            # Step 1: Pre-validation
            msg1 = f"Validating URL syntax and zero-trust SSRF policy for {crawl_req.url}"
            yield (
                "event: progress\ndata: "
                + json.dumps({"step": "validating", "message": msg1})
                + "\n\n"
            )

            validate_web_url(
                crawl_req.url,
                allow_loopback_for_testing=tools_mgr.allow_loopback_for_testing,
            )

            # Step 2: Acquisition
            msg2 = f"Acquiring web content using {crawl_req.strategy} strategy"
            yield (
                "event: progress\ndata: "
                + json.dumps({"step": "fetching", "message": msg2})
                + "\n\n"
            )

            res = await tools_mgr.extract_web_page(
                url=crawl_req.url,
                strategy=crawl_req.strategy,
                max_chars=crawl_req.max_chars,
            )

            if not res.get("success"):
                err_msg = res.get("error", "Web extraction failed")
                yield "event: error\ndata: " + json.dumps({"error": err_msg}) + "\n\n"
                return

            # Step 3: Complete
            yield "event: complete\ndata: " + json.dumps(res) + "\n\n"

        except WebExtractionSecurityError as sec_err:
            yield (
                "event: error\ndata: "
                + json.dumps({"error": f"Security Policy Violation: {sec_err}"})
                + "\n\n"
            )
        except Exception as exc:
            logger.error("Error during streaming web crawl: %s", exc, exc_info=True)
            yield "event: error\ndata: " + json.dumps({"error": str(exc)}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -----------------------------------------------------------------------------
# Metadata Registry & Document Management
# -----------------------------------------------------------------------------


@router.get(
    "/documents",
    summary="List previously ingested documents with pagination and source filter",
    response_model=DocumentListResponse,
)
async def list_documents(
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Items per page.",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Pagination offset.",
        ),
    ] = 0,
    source_type: Annotated[
        str | None,
        Query(
            description="Optional filter by source_type (web_page, pdf, docx, xlsx).",
        ),
    ] = None,
) -> DocumentListResponse:
    """Retrieve a paginated list of ingested documents from SQLite."""
    st: SourceType | None = None
    if source_type:
        try:
            st = SourceType(source_type.strip().lower())
        except ValueError as val_err:
            valid_sources = [s.value for s in SourceType]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source_type '{source_type}'. Valid options: {valid_sources}",
            ) from val_err

    items = await storage.list_documents_async(limit=limit, offset=offset, source_type=st)
    total = await storage.count_documents_async(source_type=st)

    return DocumentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    summary="Retrieve detailed metadata, extractions, and preview for a document",
    response_model=DocumentDetailResponse,
)
async def get_document_details(
    document_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
    include_content: Annotated[
        bool,
        Query(description="Whether to reload text/markdown preview."),
    ] = True,
    max_chars: Annotated[
        int,
        Query(
            ge=1,
            le=100000,
            description="Maximum characters of plain text and markdown to include.",
        ),
    ] = DEFAULT_PREVIEW_MAX_CHARS,
) -> DocumentDetailResponse:
    """Retrieve full detail view for a specific document including extraction runs and tables."""
    doc = await storage.get_document_async(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    extractions = await storage.list_extractions_async(document_id)
    tables = await storage.list_tables_async(document_id)

    text_preview = ""
    markdown_preview = ""
    is_truncated = False

    if include_content and doc.current_extraction_id:
        normalized_doc = await storage.load_normalized_document_async(doc.current_extraction_id)
        if normalized_doc:
            full_txt = normalized_doc.full_text or ""
            full_md = normalized_doc.full_markdown or ""
            text_preview = full_txt[:max_chars]
            markdown_preview = full_md[:max_chars]
            is_truncated = len(full_txt) > max_chars or len(full_md) > max_chars

    return DocumentDetailResponse(
        document=doc,
        extractions=extractions,
        tables=tables,
        text_preview=text_preview,
        markdown_preview=markdown_preview,
        is_truncated=is_truncated,
    )


@router.get(
    "/documents/{document_id}/extractions",
    summary="List all historical extraction runs for a document",
    response_model=list[StoredExtractionRecord],
)
async def list_document_extractions(
    document_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
) -> list[StoredExtractionRecord]:
    """Retrieve the full historical sequence of extraction records for a document."""
    doc = await storage.get_document_async(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return await storage.list_extractions_async(document_id)


@router.get(
    "/documents/{document_id}/tables",
    summary="List all exported structured tables for a document",
    response_model=list[StoredTableInfo],
)
async def list_document_tables(
    document_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
) -> list[StoredTableInfo]:
    """Retrieve all standalone exported tables extracted from a document."""
    doc = await storage.get_document_async(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return await storage.list_tables_async(document_id)


@router.get(
    "/documents/{document_id}/tables/{table_id}",
    summary="Download or view a specific extracted table as CSV or JSON",
)
async def get_table_data(
    document_id: str,
    table_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
    format: Annotated[
        str,
        Query(description="Export format: 'json' or 'csv'."),
    ] = "json",
) -> Response:
    """Retrieve exported table data in either JSON or CSV format."""
    table = await storage.get_table_async(table_id)
    if not table or table.document_id != document_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_id}' not found for document '{document_id}'",
        )

    fmt = format.strip().lower()
    if fmt not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{format}'. Supported formats: ['json', 'csv']",
        )

    table_path = await asyncio.to_thread(storage.get_table_artifact_path, table_id, fmt)
    if not table_path or not table_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{fmt.upper()} artifact for table not found on disk",
        )

    media_type = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(
        path=str(table_path),
        media_type=media_type,
        filename=f"{table_id}.{fmt}",
    )


@router.get(
    "/documents/{document_id}/download",
    summary="Download the raw original source document file",
)
async def download_raw_document(
    document_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
) -> FileResponse:
    """Download the original unaltered source document from content-addressed storage."""
    doc = await storage.get_document_async(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    if not doc.artifact_available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw source artifact not stored for this document (e.g. web page)",
        )

    raw_path = await asyncio.to_thread(storage.get_raw_artifact_path, document_id)
    if not raw_path or not raw_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source artifact file not found on disk",
        )

    return FileResponse(
        path=str(raw_path),
        media_type=doc.mime_type,
        filename=doc.original_display_name,
    )


@router.delete(
    "/documents/{document_id}",
    summary="Delete an ingested document entity and all associated disk artifacts",
    response_model=DeleteDocumentResponse,
)
async def delete_document(
    document_id: str,
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
) -> DeleteDocumentResponse:
    """Permanently delete a document entity, extraction telemetry records,
    canonical JSON, table exports, and raw source artifacts.
    """
    deleted = await storage.delete_document_async(document_id, delete_artifacts=True)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    return DeleteDocumentResponse(
        success=True,
        document_id=document_id,
        deleted=True,
        message=f"Document '{document_id}' and all associated artifacts were successfully deleted",
    )


@router.get(
    "/telemetry",
    summary="Retrieve developer mode extraction pipeline telemetry and health",
    response_model=ExtractionTelemetryResponse,
)
async def get_extraction_telemetry(
    storage: Annotated[ExtractionStorageManager, Depends(get_extraction_storage)],
) -> ExtractionTelemetryResponse:
    """Retrieve operational telemetry and storage health metrics."""
    total_docs = await storage.count_documents_async()
    total_exts = await storage.count_extractions_async()
    total_tbls = await storage.count_tables_async()

    is_healthy = Path(storage.db_path).is_file()

    return ExtractionTelemetryResponse(
        total_documents=total_docs,
        total_extractions=total_exts,
        total_tables=total_tbls,
        storage_backend="sqlite_wal",
        storage_status="healthy" if is_healthy else "degraded",
        supported_document_formats=sorted(list(PERMITTED_DOCUMENT_EXTENSIONS)),
        supported_web_strategies=["static", "rendered"],
        storage_healthy=is_healthy,
    )
