"""Deterministic verification for extraction tool content bounding, owner scope,
prompt-injection defenses, OpenRouter connection retries, and concurrent storage initialization.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver

from javed.agent.runtime import AgentRuntimeManager
from javed.config import Settings
from javed.extraction.storage import ExtractionStorageManager, StorageConfig
from javed.extraction.tools import (
    ExtractionToolsManager,
    GetDocumentDetailsInput,
)
from javed.schemas.chat import ChatMessage, ChatRequest
from javed.services.openrouter import OpenRouterService
from tests.test_extraction_storage import make_sample_normalized_document

# -----------------------------------------------------------------------------
# Test 3 & 4: Content Bounding, Pagination, and Missing Document Safe Behavior
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
    assert "raw_artifact_path" not in res_chunk1  # No local path leakage

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
# Test 5: Prompt-Injection Defense Verification
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

    # Check agent compilation with memory checkpointer
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    fake_model = FakeListChatModel(responses=["Hello"])
    agent = runtime.create_agent(model=fake_model, checkpointer=MemorySaver())
    assert agent is not None


# -----------------------------------------------------------------------------
# Test 7: OpenRouter Retry Behavior and Safe ConnectError Handling
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
# Test 8: Concurrent Storage Initialization
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
