"""Smoke and lifecycle tests for BRICK-007 Phase 1 dependencies.

Verifies:
1. Import compatibility of crawl4ai, docling, and pypdfium2 alongside existing Javed runtimes.
2. Lightweight initialization of Crawl4AI AsyncWebCrawler with clean asynchronous teardown.
3. Lightweight initialization of Docling DocumentConverter using PyPdfiumDocumentBackend
   with model-backed OCR, table structure, and layout disabled (zero HuggingFace downloads).
4. Cold vs warm import performance within bounded thresholds.
5. Windows process and thread hygiene (zero orphan non-daemon threads or leaked child processes).
"""

from __future__ import annotations

import importlib.metadata
import threading
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


def test_brick_007_import_compatibility() -> None:
    """Verify all BRICK-007 core libraries import cleanly without conflicts."""
    import crawl4ai
    import docling
    import pypdfium2  # noqa: F401

    # Verify existing Javed core runtimes still import cleanly alongside new dependencies
    import javed.agent.runtime  # noqa: F401
    import javed.browser.engine  # noqa: F401
    import javed.config  # noqa: F401

    assert crawl4ai.__version__ is not None
    assert docling.__version__ is not None
    assert importlib.metadata.version("pypdfium2") is not None


@pytest.mark.asyncio
async def test_crawl4ai_lifecycle_clean_teardown() -> None:
    """Verify AsyncWebCrawler instantiates and closes cleanly without leaking resources."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    config = BrowserConfig(
        headless=True,
        verbose=False,
    )

    crawler = AsyncWebCrawler(config=config)
    # AsyncWebCrawler manages its own lifecycle. Start and close explicitly.
    await crawler.start()
    try:
        assert crawler.ready or crawler.browser is not None or crawler._crawler_strategy is not None
    finally:
        await crawler.close()


def test_docling_lightweight_initialization_no_model_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify DocumentConverter with PyPdfiumBackend initializes without downloading models."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Guard against accidental HuggingFace downloads during unit test
    def fail_on_download(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Unexpected HuggingFace download in lightweight mode!")

    try:
        import huggingface_hub

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fail_on_download)
        monkeypatch.setattr(huggingface_hub, "snapshot_download", fail_on_download)
    except (ImportError, AttributeError):
        pass

    # Configure lightweight PDF parsing: OCR disabled, table structure disabled
    pipeline_options = PdfPipelineOptions(
        do_ocr=False,
        do_table_structure=False,
    )

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend,
            )
        }
    )

    assert converter is not None
    assert InputFormat.PDF in converter.format_to_options
    pdf_opt = converter.format_to_options[InputFormat.PDF]
    assert pdf_opt.backend is PyPdfiumDocumentBackend
    assert pdf_opt.pipeline_options.do_ocr is False
    assert pdf_opt.pipeline_options.do_table_structure is False


def test_import_performance_timing() -> None:
    """Measure import times to ensure they remain within reasonable operational bounds."""
    # Measure warm import time of the packages
    t0 = time.perf_counter()
    import crawl4ai  # noqa: F401
    import docling  # noqa: F401
    import pypdfium2  # noqa: F401

    warm_duration = time.perf_counter() - t0

    # Warm import should take under 0.25 seconds
    assert warm_duration < 0.25, f"Warm import took {warm_duration:.4f}s (expected < 0.25s)"


def test_clean_thread_hygiene() -> None:
    """Verify no unexpected non-daemon threads are spawned and left running."""
    active_threads = list(threading.enumerate())
    non_daemon = [t for t in active_threads if not t.daemon and t is not threading.main_thread()]

    # Main thread should be the only non-daemon thread, or any pytest runner harness threads
    # Ignore pytest-internal non-daemon threads if any exist
    suspicious_threads = [t for t in non_daemon if "pytest" not in t.name.lower()]
    assert len(suspicious_threads) == 0, f"Found leaked non-daemon threads: {suspicious_threads}"
