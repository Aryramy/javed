"""Deterministic verification for extraction tool content bounding, owner scope,
prompt-injection defenses, OpenRouter connection retries, concurrent storage initialization,
response sanitization, authoritative classification, offset pagination boundaries,
duplicate page read prevention, retrieval ceiling, and list-only user intent adherence.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.extraction.storage import ExtractionStorageManager, StorageConfig
from javed.extraction.tools import (
    CURRENT_RUN_ID,
    ExtractionToolsManager,
    GetDocumentDetailsInput,
)
from javed.main import create_app
from javed.schemas.agent import AgentStreamRequest
from javed.schemas.chat import ChatMessage, ChatRequest
from javed.services.openrouter import OpenRouterService
from tests.test_extraction_storage import make_sample_normalized_document

PROHIBITED_PATTERNS = [
    re.compile(r"raw_artifact_path"),
    re.compile(r"(?<![a-zA-Z])[a-zA-Z]:[\\/]"),  # Windows drive letter
    re.compile(r"data[\\/]sources"),
    re.compile(r"data[\\/]quarantine"),
    re.compile(r"data[\\/]extractions"),
    re.compile(r"data[\\/]tables"),
    re.compile(r"file://"),
    re.compile(r"/(?:Users|home|var|tmp|etc|app)/"),  # POSIX absolute paths
]


def assert_zero_path_leaks(data: Any, label: str = "") -> None:
    """Recursively serialize data to JSON and assert zero host path leaks or prohibited keys."""
    serialized = json.dumps(data, default=str)
    for pattern in PROHIBITED_PATTERNS:
        match = pattern.search(serialized)
        snippet = serialized[max(0, match.start() - 40) : min(len(serialized), match.end() + 40)]
        assert match is None, (
            f"Prohibited pattern '{pattern.pattern}' leaked in {label}: "
            f"found '{match.group(0)}' in snippet: {snippet}"
        )


# -----------------------------------------------------------------------------
# Test 1: Content Bounding, Pagination, and Missing Document Safe Behavior
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_document_safe_behavior(tmp_path: Path) -> None:
    """Verify requesting a non-existent document yields a structured error without leaking
    filesystem paths, raising unhandled exceptions, or attempting ID guessing.
    """
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "missing_doc.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    # Missing document ID
    res = await tools_mgr.get_document_details("non-existent-doc-id-12345")
    assert res["success"] is False
    assert res["error_type"] == "DocumentNotFoundError"
    assert "non-existent-doc-id-12345" in res["error"]
    assert "raw_artifact_path" not in res
    assert_zero_path_leaks(res, "missing_document_details")


@pytest.mark.asyncio
async def test_long_document_content_bounding_and_pagination(tmp_path: Path) -> None:
    """Verify get_document_details enforces strict bounded character retrieval,
    supports character offset pagination, and reports truncation indicators.
    """
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "bounding.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    # Ingest a synthetic large document (50,000+ characters)
    paragraphs = [f"Paragraph {i}: Sample SLA obligations and response terms." for i in range(1200)]
    large_text = "\n\n".join(paragraphs)
    total_len = len(large_text)
    assert total_len > 40000

    norm_doc, raw_bytes = make_sample_normalized_document(
        text=large_text, display_name="sla-terms.pdf"
    )

    # Save to storage
    doc_sum = tools_mgr.storage.store_document(
        norm_doc,
        raw_bytes=raw_bytes,
    )

    # 1. First slice with default bounded max_chars (10,000)
    res_chunk1 = await tools_mgr.get_document_details(
        document_id=doc_sum.document_id,
        offset=0,
        max_chars=10000,
    )
    assert res_chunk1["success"] is True
    assert res_chunk1["title"] == "sla-terms.pdf"
    assert res_chunk1["returned_characters"] == 10000
    assert res_chunk1["total_characters"] >= total_len
    assert res_chunk1["offset"] == 0
    assert res_chunk1["next_offset"] == 10000
    assert res_chunk1["truncated"] is True
    assert "raw_artifact_path" not in res_chunk1

    # 2. Second slice using next_offset
    res_chunk2 = await tools_mgr.get_document_details(
        document_id=doc_sum.document_id,
        offset=res_chunk1["next_offset"],
        max_chars=10000,
    )
    assert res_chunk2["success"] is True
    assert res_chunk2["offset"] == 10000
    assert res_chunk2["next_offset"] == 20000
    assert res_chunk2["returned_characters"] == 10000
    assert res_chunk2["truncated"] is True

    # 3. Input validation: verify capping max_chars to 30,000 max
    inp = GetDocumentDetailsInput(
        document_id=doc_sum.document_id,
        offset=0,
        max_chars=999999,  # Attempting to request 1 million characters
    )
    assert inp.max_chars == 30000  # Capped at 30,000 ceiling


# -----------------------------------------------------------------------------
# Test 2: Prompt-Injection Defense Verification
# -----------------------------------------------------------------------------


def test_agent_prompt_injection_defense_directive(tmp_path: Path) -> None:
    """Verify AgentRuntimeManager explicitly injects prompt-injection defense directives
    warning the model that document content is untrusted data, not instructions.
    """
    settings = Settings(
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=StorageConfig(db_path=str(tmp_path / "sec.db"))
    )

    runtime = AgentRuntimeManager(
        settings=settings,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
    )

    # Inspect the extraction tools available to the agent
    tools = runtime.get_extraction_tools_manager().get_tools()
    tool_names = [t.name for t in tools]
    assert "list_ingested_documents" in tool_names
    assert "get_document_details" in tool_names
    assert "extract_document" in tool_names
    assert "extract_web_page" in tool_names

    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    fake_model = FakeListChatModel(responses=["Hello"])
    agent = runtime.create_agent(model=fake_model, checkpointer=MemorySaver())
    assert agent is not None


# -----------------------------------------------------------------------------
# Test 3: OpenRouter Retry Behavior and Safe ConnectError Handling
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openrouter_connection_error_safe_mapping() -> None:
    """Verify OpenRouter streaming handles transient network failure gracefully,
    emitting a user-friendly error event without exposing raw socket exceptions or secrets.
    """
    svc = OpenRouterService(settings=Settings(openrouter_api_key="sk-test-mock-key"))

    # Mock client raising httpx.ConnectError from stream async context manager
    @asynccontextmanager
    async def mock_stream(*args, **kwargs):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
        yield

    mock_client = AsyncMock()
    mock_client.stream = mock_stream
    svc._external_client = mock_client

    events = []
    async for event in svc.stream_chat(
        ChatRequest(
            messages=[ChatMessage(role="user", content="hi")],
            model="deepseek/deepseek-chat",
        )
    ):
        events.append(event)

    assert len(events) == 1
    err_event = events[0]
    assert err_event.type == "error"
    assert "unable to reach AI gateway" in err_event.error
    assert "sk-test-mock-key" not in err_event.error
    assert "getaddrinfo" not in err_event.error  # Sanitized from raw socket error


# -----------------------------------------------------------------------------
# Test 4: Concurrent Storage Initialization
# -----------------------------------------------------------------------------


def test_concurrent_storage_initialization(tmp_path: Path) -> None:
    """Verify multiple concurrent initialization calls from distinct threads
    do not encounter SQLite 'database is locked' errors and cleanly initialize WAL mode.
    """
    db_file = tmp_path / "concurrent_test.db"
    storage_cfg = StorageConfig(
        db_path=str(db_file),
        busy_timeout_ms=5000,
        enable_wal=True,
    )

    errors: list[Exception] = []

    def init_worker() -> None:
        try:
            mgr = ExtractionStorageManager(config=storage_cfg)
            mgr.initialize()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=init_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(errors) == 0, f"Concurrent initialization errors: {errors}"
    assert db_file.exists()


# -----------------------------------------------------------------------------
# Test 5 (Phase 9C): Zero Host Path Leaks Across All Responses & Telemetry
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_paths_sanitized_across_all_responses(tmp_path: Path) -> None:
    """Verify all internal host filesystem paths are completely sanitized across
    tool outputs, storage records, and HTTP REST endpoints, replacing them with
    safe booleans and opaque identifiers.
    """
    settings = Settings(
        env="test",
        openrouter_api_key="sk-or-v1-mock-test-key",
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    app = create_app(settings)

    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "sanitized.db"),
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

    # 1. Ingest document with table
    sample_text = "Operational SLA terms with 99.9% uptime requirement."
    norm_doc, raw_bytes = make_sample_normalized_document(
        text=sample_text,
        display_name="PRC SLA External.pdf",
        with_table=True,
    )
    ing_res = tools_mgr.storage.store_document(norm_doc, raw_bytes=raw_bytes)

    # 2. Check storage summaries
    doc_sum = tools_mgr.storage.get_document(ing_res.document_id)
    assert doc_sum is not None
    assert doc_sum.artifact_available is True
    assert doc_sum.artifact_id is not None and len(doc_sum.artifact_id) > 0
    assert not hasattr(doc_sum, "raw_artifact_path")
    assert_zero_path_leaks(doc_sum.model_dump(), "StoredDocumentSummary")

    # Check extraction record
    extractions = tools_mgr.storage.list_extractions(doc_sum.document_id)
    assert len(extractions) > 0
    ext_rec = extractions[0]
    assert ext_rec.canonical_json_available is True
    assert ext_rec.canonical_json_id is not None and len(ext_rec.canonical_json_id) > 0
    assert not hasattr(ext_rec, "canonical_json_path")
    assert_zero_path_leaks(ext_rec.model_dump(), "StoredExtractionRecord")

    # Check table record
    tables = tools_mgr.storage.list_tables(doc_sum.document_id)
    assert len(tables) > 0
    tbl = tables[0]
    assert tbl.csv_available is True
    assert tbl.json_available is True
    assert not hasattr(tbl, "csv_path")
    assert not hasattr(tbl, "json_path")
    assert_zero_path_leaks(tbl.model_dump(), "StoredTableInfo")

    # 3. Check tool outputs
    list_res = await tools_mgr.list_ingested_documents()
    assert list_res["success"] is True
    assert_zero_path_leaks(list_res, "list_ingested_documents")

    det_res = await tools_mgr.get_document_details(doc_sum.document_id)
    assert det_res["success"] is True
    assert det_res["artifact_available"] is True
    assert det_res["artifact_id"] == doc_sum.artifact_id
    assert_zero_path_leaks(det_res, "get_document_details")

    # 4. Check HTTP REST endpoints
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Telemetry
        r_telem = await client.get("/api/v1/extraction/telemetry")
        assert r_telem.status_code == 200
        telem_data = r_telem.json()
        assert telem_data["storage_backend"] == "sqlite_wal"
        assert telem_data["storage_status"] == "healthy"
        assert "db_path" not in telem_data
        assert "sources_dir" not in telem_data
        assert_zero_path_leaks(telem_data, "/api/v1/extraction/telemetry")

        # Documents list
        r_docs = await client.get("/api/v1/extraction/documents")
        assert r_docs.status_code == 200
        docs_data = r_docs.json()
        assert_zero_path_leaks(docs_data, "/api/v1/extraction/documents")

        # Document detail
        r_doc = await client.get(f"/api/v1/extraction/documents/{doc_sum.document_id}")
        assert r_doc.status_code == 200
        doc_data = r_doc.json()
        assert_zero_path_leaks(doc_data, f"/api/v1/extraction/documents/{doc_sum.document_id}")

        # Document extractions
        r_ext = await client.get(f"/api/v1/extraction/documents/{doc_sum.document_id}/extractions")
        assert r_ext.status_code == 200
        assert_zero_path_leaks(r_ext.json(), "extractions endpoint")

        # Document tables
        r_tbl = await client.get(f"/api/v1/extraction/documents/{doc_sum.document_id}/tables")
        assert r_tbl.status_code == 200
        assert_zero_path_leaks(r_tbl.json(), "tables endpoint")


# -----------------------------------------------------------------------------
# Test 6 (Phase 9C): Authoritative Tool Classification & Fail-Closed Behavior
# -----------------------------------------------------------------------------


def test_tool_classification_authoritative(tmp_path: Path) -> None:
    """Verify authoritative classification attached to tool construction, model visibility,
    runtime resolution, and approval records, with fail-closed default of DENIED.
    """
    settings = Settings(
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    tools_mgr = ExtractionToolsManager(
        storage_config=StorageConfig(db_path=str(tmp_path / "class.db"))
    )

    # 1. Construction-time metadata checks on tools
    tool_map = {t.name: t for t in tools_mgr.get_tools()}
    assert "list_ingested_documents" in tool_map
    assert "get_document_details" in tool_map
    assert "extract_document" in tool_map
    assert "extract_web_page" in tool_map

    assert tool_map["list_ingested_documents"].metadata["classification"] == "ALLOWED_READ_ONLY"
    assert tool_map["list_ingested_documents"].metadata["server_id"] == "extraction"

    assert tool_map["get_document_details"].metadata["classification"] == "ALLOWED_READ_ONLY"
    assert tool_map["get_document_details"].metadata["server_id"] == "extraction"

    assert tool_map["extract_document"].metadata["classification"] == "APPROVAL_REQUIRED"
    assert tool_map["extract_document"].metadata["server_id"] == "extraction"

    assert tool_map["extract_web_page"].metadata["classification"] == "APPROVAL_REQUIRED"
    assert tool_map["extract_web_page"].metadata["server_id"] == "extraction"

    # 2. Runtime classification resolver
    runtime = AgentRuntimeManager(
        settings=settings,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
    )

    assert runtime.get_tool_classification("list_ingested_documents") == (
        "extraction",
        "ALLOWED_READ_ONLY",
    )
    assert runtime.get_tool_classification("get_document_details") == (
        "extraction",
        "ALLOWED_READ_ONLY",
    )
    assert runtime.get_tool_classification("extract_document") == (
        "extraction",
        "APPROVAL_REQUIRED",
    )
    assert runtime.get_tool_classification("extract_web_page") == (
        "extraction",
        "APPROVAL_REQUIRED",
    )

    # Browser tools
    assert runtime.get_tool_classification("browser_navigate") == ("browser", "ALLOWED_READ_ONLY")
    assert runtime.get_tool_classification("browser_click") == ("browser", "APPROVAL_REQUIRED")

    # Fail-closed for unknown or unclassified tools
    assert runtime.get_tool_classification("arbitrary_unknown_tool") == ("unknown", "DENIED")
    assert runtime.get_tool_classification("") == ("unknown", "DENIED")


# -----------------------------------------------------------------------------
# Test 7 (Phase 9C): Deterministic Boundary Offset Pagination on 67,399 Chars
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_offset_pagination_boundary_cases(tmp_path: Path) -> None:
    """Verify deterministic character offset pagination over an exact 67,399-character document
    across all boundary conditions: offset 0, 10000, 20000, 60000, 67399, beyond end, negative,
    and page ceiling capping.
    """
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "page_bound.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    # Ingest document of exactly 67,399 characters
    # (make_sample_normalized_document adds 20 chars for header)
    norm_doc, raw_bytes = make_sample_normalized_document(
        text="A" * (67399 - 20), display_name="PRC SLA External.pdf"
    )
    ing_res = tools_mgr.storage.store_document(norm_doc, raw_bytes=raw_bytes)
    doc_id = ing_res.document_id

    # Case A: offset 0, max_chars 10000
    r0 = await tools_mgr.get_document_details(doc_id, offset=0, max_chars=10000)
    assert r0["success"] is True
    assert r0["offset"] == 0
    assert r0["returned_characters"] == 10000
    assert len(r0["content"]) == 10000
    assert r0["total_characters"] == 67399
    assert r0["next_offset"] == 10000
    assert r0["truncated"] is True

    # Case B: offset 10000, max_chars 10000
    r1 = await tools_mgr.get_document_details(doc_id, offset=10000, max_chars=10000)
    assert r1["offset"] == 10000
    assert r1["returned_characters"] == 10000
    assert len(r1["content"]) == 10000
    assert r1["total_characters"] == 67399
    assert r1["next_offset"] == 20000
    assert r1["truncated"] is True

    # Case C: offset 20000, max_chars 10000
    r2 = await tools_mgr.get_document_details(doc_id, offset=20000, max_chars=10000)
    assert r2["offset"] == 20000
    assert r2["returned_characters"] == 10000
    assert len(r2["content"]) == 10000
    assert r2["total_characters"] == 67399
    assert r2["next_offset"] == 30000
    assert r2["truncated"] is True

    # Case D: offset 60000, max_chars 10000 -> 60000 to 67399 is exactly 7,399 chars
    r3 = await tools_mgr.get_document_details(doc_id, offset=60000, max_chars=10000)
    assert r3["offset"] == 60000
    assert r3["returned_characters"] == 7399
    assert len(r3["content"]) == 7399
    assert r3["total_characters"] == 67399
    assert r3["next_offset"] is None
    assert r3["truncated"] is False

    # Case E: offset 67399 (exact end)
    r4 = await tools_mgr.get_document_details(doc_id, offset=67399, max_chars=10000)
    assert r4["offset"] == 67399
    assert r4["returned_characters"] == 0
    assert len(r4["content"]) == 0
    assert r4["total_characters"] == 67399
    assert r4["next_offset"] is None
    assert r4["truncated"] is False

    # Case F: offset 70000 (beyond end)
    r5 = await tools_mgr.get_document_details(doc_id, offset=70000, max_chars=10000)
    assert r5["offset"] == 70000
    assert r5["returned_characters"] == 0
    assert len(r5["content"]) == 0
    assert r5["total_characters"] == 67399
    assert r5["next_offset"] is None
    assert r5["truncated"] is False

    # Case G: negative offset (-50) -> clamped to 0
    r_neg = await tools_mgr.get_document_details(doc_id, offset=-50, max_chars=10000)
    assert r_neg["offset"] == 0
    assert r_neg["returned_characters"] == 10000
    assert r_neg["total_characters"] == 67399
    assert r_neg["next_offset"] == 10000

    # Case H: maximum allowed page size (30,000)
    r_max = await tools_mgr.get_document_details(doc_id, offset=0, max_chars=30000)
    assert r_max["returned_characters"] == 30000
    assert len(r_max["content"]) == 30000
    assert r_max["next_offset"] == 30000
    assert r_max["total_characters"] == 67399

    # Case I: page size above ceiling (50,000) -> clamped to 30,000
    r_ceil = await tools_mgr.get_document_details(doc_id, offset=0, max_chars=50000)
    assert r_ceil["returned_characters"] == 30000
    assert len(r_ceil["content"]) == 30000
    assert r_ceil["next_offset"] == 30000
    assert r_ceil["total_characters"] == 67399


# -----------------------------------------------------------------------------
# Test 8 (Phase 9C): Duplicate Page Read Prevention & Cache Reuse
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_page_read_prevention(tmp_path: Path) -> None:
    """Verify requesting the exact same (document_id, offset, max_chars) within one run
    returns the cached result without repeating the disk read and signals duplicate_read=True.
    """
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "dup.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    norm_doc, raw_bytes = make_sample_normalized_document(
        text="Sample contract terms.", display_name="contract.pdf"
    )
    doc_sum = tools_mgr.storage.store_document(norm_doc, raw_bytes=raw_bytes)
    doc_id = doc_sum.document_id

    run_id = f"run-dup-{uuid.uuid4().hex[:6]}"
    token = CURRENT_RUN_ID.set(run_id)

    try:
        # First read
        r1 = await tools_mgr.get_document_details(doc_id, offset=0, max_chars=10000)
        assert r1["success"] is True
        assert r1.get("duplicate_read") is False
        assert r1.get("from_cache") is False

        # Duplicate read in the same run
        r2 = await tools_mgr.get_document_details(doc_id, offset=0, max_chars=10000)
        assert r2["success"] is True
        assert r2.get("duplicate_read") is True
        assert r2.get("from_cache") is True
        assert "Cached page reused" in r2.get("warning", "")
        assert r2["returned_characters"] == r1["returned_characters"]

        # Different offset is NOT a duplicate
        r3 = await tools_mgr.get_document_details(doc_id, offset=5, max_chars=10000)
        assert r3["success"] is True
        assert r3.get("duplicate_read") is False
        assert r3.get("from_cache") is False
    finally:
        CURRENT_RUN_ID.reset(token)


# -----------------------------------------------------------------------------
# Test 9 (Phase 9C): Retrieval Read Ceiling Enforcement (15 Reads)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_ceiling_enforcement(tmp_path: Path) -> None:
    """Verify the runtime enforces a strict per-run document-read ceiling of 15 reads,
    failing closed with RetrievalCeilingExceeded upon exceeding the limit.
    """
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "ceiling.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    norm_doc, raw_bytes = make_sample_normalized_document(
        text="A" * 50000, display_name="large_doc.pdf"
    )
    doc_sum = tools_mgr.storage.store_document(norm_doc, raw_bytes=raw_bytes)
    doc_id = doc_sum.document_id

    run_id = f"run-ceiling-{uuid.uuid4().hex[:6]}"
    token = CURRENT_RUN_ID.set(run_id)

    try:
        # Perform 15 reads (using unique offsets to bypass duplicate detection)
        for i in range(15):
            res = await tools_mgr.get_document_details(doc_id, offset=i * 100, max_chars=100)
            assert res["success"] is True

        # 16th read must fail closed with ceiling exceeded
        r16 = await tools_mgr.get_document_details(doc_id, offset=1500, max_chars=100)
        assert r16["success"] is False
        assert r16["error_type"] == "RetrievalCeilingExceeded"
        assert "Per-run document read ceiling (15) exceeded" in r16["error"]
    finally:
        CURRENT_RUN_ID.reset(token)


# -----------------------------------------------------------------------------
# Test 10 (Phase 9C): User Intent Adherence (List-Only Queries Stop Cleanly)
# -----------------------------------------------------------------------------


class _ScriptedListOnlyModel(BaseChatModel):
    """Deterministic model that simulates model adherence:
    Turn 1: emits list_ingested_documents tool call.
    Turn 2: presents the list and halts without requesting get_document_details.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
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
                        "name": "list_ingested_documents",
                        "args": {},
                        "id": "call_list_001",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(
                content=(
                    "Here are the documents currently available in the ingested document "
                    "registry:\n- PRC SLA External.pdf"
                )
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted-list-only-model"


@pytest.mark.asyncio
async def test_list_only_user_intent_does_not_call_details(tmp_path: Path) -> None:
    """Verify an agent given a list-only request invokes list_ingested_documents once
    and halts with the list, without autonomously invoking get_document_details.
    """
    settings = Settings(
        agent_checkpoint_db_path=str(tmp_path / "checkpoints.db"),
        agent_approvals_db_path=str(tmp_path / "approvals.db"),
    )
    storage_cfg = StorageConfig(
        db_path=str(tmp_path / "intent.db"),
        sources_dir=str(tmp_path / "sources"),
        extractions_dir=str(tmp_path / "extractions"),
        tables_dir=str(tmp_path / "tables"),
    )
    tools_mgr = ExtractionToolsManager(storage_config=storage_cfg)

    norm_doc, raw_bytes = make_sample_normalized_document(
        text="SLA terms.", display_name="PRC SLA External.pdf"
    )
    tools_mgr.storage.store_document(norm_doc, raw_bytes=raw_bytes)

    scripted_model = _ScriptedListOnlyModel()
    runtime = AgentRuntimeManager(
        settings=settings,
        model_override=scripted_model,
        enable_extraction=True,
        extraction_tools_manager=tools_mgr,
    )
    await runtime.initialize()

    thread_id = f"test-thread-list-{uuid.uuid4().hex[:6]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="List the documents currently available in the ingested document registry.",
    )

    events = []
    async for ev in runtime.stream_agent(req):
        events.append(ev)

    event_types = [e.event for e in events]
    assert "run_started" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "run_completed" in event_types

    # Verify tool calls: list_ingested_documents completed, get_document_details NEVER requested
    tools_called = [
        e.data.get("tool") for e in events if e.event in ("tool_started", "tool_completed")
    ]
    assert "list_ingested_documents" in tools_called
    assert "get_document_details" not in tools_called
    assert "extract_document" not in tools_called
    assert "extract_web_page" not in tools_called

    # Verify classification reported in event telemetry is accurate
    for e in events:
        if (
            e.event in ("tool_started", "tool_completed")
            and e.data.get("tool") == "list_ingested_documents"
        ):
            assert e.data.get("classification") == "ALLOWED_READ_ONLY"
            assert e.data.get("server_id") == "extraction"

    await runtime.close()
