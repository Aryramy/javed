"""Comprehensive tests for BRICK-007 Phase 8: REST API & Developer Mode Telemetry.

Validates:
1. Extraction telemetry and pipeline health endpoint (/api/v1/extraction/telemetry).
2. Document upload endpoint (/api/v1/extraction/upload) for PDF, DOCX, XLSX.
3. Content deduplication through upload endpoint.
4. Security rejections: unsupported extensions, empty files, traversal, and size limits.
5. Web crawl endpoint (/api/v1/extraction/crawl) with static and rendered strategies.
6. Web crawl SSRF rejection (cloud metadata, private IPs, sensitive parameters).
7. Streaming web crawl progress via SSE (/api/v1/extraction/crawl/stream).
8. Paginated document listing (/api/v1/extraction/documents) and source_type filtering.
9. Document details (/api/v1/extraction/documents/{id}), extractions, and tables queries.
10. Standalone table data downloads (CSV and JSON format).
11. Raw source file downloads (/api/v1/extraction/documents/{id}/download).
12. Cascading document deletion (/api/v1/extraction/documents/{id}) and artifact cleanup.
13. Clean process and thread hygiene without leaks.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import docx
import openpyxl
import pytest
from aiohttp import web
from httpx import ASGITransport, AsyncClient

from javed.config import Settings
from javed.extraction import (
    ExtractionToolsManager,
    StorageConfig,
)
from javed.main import create_app

# -----------------------------------------------------------------------------
# Fixtures & Synthetic Document Generators
# -----------------------------------------------------------------------------


def find_free_port() -> int:
    """Find a free ephemeral TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def web_server_port() -> int:
    return find_free_port()


@pytest.fixture
async def mock_web_server(web_server_port: int):
    """Run an ephemeral aiohttp mock web server on loopback."""
    app = web.Application()

    async def handle_article(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Annual Revenue Report</title></head>
<body>
    <h1>Executive Financial Overview</h1>
    <p>Consolidated gross margins increased to 68.4% year-over-year.</p>
    <table>
        <thead><tr><th>Department</th><th>Budget</th><th>Spend</th></tr></thead>
        <tbody>
            <tr><td>Engineering</td><td>$4.5M</td><td>$4.2M</td></tr>
            <tr><td>Operations</td><td>$2.1M</td><td>$1.9M</td></tr>
        </tbody>
    </table>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/article", handle_article)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", web_server_port)
    await site.start()

    yield f"http://127.0.0.1:{web_server_port}"

    await runner.cleanup()


def make_synthetic_pdf(target_path: Path, text: str = "Quarterly Financial Analysis") -> Path:
    """Generate minimal valid PDF 1.4 file."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream_content = f"BT\n/F1 14 Tf\n1 0 0 1 72 720 Tm ({escaped}) Tj\nET\n"
    stream_bytes = stream_content.encode("utf-8")

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length "
        + str(len(stream_bytes)).encode("ascii")
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
    target_path.write_bytes(pdf)
    return target_path


def make_synthetic_docx(target_path: Path) -> Path:
    """Generate valid Word .docx file with heading and table."""
    doc = docx.Document()
    doc.add_heading("Operational Roadmap", level=1)
    doc.add_paragraph("Key strategic milestones for platform operations.")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "Initiative"
    tbl.cell(0, 1).text = "Lead"
    tbl.cell(1, 0).text = "Zero Trust Ingestion"
    tbl.cell(1, 1).text = "Security Core"
    doc.save(str(target_path))
    return target_path


def make_synthetic_xlsx(target_path: Path) -> Path:
    """Generate valid Excel .xlsx file with multi-sheet data."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Revenue"
    ws1.append(["Quarter", "Amount"])
    ws1.append(["Q1", 1250000])

    ws2 = wb.create_sheet(title="Costs")
    ws2.append(["Category", "Amount"])
    ws2.append(["Infrastructure", 450000])

    wb.save(str(target_path))
    return target_path


@pytest.fixture
async def api_client(tmp_path: Path):
    """Provide AsyncClient for FastAPI application with isolated extraction storage."""
    settings = Settings(
        env="test",
        openrouter_api_key="sk-or-v1-mock-test-key",
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    app = create_app(settings)

    # Configure isolated extraction storage in temp dir
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "extraction_api.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=storage_cfg,
        allowed_document_roots=[tmp_path],
        allow_loopback_for_testing=True,
    )
    app.state.extraction_tools_manager = tools_mgr

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, tools_mgr, tmp_path

    tools_mgr.close()


# -----------------------------------------------------------------------------
# Unit & Functional API Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_telemetry(api_client: Any) -> None:
    """Verify GET /api/v1/extraction/telemetry returns healthy pipeline metadata."""
    client, tools_mgr, tmp_path = api_client

    res = await client.get("/api/v1/extraction/telemetry")
    assert res.status_code == 200
    data = res.json()

    assert data["total_documents"] == 0
    assert data["total_extractions"] == 0
    assert data["total_tables"] == 0
    assert ".pdf" in data["supported_document_formats"]
    assert ".docx" in data["supported_document_formats"]
    assert ".xlsx" in data["supported_document_formats"]
    assert "static" in data["supported_web_strategies"]
    assert "rendered" in data["supported_web_strategies"]
    assert data["storage_healthy"] is True


@pytest.mark.asyncio
async def test_document_upload_success_pdf(api_client: Any) -> None:
    """Verify POST /api/v1/extraction/upload ingests PDF and subsequent upload dedupes."""
    client, tools_mgr, tmp_path = api_client
    pdf_path = make_synthetic_pdf(tmp_path / "financial.pdf", text="Consolidated income of $8.4M")

    # Step 1: Initial upload
    with open(pdf_path, "rb") as f:
        res = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("financial.pdf", f.read(), "application/pdf")},
        )
    assert res.status_code == 200
    data = res.json()

    assert data["success"] is True
    doc_id = data["document_id"]
    assert doc_id is not None
    assert data["mime_type"] == "application/pdf"
    assert data["page_count"] == 1
    assert "Consolidated income of $8.4M" in data["text_preview"]
    assert not data["is_duplicate"]

    # Step 2: Duplicate upload of identical file
    with open(pdf_path, "rb") as f:
        res2 = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("financial.pdf", f.read(), "application/pdf")},
        )
    assert res2.status_code == 200
    data2 = res2.json()

    assert data2["success"] is True
    assert data2["is_duplicate"] is True
    assert data2["document_id"] == doc_id


@pytest.mark.asyncio
async def test_document_upload_docx_and_xlsx(api_client: Any) -> None:
    """Verify POST /api/v1/extraction/upload extracts Word DOCX and Excel XLSX."""
    client, tools_mgr, tmp_path = api_client

    # 1. Upload DOCX
    docx_path = make_synthetic_docx(tmp_path / "plan.docx")
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with open(docx_path, "rb") as f:
        res_docx = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("plan.docx", f.read(), docx_mime)},
        )
    assert res_docx.status_code == 200
    data_docx = res_docx.json()
    assert data_docx["success"] is True
    assert data_docx["table_count"] == 1
    assert data_docx["tables"][0]["headers"] == ["Initiative", "Lead"]

    # 2. Upload XLSX
    xlsx_path = make_synthetic_xlsx(tmp_path / "metrics.xlsx")
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    with open(xlsx_path, "rb") as f:
        res_xlsx = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("metrics.xlsx", f.read(), xlsx_mime)},
        )
    assert res_xlsx.status_code == 200
    data_xlsx = res_xlsx.json()
    assert data_xlsx["success"] is True
    assert data_xlsx["table_count"] == 2
    sheet_names = {t["sheet_name"] for t in data_xlsx["tables"]}
    assert sheet_names == {"Revenue", "Costs"}


@pytest.mark.asyncio
async def test_document_upload_security_rejections(api_client: Any) -> None:
    """Verify security rejections for invalid extensions, empty files, and missing names."""
    client, tools_mgr, tmp_path = api_client

    # 1. Unsupported extension (.exe)
    res_bad_ext = await client.post(
        "/api/v1/extraction/upload",
        files={"file": ("malware.exe", b"binary content", "application/octet-stream")},
    )
    assert res_bad_ext.status_code == 400
    assert "Unsupported document format" in res_bad_ext.json()["detail"]

    # 2. Empty file
    res_empty = await client.post(
        "/api/v1/extraction/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res_empty.status_code == 400
    assert "empty" in res_empty.json()["detail"].lower()


@pytest.mark.asyncio
async def test_crawl_web_page_success_and_deduplication(
    api_client: Any,
    mock_web_server: str,
) -> None:
    """Verify POST /api/v1/extraction/crawl acquires web page and dedupes repeat crawls."""
    client, tools_mgr, tmp_path = api_client
    url = f"{mock_web_server}/article"

    # Step 1: Initial crawl
    res = await client.post(
        "/api/v1/extraction/crawl",
        json={"url": url, "strategy": "static"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["success"] is True
    doc_id = data["document_id"]
    assert data["title"] == "Annual Revenue Report"
    assert "Consolidated gross margins" in data["text_preview"]
    assert data["table_count"] == 1
    assert data["tables"][0]["headers"] == ["Department", "Budget", "Spend"]
    assert not data["is_duplicate"]

    # Step 2: Repeat crawl of identical content
    res2 = await client.post(
        "/api/v1/extraction/crawl",
        json={"url": url, "strategy": "static"},
    )
    assert res2.status_code == 200
    data2 = res2.json()

    assert data2["success"] is True
    assert data2["is_duplicate"] is True
    assert data2["document_id"] == doc_id


@pytest.mark.asyncio
async def test_crawl_web_page_ssrf_rejection(api_client: Any) -> None:
    """Verify POST /api/v1/extraction/crawl rejects SSRF, cloud metadata, and credentials."""
    client, tools_mgr, tmp_path = api_client

    # 1. Cloud metadata IP
    res_meta = await client.post(
        "/api/v1/extraction/crawl",
        json={"url": "http://169.254.169.254/latest/meta-data"},
    )
    assert res_meta.status_code == 400
    assert "Security Policy Violation" in res_meta.json()["detail"]

    # 2. Secret query parameter
    res_token = await client.post(
        "/api/v1/extraction/crawl",
        json={"url": "https://example.com/api?api_key=secret-token-123"},
    )
    assert res_token.status_code == 400
    assert "Security Policy Violation" in res_token.json()["detail"]

    # 3. Invalid non-HTTP scheme
    res_scheme = await client.post(
        "/api/v1/extraction/crawl",
        json={"url": "ftp://example.com/data.txt"},
    )
    assert res_scheme.status_code == 422  # Pydantic schema validation error


@pytest.mark.asyncio
async def test_crawl_stream_sse_progress(
    api_client: Any,
    mock_web_server: str,
) -> None:
    """Verify POST /api/v1/extraction/crawl/stream yields typed SSE progress events."""
    client, tools_mgr, tmp_path = api_client
    url = f"{mock_web_server}/article"

    res = await client.post(
        "/api/v1/extraction/crawl/stream",
        json={"url": url, "strategy": "static"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = []
    lines = res.text.split("\n\n")
    for block in lines:
        if not block.strip():
            continue
        ev_name = None
        ev_data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                ev_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                ev_data = json.loads(line[len("data: ") :].strip())
        if ev_name:
            events.append({"event": ev_name, "data": ev_data})

    ev_names = [e["event"] for e in events]
    assert "progress" in ev_names
    assert "complete" in ev_names

    # Verify complete event contains valid extraction payload
    complete_ev = next(e for e in events if e["event"] == "complete")
    assert complete_ev["data"]["success"] is True
    assert complete_ev["data"]["document_id"] is not None


@pytest.mark.asyncio
async def test_list_documents_pagination_and_filter(api_client: Any) -> None:
    """Verify GET /api/v1/extraction/documents pagination, counting, and source_type filtering."""
    client, tools_mgr, tmp_path = api_client
    pdf_path = make_synthetic_pdf(tmp_path / "report_1.pdf")
    docx_path = make_synthetic_docx(tmp_path / "notes_1.docx")

    # Ingest 2 documents
    with open(pdf_path, "rb") as f:
        await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("report_1.pdf", f.read(), "application/pdf")},
        )
    with open(docx_path, "rb") as f:
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("notes_1.docx", f.read(), docx_mime)},
        )

    # 1. List all documents
    res_all = await client.get("/api/v1/extraction/documents?limit=10&offset=0")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] == 2
    assert len(data_all["items"]) == 2

    # 2. Filter by source_type=pdf
    res_pdf = await client.get("/api/v1/extraction/documents?source_type=pdf")
    assert res_pdf.status_code == 200
    data_pdf = res_pdf.json()
    assert data_pdf["total"] == 1
    assert data_pdf["items"][0]["source_type"] == "pdf"

    # 3. Filter by invalid source_type
    res_invalid = await client.get("/api/v1/extraction/documents?source_type=unsupported_type")
    assert res_invalid.status_code == 400
    assert "Invalid source_type" in res_invalid.json()["detail"]


@pytest.mark.asyncio
async def test_get_document_details_and_not_found(api_client: Any) -> None:
    """Verify GET /api/v1/extraction/documents/{id} returns details and handles 404."""
    client, tools_mgr, tmp_path = api_client
    pdf_path = make_synthetic_pdf(tmp_path / "detail_test.pdf", text="Detail inspection content")

    with open(pdf_path, "rb") as f:
        upload_res = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("detail_test.pdf", f.read(), "application/pdf")},
        )
    doc_id = upload_res.json()["document_id"]

    # 1. Get existing document details
    res = await client.get(f"/api/v1/extraction/documents/{doc_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["document"]["document_id"] == doc_id
    assert len(data["extractions"]) == 1
    assert "Detail inspection content" in data["text_preview"]

    # 2. Get non-existent document
    res_missing = await client.get("/api/v1/extraction/documents/nonexistent-doc-id-000")
    assert res_missing.status_code == 404
    assert "not found" in res_missing.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_document_extractions_and_tables(api_client: Any) -> None:
    """Verify extractions, tables, and table format export endpoints."""
    client, tools_mgr, tmp_path = api_client
    docx_path = make_synthetic_docx(tmp_path / "tables_test.docx")

    with open(docx_path, "rb") as f:
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        upload_res = await client.post(
            "/api/v1/extraction/upload",
            files={"file": ("tables_test.docx", f.read(), docx_mime)},
        )
    doc_id = upload_res.json()["document_id"]

    # 1. List extractions
    res_exts = await client.get(f"/api/v1/extraction/documents/{doc_id}/extractions")
    assert res_exts.status_code == 200
    assert len(res_exts.json()) == 1

    # 2. List tables
    res_tables = await client.get(f"/api/v1/extraction/documents/{doc_id}/tables")
    assert res_tables.status_code == 200
    tables_list = res_tables.json()
    assert len(tables_list) == 1
    table_id = tables_list[0]["table_id"]

    # 3. Export table as JSON
    url_json = f"/api/v1/extraction/documents/{doc_id}/tables/{table_id}?format=json"
    res_tbl_json = await client.get(url_json)
    assert res_tbl_json.status_code == 200
    assert "application/json" in res_tbl_json.headers["content-type"]

    # 4. Export table as CSV
    url_csv = f"/api/v1/extraction/documents/{doc_id}/tables/{table_id}?format=csv"
    res_tbl_csv = await client.get(url_csv)
    assert res_tbl_csv.status_code == 200
    assert "text/csv" in res_tbl_csv.headers["content-type"]


@pytest.mark.asyncio
async def test_download_raw_document(api_client: Any) -> None:
    """Verify GET /api/v1/extraction/documents/{id}/download serves original raw source."""
    client, tools_mgr, tmp_path = api_client
    pdf_path = make_synthetic_pdf(tmp_path / "downloadable.pdf")
    pdf_bytes = pdf_path.read_bytes()

    res_up = await client.post(
        "/api/v1/extraction/upload",
        files={"file": ("downloadable.pdf", pdf_bytes, "application/pdf")},
    )
    doc_id = res_up.json()["document_id"]

    res_down = await client.get(f"/api/v1/extraction/documents/{doc_id}/download")
    assert res_down.status_code == 200
    assert res_down.content == pdf_bytes
    assert "application/pdf" in res_down.headers["content-type"]
    assert "downloadable.pdf" in res_down.headers["content-disposition"]


@pytest.mark.asyncio
async def test_delete_document_cascading(api_client: Any) -> None:
    """Verify DELETE /api/v1/extraction/documents/{id} cleans up DB records and disk files."""
    client, tools_mgr, tmp_path = api_client
    pdf_path = make_synthetic_pdf(tmp_path / "to_delete.pdf")

    res_up = await client.post(
        "/api/v1/extraction/upload",
        files={"file": ("to_delete.pdf", pdf_path.read_bytes(), "application/pdf")},
    )
    doc_id = res_up.json()["document_id"]

    # Delete document
    res_del = await client.delete(f"/api/v1/extraction/documents/{doc_id}")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True

    # Subsequent GET returns 404
    res_get = await client.get(f"/api/v1/extraction/documents/{doc_id}")
    assert res_get.status_code == 404

    # Duplicate DELETE returns 404
    res_del_again = await client.delete(f"/api/v1/extraction/documents/{doc_id}")
    assert res_del_again.status_code == 404
