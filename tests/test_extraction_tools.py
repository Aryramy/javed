"""Comprehensive tests for BRICK-007 Phase 7: LangChain Agent Extraction Tools & HITL Gating.

Validates:
1. Tool inventory and schema contracts for all 4 extraction tools.
2. extract_web_page execution with SSRF defense, static/rendered strategies, and persistence.
3. extract_document execution with PDF, DOCX, and XLSX support.
4. Path safety: directory traversal rejection, boundary containment, unsupported formats,
   and missing files.
5. Ingestion deduplication through tools: identical content reuses document ID and flags duplicate.
6. list_ingested_documents pagination, counts, and source_type filtering.
7. get_document_details retrieval of metadata, tables, extraction records, and canonical text.
8. Clean resource lifecycle and thread hygiene on close.
9. Agent runtime integration:
   - Tool visibility and positive allowlist exposure when enable_extraction is True.
   - Tool execution blocking when enable_extraction is False.
   - Multi-step scripted agent execution invoking extraction tools.
   - HITL approval interruption and resumption for extract_document.
   - HITL rejection preventing document extraction.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import docx
import openpyxl
import pytest
from aiohttp import web
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from javed.agent.runtime import AgentRuntimeManager
from javed.agent.security import (
    ALLOWED_TOOLS,
    EXTRACTION_TOOLS,
    PositiveToolAllowlistMiddleware,
    assert_safe_tools,
)
from javed.config import Settings
from javed.extraction import (
    ExtractDocumentInput,
    ExtractionToolsManager,
    ExtractWebPageInput,
    GetDocumentDetailsInput,
    ListIngestedDocumentsInput,
    StorageConfig,
    create_extraction_tools_inventory,
)
from javed.schemas.agent import AgentStreamRequest

# -----------------------------------------------------------------------------
# Test Fixtures & Synthetic File Generators
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
async def local_mock_web_server(web_server_port: int):
    """Run an ephemeral aiohttp mock web server on loopback."""
    app = web.Application()

    async def handle_article(request: web.Request) -> web.Response:
        html = """<!DOCTYPE html>
<html>
<head><title>Quarterly Financial Briefing</title></head>
<body>
    <h1>Executive Summary</h1>
    <p>Operational revenues expanded by 14% over baseline targets.</p>
    <table>
        <thead><tr><th>Quarter</th><th>Revenue</th><th>Growth</th></tr></thead>
        <tbody>
            <tr><td>Q1</td><td>$1.2M</td><td>10%</td></tr>
            <tr><td>Q2</td><td>$1.4M</td><td>14%</td></tr>
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


def make_synthetic_pdf(target_path: Path, lines: list[str] | None = None) -> Path:
    """Generate minimal valid PDF 1.4 file."""
    text_lines = lines or ["Quarterly Performance Report", "Operating income totaled $4.2M."]
    text_commands = []
    y_pos = 720
    for line in text_lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_commands.append(f"1 0 0 1 72 {y_pos} Tm ({escaped}) Tj")
        y_pos -= 24

    stream_content = "BT\n/F1 12 Tf\n" + "\n".join(text_commands) + "\nET\n"
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
    """Generate minimal valid Word .docx file with heading and table."""
    doc = docx.Document()
    doc.add_heading("Product Strategy Document", level=1)
    doc.add_paragraph("Key strategic pillars for the upcoming fiscal cycle.")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "Pillar"
    tbl.cell(0, 1).text = "Owner"
    tbl.cell(1, 0).text = "Platform Security"
    tbl.cell(1, 1).text = "Core Team"
    doc.save(str(target_path))
    return target_path


def make_synthetic_xlsx(target_path: Path) -> Path:
    """Generate minimal valid Excel .xlsx file with multiple sheets."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Financials"
    ws1.append(["Account", "Balance"])
    ws1.append(["Checking", 15400])

    ws2 = wb.create_sheet(title="Headcount")
    ws2.append(["Department", "FTE"])
    ws2.append(["Engineering", 42])

    wb.save(str(target_path))
    return target_path


@pytest.fixture
def extraction_env(tmp_path: Path) -> tuple[ExtractionToolsManager, StorageConfig]:
    """Provide isolated ExtractionToolsManager with isolated SQLite storage in temp dir."""
    config = StorageConfig(
        db_path=str(tmp_path / "extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    manager = ExtractionToolsManager(
        storage_config=config,
        allowed_document_roots=[tmp_path],
        allow_loopback_for_testing=True,
    )
    yield manager, config
    manager.close()


# -----------------------------------------------------------------------------
# Unit Tests: Inventory & Schema Validation
# -----------------------------------------------------------------------------


def test_extraction_tools_inventory_creation() -> None:
    """Verify tool factory creates the 4 expected structured tools."""
    tools = create_extraction_tools_inventory()
    assert len(tools) == 4
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "extract_web_page",
        "extract_document",
        "list_ingested_documents",
        "get_document_details",
    }


def test_input_schema_validation() -> None:
    """Verify Pydantic input schemas enforce types, limits, and defaults."""
    # Web page input
    w_in = ExtractWebPageInput(url="https://example.com/test", strategy="STATIC")
    assert w_in.strategy == "static"
    assert w_in.max_chars == 25000

    with pytest.raises(ValueError, match="strategy must be either"):
        ExtractWebPageInput(url="https://example.com", strategy="invalid_strategy")

    with pytest.raises(ValueError, match="max_chars must be strictly positive"):
        ExtractWebPageInput(url="https://example.com", max_chars=0)

    # Document input
    d_in = ExtractDocumentInput(file_path="C:/data/test.pdf")
    assert d_in.file_path == "C:/data/test.pdf"

    with pytest.raises(ValueError, match="file_path cannot be empty"):
        ExtractDocumentInput(file_path="   ")

    with pytest.raises(ValueError, match="null bytes"):
        ExtractDocumentInput(file_path="test\x00.pdf")

    # List documents input
    l_in = ListIngestedDocumentsInput(limit=50, offset=10, source_type="pdf")
    assert l_in.limit == 50
    assert l_in.offset == 10
    assert l_in.source_type == "pdf"

    # Limit capped at 100
    l_capped = ListIngestedDocumentsInput(limit=200)
    assert l_capped.limit == 100

    # Details input
    dt_in = GetDocumentDetailsInput(document_id="doc_123")
    assert dt_in.document_id == "doc_123"
    assert dt_in.include_text is True


# -----------------------------------------------------------------------------
# Functional Tests: Tool Execution via ExtractionToolsManager
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_web_page_tool(
    local_mock_web_server: str,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify extract_web_page fetches web content, creates DB row, and returns summary."""
    manager, config = extraction_env
    url = f"{local_mock_web_server}/article"

    res = await manager.extract_web_page(url=url, strategy="static")

    assert res["success"] is True
    assert res["document_id"] is not None
    assert res["title"] == "Quarterly Financial Briefing"
    assert not res["is_duplicate"]
    assert res["table_count"] == 1
    assert len(res["tables"]) == 1
    assert res["tables"][0]["headers"] == ["Quarter", "Revenue", "Growth"]
    assert "Operational revenues expanded" in res["text_preview"]

    # Deduplication test: extract same URL again with identical content
    res2 = await manager.extract_web_page(url=url, strategy="static")
    assert res2["success"] is True
    assert res2["is_duplicate"] is True
    assert res2["document_id"] == res["document_id"]


@pytest.mark.asyncio
async def test_extract_web_page_ssrf_blocking(
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify extract_web_page strictly blocks private network and metadata URLs."""
    manager, config = extraction_env

    # Cloud metadata IP
    res = await manager.extract_web_page(url="http://169.254.169.254/latest/meta-data")
    assert res["success"] is False
    assert "Security Policy Violation" in res["error"]

    # Secret-bearing query parameter
    res2 = await manager.extract_web_page(url="https://example.com/api?token=secret123")
    assert res2["success"] is False
    assert "Security Policy Violation" in res2["error"]


@pytest.mark.asyncio
async def test_extract_document_pdf(
    tmp_path: Path,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify extract_document parses synthetic PDF, stores artifacts, and returns tables/text."""
    manager, config = extraction_env
    pdf_path = make_synthetic_pdf(tmp_path / "report.pdf")

    res = await manager.extract_document(file_path=str(pdf_path))

    assert res["success"] is True
    assert res["mime_type"] == "application/pdf"
    assert res["page_count"] == 1
    assert "Operating income totaled $4.2M" in res["text_preview"]

    # Re-extracting identical file flags is_duplicate=True
    res_dup = await manager.extract_document(file_path=str(pdf_path))
    assert res_dup["success"] is True
    assert res_dup["is_duplicate"] is True
    assert res_dup["document_id"] == res["document_id"]


@pytest.mark.asyncio
async def test_extract_document_docx(
    tmp_path: Path,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify extract_document parses synthetic DOCX with headings and tables."""
    manager, config = extraction_env
    docx_path = make_synthetic_docx(tmp_path / "strategy.docx")

    res = await manager.extract_document(file_path=str(docx_path))

    assert res["success"] is True
    assert "wordprocessingml.document" in res["mime_type"]
    assert res["title"] == "Product Strategy Document"
    assert res["table_count"] == 1
    assert res["tables"][0]["headers"] == ["Pillar", "Owner"]


@pytest.mark.asyncio
async def test_extract_document_xlsx(
    tmp_path: Path,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify extract_document parses synthetic XLSX multi-sheet tables."""
    manager, config = extraction_env
    xlsx_path = make_synthetic_xlsx(tmp_path / "data.xlsx")

    res = await manager.extract_document(file_path=str(xlsx_path))

    assert res["success"] is True
    assert res["table_count"] == 2
    sheet_names = {t["sheet_name"] for t in res["tables"]}
    assert sheet_names == {"Financials", "Headcount"}


@pytest.mark.asyncio
async def test_extract_document_security_boundaries(
    tmp_path: Path,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify path traversal rejection, unsupported formats, and missing files."""
    manager, config = extraction_env

    # 1. Path escaping allowed root
    outside_dir = tmp_path.parent / "unauthorized_outside"
    outside_dir.mkdir(exist_ok=True)
    outside_pdf = make_synthetic_pdf(outside_dir / "secret.pdf")

    res_traversal = await manager.extract_document(file_path=str(outside_pdf))
    assert res_traversal["success"] is False
    assert "Security Policy Violation" in res_traversal["error"]
    assert "escapes allowed directories" in res_traversal["error"]

    # 2. Unsupported extension
    bad_ext_file = tmp_path / "script.exe"
    bad_ext_file.write_text("not a document")
    res_bad_ext = await manager.extract_document(file_path=str(bad_ext_file))
    assert res_bad_ext["success"] is False
    assert "Unsupported document format" in res_bad_ext["error"]

    # 3. Nonexistent file
    res_missing = await manager.extract_document(file_path=str(tmp_path / "missing.pdf"))
    assert res_missing["success"] is False
    assert "FileNotFoundError" in res_missing["error_type"]


@pytest.mark.asyncio
async def test_list_and_details_tools(
    tmp_path: Path,
    extraction_env: tuple[ExtractionToolsManager, StorageConfig],
) -> None:
    """Verify list_ingested_documents and get_document_details operations."""
    manager, config = extraction_env
    pdf_path = make_synthetic_pdf(tmp_path / "audit.pdf")
    docx_path = make_synthetic_docx(tmp_path / "notes.docx")

    res_pdf = await manager.extract_document(file_path=str(pdf_path))
    res_docx = await manager.extract_document(file_path=str(docx_path))
    assert res_docx["success"] is True

    # List all documents
    list_all = await manager.list_ingested_documents(limit=10)
    assert list_all["success"] is True
    assert list_all["count"] == 2

    # Filter by source_type
    list_pdf = await manager.list_ingested_documents(source_type="pdf")
    assert list_pdf["success"] is True
    assert list_pdf["count"] == 1
    assert list_pdf["documents"][0]["document_id"] == res_pdf["document_id"]

    # Filter by invalid source_type
    list_invalid = await manager.list_ingested_documents(source_type="invalid_type")
    assert list_invalid["success"] is False
    assert "Invalid source_type" in list_invalid["error"]

    # Get details for existing document
    details = await manager.get_document_details(
        document_id=res_pdf["document_id"], include_text=True
    )
    assert details["success"] is True
    assert details["document_id"] == res_pdf["document_id"]
    assert details["mime_type"] == "application/pdf"
    assert "Operating income" in details["text_content"]

    # Get details for nonexistent document
    details_none = await manager.get_document_details(document_id="nonexistent-id-000")
    assert details_none["success"] is False
    assert "not found" in details_none["error"]


# -----------------------------------------------------------------------------
# Agent Runtime Integration Tests
# -----------------------------------------------------------------------------


def test_positive_tool_allowlist_extraction_exposure() -> None:
    """Verify PositiveToolAllowlistMiddleware exposes EXTRACTION_TOOLS only when enabled."""
    # When disabled: extraction tools are invisible and blocked
    mw_disabled = PositiveToolAllowlistMiddleware(enable_extraction=False)
    visible_disabled = mw_disabled._get_model_visible_tools()
    assert visible_disabled == ALLOWED_TOOLS
    assert "extract_web_page" not in visible_disabled

    # When enabled: extraction tools are visible and executable
    mw_enabled = PositiveToolAllowlistMiddleware(enable_extraction=True)
    visible_enabled = mw_enabled._get_model_visible_tools()
    assert visible_enabled == (ALLOWED_TOOLS | EXTRACTION_TOOLS)
    assert "extract_web_page" in visible_enabled
    assert "extract_document" in visible_enabled


def test_assert_safe_tools_with_extraction() -> None:
    """Verify assert_safe_tools accepts extraction tools when enable_extraction is True."""
    tools_dict = {
        "write_todos": MagicMock(),
        "extract_web_page": MagicMock(),
        "extract_document": MagicMock(),
    }

    # Fails if enable_extraction is False
    with pytest.raises(PermissionError, match="Unauthorized tools in agent registry"):
        assert_safe_tools(tools_dict, enable_extraction=False)

    # Passes when enable_extraction is True
    assert_safe_tools(tools_dict, enable_extraction=True)


class _ScriptedExtractionModel(BaseChatModel):
    """Deterministic scripted model that invokes extract_web_page on turn 1."""

    def __init__(self, target_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target_url = target_url
        self._turn_count = 0

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self._turn_count += 1
        if self._turn_count == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "extract_web_page",
                        "args": {"url": self._target_url, "strategy": "static"},
                        "id": "call_ext_001",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Extracted report content successfully.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-extraction-test-model"


@pytest.mark.asyncio
async def test_agent_e2e_web_extraction(
    tmp_path: Path,
    local_mock_web_server: str,
) -> None:
    """Verify agent invokes extract_web_page tool and completes streaming execution."""
    url = f"{local_mock_web_server}/article"
    model = _ScriptedExtractionModel(target_url=url)

    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "agent_extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=storage_cfg,
        allow_loopback_for_testing=True,
    )

    runtime = AgentRuntimeManager(
        settings=Settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
            agent_approvals_db_path=str(tmp_path / "approvals.db"),
        ),
        model_override=model,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
        extraction_approval_required=False,
    )
    await runtime.initialize()

    try:
        events = []
        req = AgentStreamRequest(thread_id="test-ext-thread-01", message="Please extract article")
        async for ev in runtime.stream_agent(req):
            events.append(ev)

        ev_types = [e.event for e in events]
        assert "run_started" in ev_types
        assert "tool_started" in ev_types
        assert "tool_completed" in ev_types
        assert "run_completed" in ev_types

        # Verify tool activity recorded in thread
        state = await runtime.get_thread_state("test-ext-thread-01")
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "extract_web_page"
        assert state.tool_calls[0].status == "COMPLETED"

    finally:
        await runtime.close()


class _ScriptedDocumentExtractionModel(BaseChatModel):
    """Deterministic scripted model that invokes extract_document."""

    def __init__(self, file_path: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._file_path = file_path
        self._turn_count = 0

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self._turn_count += 1
        if self._turn_count == 1:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "extract_document",
                        "args": {"file_path": self._file_path},
                        "id": "call_doc_001",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="Document parsed and verified successfully.")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-doc-extraction-model"


@pytest.mark.asyncio
async def test_agent_hitl_approval_interruption_and_resumption_for_extract_document(
    tmp_path: Path,
) -> None:
    """Verify extract_document halts at HITL approval gate and executes upon human approval."""
    pdf_path = make_synthetic_pdf(tmp_path / "financial.pdf")
    model = _ScriptedDocumentExtractionModel(file_path=str(pdf_path))

    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "hitl_extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=storage_cfg,
        allowed_document_roots=[tmp_path],
    )

    runtime = AgentRuntimeManager(
        settings=Settings(
            agent_checkpoint_db_path=str(tmp_path / "hitl_checkpoints.db"),
            agent_approvals_db_path=str(tmp_path / "hitl_approvals.db"),
        ),
        model_override=model,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
        extraction_approval_required=True,
    )
    await runtime.initialize()

    try:
        # Step 1: Execute agent run -> must halt with approval_required event
        events_phase1 = []
        req1 = AgentStreamRequest(thread_id="hitl-doc-thread", message="Read financial PDF")
        async for ev in runtime.stream_agent(req1):
            events_phase1.append(ev)

        ev_types = [e.event for e in events_phase1]
        assert "approval_required" in ev_types
        approval_events = [e for e in events_phase1 if e.event == "approval_required"]
        assert len(approval_events) == 1
        approval_id = approval_events[0].data["approval_id"]

        # Verify approval record created in store
        approval = await runtime.approval_store.get_approval(approval_id)
        assert approval is not None
        assert approval.tool_id == "extract_document"
        assert approval.status == "pending"

        # Step 2: Grant human approval and resume execution via resume_agent
        events_phase2 = []
        async for ev in runtime.resume_agent(
            thread_id="hitl-doc-thread",
            approval_id=approval_id,
            decision="approve",
            reason="Operator verified target document",
        ):
            events_phase2.append(ev)

        p2_types = [e.event for e in events_phase2]
        assert "approval_approved" in p2_types
        assert "agent_resumed" in p2_types
        assert "tool_completed" in p2_types
        assert "run_completed" in p2_types

        # Verify completed execution state
        state = await runtime.get_thread_state("hitl-doc-thread")
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].tool_name == "extract_document"
        assert state.tool_calls[0].status == "APPROVED"

    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agent_hitl_rejection_for_extract_document(
    tmp_path: Path,
) -> None:
    """Verify human rejection prevents extract_document dispatch."""
    pdf_path = make_synthetic_pdf(tmp_path / "private.pdf")
    model = _ScriptedDocumentExtractionModel(file_path=str(pdf_path))

    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "hitl_rej_extraction.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=storage_cfg,
        allowed_document_roots=[tmp_path],
    )

    runtime = AgentRuntimeManager(
        settings=Settings(
            agent_checkpoint_db_path=str(tmp_path / "rej_checkpoints.db"),
            agent_approvals_db_path=str(tmp_path / "rej_approvals.db"),
        ),
        model_override=model,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
        extraction_approval_required=True,
    )
    await runtime.initialize()

    try:
        # Step 1: Run halts with approval_required
        events_phase1 = []
        req1 = AgentStreamRequest(thread_id="rej-doc-thread", message="Read private PDF")
        async for ev in runtime.stream_agent(req1):
            events_phase1.append(ev)

        approval_events = [e for e in events_phase1 if e.event == "approval_required"]
        assert len(approval_events) == 1
        approval_id = approval_events[0].data["approval_id"]

        # Step 2: Human rejects and resumes via resume_agent
        events_resume = []
        async for ev in runtime.resume_agent(
            thread_id="rej-doc-thread",
            approval_id=approval_id,
            decision="reject",
            reason="Access to private PDF denied by policy",
        ):
            events_resume.append(ev)

        p2_types = [e.event for e in events_resume]
        assert "approval_rejected" in p2_types
        assert "agent_resumed" in p2_types
        assert "run_completed" in p2_types

        # Verify tool was marked rejected in approval store
        appr_rec = await runtime.approval_store.get_approval(approval_id)
        assert appr_rec is not None
        assert appr_rec.status == "rejected"

        # Verify tool was recorded in thread state
        state = await runtime.get_thread_state("rej-doc-thread")
        assert len(state.tool_calls) == 1
        assert state.tool_calls[0].status == "FAILED"

    finally:
        await runtime.close()


def test_thread_and_process_hygiene(tmp_path: Path) -> None:
    """Verify ExtractionToolsManager shuts down cleanly without leaving background threads."""
    initial_threads = {t.name for t in threading.enumerate()}

    storage_cfg = StorageConfig(db_path=str(tmp_path / "hygiene.db"))
    manager = ExtractionToolsManager(storage_config=storage_cfg)

    # Initialize components
    _ = manager.get_web_extractor()
    _ = manager.get_doc_extractor()
    manager.close()

    active_threads = {t.name for t in threading.enumerate()}
    leaked_threads = active_threads - initial_threads
    # Disregard pytest/asyncio internal worker threads if any
    relevant_leaks = [t for t in leaked_threads if "javed" in t.lower() or "crawl" in t.lower()]
    assert not relevant_leaks, f"Detected leaked background threads: {relevant_leaks}"
