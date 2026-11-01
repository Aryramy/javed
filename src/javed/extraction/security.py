"""Defensive extraction security guard, quarantine manager, and format validator.

Implements the zero-trust defensive ingestion boundary for BRICK-007 Phase 3:
1. Strict file size enforcement (25 MB default, 50 MB governance maximum ceiling).
2. MIME, magic bytes, and extension whitelist verification.
3. UUID-isolated quarantine staging with path containment and atomic exclusive creation.
4. Office ZIP container inspection (entry count, compression ratio, expanded bytes, traversal).
5. Lightweight PDF preflight (magic bytes, page limit, password detection, active content scan).
6. Plain text and HTML active content classification.
7. Path, name, NTFS stream, and Windows device name rejection.
8. Zero heavy runtime imports (zero crawl4ai, zero docling, zero torch, zero database).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import io
import logging
import re
import threading
import time
import uuid
import zipfile
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO

import pypdfium2

from javed.extraction.schema import (
    ExtractionBaseModel,
    ExtractionErrorCode,
    SourceType,
)

logger = logging.getLogger("javed.extraction.security")

# -----------------------------------------------------------------------------
# Constants & Governance Boundaries
# -----------------------------------------------------------------------------

DEFAULT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_GOVERNANCE_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB strict maximum
DEFAULT_MAX_PDF_PAGES = 200
DEFAULT_MAX_OFFICE_ENTRIES = 1000
DEFAULT_MAX_OFFICE_ENTRY_UNCOMPRESSED_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_MAX_OFFICE_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_OFFICE_COMPRESSION_RATIO = 100.0  # 100:1 max ratio
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_CONCURRENT_INSPECTIONS = 5

CHUNK_SIZE = 64 * 1024  # 64 KB read buffer

# Windows Reserved Device Names (case-insensitive)
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Magic Signatures
MAGIC_PDF = b"%PDF-"
MAGIC_ZIP = b"PK\x03\x04"
MAGIC_MZ = b"MZ"
MAGIC_ELF = b"\x7fELF"
MAGIC_7Z = b"7z\xbc\xaf\x27\x1c"
MAGIC_RAR = b"Rar!\x1a\x07"
MAGIC_GZIP = b"\x1f\x8b"

# Active HTML Content Indicators
ACTIVE_HTML_PATTERNS = [
    re.compile(rb"<\s*script\b", re.IGNORECASE),
    re.compile(rb"<\s*iframe\b", re.IGNORECASE),
    re.compile(rb"<\s*object\b", re.IGNORECASE),
    re.compile(rb"<\s*embed\b", re.IGNORECASE),
    re.compile(rb"\bon[a-z]+\s*=", re.IGNORECASE),
    re.compile(rb"javascript\s*:", re.IGNORECASE),
]

# Active PDF Content Indicators
ACTIVE_PDF_PATTERNS = [
    (b"/JS", "PDF embedded JavaScript marker (/JS)"),
    (b"/JavaScript", "PDF embedded JavaScript action (/JavaScript)"),
    (b"/Launch", "PDF external process launch action (/Launch)"),
    (b"/EmbeddedFiles", "PDF embedded file stream (/EmbeddedFiles)"),
]

# Prohibited filename characters
PROHIBITED_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f:*?\"<>|]")


# -----------------------------------------------------------------------------
# Decision Outcomes and Security Models
# -----------------------------------------------------------------------------


class SecurityDecisionOutcome(StrEnum):
    """Possible outcomes of the security inspection."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    INSPECTION_FAILED = "inspection_failed"


class SecurityGuardConfig(ExtractionBaseModel):
    """Configuration contracts for ExtractionSecurityGuard."""

    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES
    max_office_entries: int = DEFAULT_MAX_OFFICE_ENTRIES
    max_office_entry_uncompressed_bytes: int = DEFAULT_MAX_OFFICE_ENTRY_UNCOMPRESSED_BYTES
    max_office_total_uncompressed_bytes: int = DEFAULT_MAX_OFFICE_TOTAL_UNCOMPRESSED_BYTES
    max_office_compression_ratio: float = DEFAULT_MAX_OFFICE_COMPRESSION_RATIO
    preflight_timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS
    max_concurrent_inspections: int = DEFAULT_MAX_CONCURRENT_INSPECTIONS
    quarantine_root: str = "data/quarantine"

    def model_post_init(self, __context: Any) -> None:
        if self.max_file_size_bytes > MAX_GOVERNANCE_FILE_SIZE_BYTES:
            msg = (
                f"max_file_size_bytes ({self.max_file_size_bytes}) exceeds "
                f"governance ceiling of {MAX_GOVERNANCE_FILE_SIZE_BYTES} bytes (50 MB)"
            )
            raise ValueError(msg)
        if self.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be strictly positive")
        if self.max_pdf_pages <= 0:
            raise ValueError("max_pdf_pages must be strictly positive")
        if self.max_office_compression_ratio < 1.0:
            raise ValueError("max_office_compression_ratio must be at least 1.0")


class SecurityValidationDecision(ExtractionBaseModel):
    """Structured security validation decision returned by the guard."""

    outcome: SecurityDecisionOutcome
    source_type: SourceType
    verified_mime_type: str
    byte_count: int
    content_sha256: str
    sanitized_display_name: str
    quarantine_path: str | None = None
    page_count: int | None = None
    archive_entry_count: int | None = None
    error_code: ExtractionErrorCode | None = None
    error_message: str | None = None
    warnings: list[str] = []

    def safe_log_dict(self) -> dict[str, Any]:
        """Produce safe metadata dictionary strictly excluding document contents or paths."""
        return {
            "outcome": self.outcome.value,
            "source_type": self.source_type.value,
            "verified_mime_type": self.verified_mime_type,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
            "sanitized_display_name": self.sanitized_display_name,
            "page_count": self.page_count,
            "archive_entry_count": self.archive_entry_count,
            "error_code": self.error_code.value if self.error_code else None,
            "warning_count": len(self.warnings),
        }


# -----------------------------------------------------------------------------
# Quarantine Manager
# -----------------------------------------------------------------------------


class QuarantineManager:
    """Manages secure staging, path containment, and lifecycle of quarantined inputs."""

    def __init__(self, quarantine_root: str | Path = "data/quarantine") -> None:
        self.root = Path(quarantine_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._active_files: dict[str, Path] = {}
        self._lock = threading.Lock()

    def generate_quarantine_path(self, safe_extension: str) -> Path:
        """Generate a UUID-based quarantine path verified for strict directory containment."""
        ext = safe_extension if safe_extension.startswith(".") else f".{safe_extension}"
        quarantine_id = uuid.uuid4()
        target = (self.root / f"{quarantine_id}{ext}").resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Generated quarantine path escapes quarantine root")
        return target

    def stage_stream(
        self,
        stream: BinaryIO,
        safe_extension: str,
        max_bytes: int,
        inspection_id: str | None = None,
    ) -> tuple[Path, int, str]:
        """Atomically stage a stream into quarantine with streaming SHA-256 and size checks.

        Returns (quarantine_path, bytes_written, sha256_hex).
        Cleans up immediately if max_bytes is exceeded or an exception occurs.
        """
        target_path = self.generate_quarantine_path(safe_extension)
        if inspection_id:
            with self._lock:
                self._active_files[inspection_id] = target_path

        bytes_written = 0
        hasher = hashlib.sha256()

        try:
            # Use 'xb' for exclusive creation (fail if file exists, prevents overwrite)
            with open(target_path, "xb") as out_f:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        out_f.close()
                        self.cleanup(target_path)
                        raise ValueError(
                            f"Input size ({bytes_written} bytes) exceeds maximum limit "
                            f"({max_bytes} bytes)"
                        )
                    hasher.update(chunk)
                    out_f.write(chunk)

            if bytes_written == 0:
                self.cleanup(target_path)
                raise ValueError("Input stream contains 0 bytes (empty input)")

            return target_path, bytes_written, hasher.hexdigest()

        except Exception:
            self.cleanup(target_path)
            raise

    def stage_bytes(
        self,
        data: bytes,
        safe_extension: str,
        max_bytes: int,
        inspection_id: str | None = None,
    ) -> tuple[Path, int, str]:
        """Atomically stage in-memory bytes into quarantine with bounded checks."""
        if len(data) > max_bytes:
            raise ValueError(
                f"Input size ({len(data)} bytes) exceeds maximum limit ({max_bytes} bytes)"
            )
        if len(data) == 0:
            raise ValueError("Input bytes are empty (0 bytes)")

        return self.stage_stream(
            io.BytesIO(data),
            safe_extension,
            max_bytes,
            inspection_id=inspection_id,
        )

    def cleanup(self, path: Path | str | None) -> None:
        """Safely delete a quarantined file ensuring containment within quarantine root."""
        if not path:
            return
        p = Path(path).resolve()
        with self._lock:
            for k, v in list(self._active_files.items()):
                if v == p:
                    self._active_files.pop(k, None)
        try:
            if p.is_relative_to(self.root) and p.is_file():
                p.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Failed to clean up quarantine path: %s", type(e).__name__)

    def cleanup_inspection(self, inspection_id: str | None) -> None:
        """Safely clean up any quarantined file associated with an inspection ID."""
        if not inspection_id:
            return
        with self._lock:
            target = self._active_files.pop(inspection_id, None)
        if target:
            self.cleanup(target)

    def is_inspection_active(self, inspection_id: str | None) -> bool:
        """Check if an inspection ID is actively tracked and not cleaned up or aborted."""
        if not inspection_id:
            return True
        with self._lock:
            return inspection_id in self._active_files

    def cleanup_all_active(self) -> int:
        """Purge all currently tracked active quarantine files."""
        with self._lock:
            targets = list(self._active_files.values())
            self._active_files.clear()
        count = 0
        for target in targets:
            try:
                if target.is_relative_to(self.root) and target.is_file():
                    target.unlink(missing_ok=True)
                    count += 1
            except Exception:
                pass
        return count


# -----------------------------------------------------------------------------
# Name & Path Sanitization
# -----------------------------------------------------------------------------


def sanitize_and_validate_display_name(raw_name: str) -> str:
    """Validate and sanitize original display name, rejecting traversal and device names."""
    if not raw_name or not raw_name.strip():
        raise ValueError("Display name cannot be empty")

    name = raw_name.strip()

    # Reject null bytes and control characters
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError("Filename contains prohibited control characters")

    # Reject path separators, absolute paths, and UNC paths
    if "/" in name or "\\" in name:
        raise ValueError("Filename contains path separator characters")
    if name.startswith("//") or name.startswith("\\\\"):
        raise ValueError("UNC paths are strictly prohibited")
    if re.match(r"^[a-zA-Z]:", name):
        raise ValueError("Drive letter paths are strictly prohibited")

    # Reject path traversal segments
    if ".." in name:
        raise ValueError("Path traversal segments ('..') are strictly prohibited")

    # Reject trailing dot or trailing space (causes Windows path ambiguity)
    if raw_name.endswith(".") or raw_name.endswith(" "):
        raise ValueError("Trailing dots and spaces are prohibited in filenames")

    # Reject NTFS Alternate Data Stream syntax
    if ":" in name:
        raise ValueError("NTFS Alternate Data Stream syntax is strictly prohibited")

    # Reject trailing dot or trailing space (causes Windows path ambiguity)
    if name.endswith(".") or name.endswith(" "):
        raise ValueError("Trailing dots and spaces are prohibited in filenames")

    # Reject Windows reserved device names
    stem = Path(name).stem.upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise ValueError(f"Reserved Windows device name prohibited: {stem}")

    # Bounded length
    if len(name) > 255:
        raise ValueError("Filename exceeds 255 characters limit")

    return name


# -----------------------------------------------------------------------------
# Extraction Security Guard
# -----------------------------------------------------------------------------


class ExtractionSecurityGuard:
    """Enforces zero-trust pre-parser validation for all ingested content."""

    def __init__(
        self,
        config: SecurityGuardConfig | None = None,
    ) -> None:
        self.config = config or SecurityGuardConfig()
        self.quarantine_mgr = QuarantineManager(self.config.quarantine_root)
        self._semaphore = threading.Semaphore(self.config.max_concurrent_inspections)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(self.config.max_concurrent_inspections * 2, 4),
            thread_name_prefix="javed-extraction-guard",
        )
        self._closed = False

    def close(self) -> None:
        """Shut down background worker pool."""
        if not self._closed:
            self._closed = True
            self._executor.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> ExtractionSecurityGuard:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Explicit Inspection Entry Points (Preferred over ambiguous string inputs)
    # -------------------------------------------------------------------------

    def validate_bytes(
        self,
        data: bytes,
        original_filename: str,
        declared_mime: str | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Explicit entry point: validate in-memory byte buffer."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("validate_bytes requires bytes or bytearray input")
        return self.validate_file(
            source=bytes(data),
            original_filename=original_filename,
            declared_mime=declared_mime,
            declared_size=len(data),
            inspection_id=inspection_id,
        )

    def validate_stream(
        self,
        stream: BinaryIO,
        original_filename: str,
        declared_mime: str | None = None,
        declared_size: int | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Explicit entry point: validate binary stream / file-like object."""
        if not hasattr(stream, "read"):
            raise TypeError("validate_stream requires a readable binary stream")
        return self.validate_file(
            source=stream,
            original_filename=original_filename,
            declared_mime=declared_mime,
            declared_size=declared_size,
            inspection_id=inspection_id,
        )

    def validate_local_file(
        self,
        file_path: Path | str,
        original_filename: str | None = None,
        declared_mime: str | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Explicit entry point: validate an existing local file on disk."""
        p = Path(file_path).resolve()
        name = original_filename or p.name
        return self.validate_file(
            source=p,
            original_filename=name,
            declared_mime=declared_mime,
            inspection_id=inspection_id,
        )

    def validate_text(
        self,
        text: str,
        original_filename: str = "document.txt",
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Explicit entry point: validate plain text content."""
        if not isinstance(text, str):
            raise TypeError("validate_text requires str input")
        name = (
            original_filename
            if original_filename.endswith((".txt", ".text", ".md", ".markdown", ".csv"))
            else f"{original_filename}.txt"
        )
        data = text.encode("utf-8")
        return self.validate_file(
            source=data,
            original_filename=name,
            declared_mime="text/plain",
            declared_size=len(data),
            inspection_id=inspection_id,
        )

    def validate_html(
        self,
        html: str,
        original_filename: str = "document.html",
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Explicit entry point: validate raw HTML content.

        Notice: Preflight classification and script pattern detection flag untrusted markers;
        preflight acceptance does not render HTML trusted or safe for unescaped DOM insertion.
        """
        if not isinstance(html, str):
            raise TypeError("validate_html requires str input")
        name = (
            original_filename
            if original_filename.endswith((".html", ".htm"))
            else f"{original_filename}.html"
        )
        data = html.encode("utf-8")
        return self.validate_file(
            source=data,
            original_filename=name,
            declared_mime="text/html",
            declared_size=len(data),
            inspection_id=inspection_id,
        )

    # -------------------------------------------------------------------------
    # Asynchronous Explicit Entry Points
    # -------------------------------------------------------------------------

    async def validate_bytes_async(
        self,
        data: bytes,
        original_filename: str,
        declared_mime: str | None = None,
    ) -> SecurityValidationDecision:
        """Asynchronously validate in-memory byte buffer without blocking event loop."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("validate_bytes_async requires bytes or bytearray input")
        return await self.validate_file_async(
            source=bytes(data),
            original_filename=original_filename,
            declared_mime=declared_mime,
            declared_size=len(data),
        )

    async def validate_stream_async(
        self,
        stream: BinaryIO,
        original_filename: str,
        declared_mime: str | None = None,
        declared_size: int | None = None,
    ) -> SecurityValidationDecision:
        """Asynchronously validate binary stream without blocking event loop."""
        if not hasattr(stream, "read"):
            raise TypeError("validate_stream_async requires a readable binary stream")
        return await self.validate_file_async(
            source=stream,
            original_filename=original_filename,
            declared_mime=declared_mime,
            declared_size=declared_size,
        )

    async def validate_local_file_async(
        self,
        file_path: Path | str,
        original_filename: str | None = None,
        declared_mime: str | None = None,
    ) -> SecurityValidationDecision:
        """Asynchronously validate an existing local file without blocking event loop."""
        p = Path(file_path).resolve()
        name = original_filename or p.name
        return await self.validate_file_async(
            source=p,
            original_filename=name,
            declared_mime=declared_mime,
        )

    async def validate_text_async(
        self,
        text: str,
        original_filename: str = "document.txt",
    ) -> SecurityValidationDecision:
        """Asynchronously validate plain text without blocking event loop."""
        if not isinstance(text, str):
            raise TypeError("validate_text_async requires str input")
        name = (
            original_filename
            if original_filename.endswith((".txt", ".text", ".md", ".markdown", ".csv"))
            else f"{original_filename}.txt"
        )
        data = text.encode("utf-8")
        return await self.validate_file_async(
            source=data,
            original_filename=name,
            declared_mime="text/plain",
            declared_size=len(data),
        )

    async def validate_html_async(
        self,
        html: str,
        original_filename: str = "document.html",
    ) -> SecurityValidationDecision:
        """Asynchronously validate raw HTML content without blocking event loop."""
        if not isinstance(html, str):
            raise TypeError("validate_html_async requires str input")
        name = (
            original_filename
            if original_filename.endswith((".html", ".htm"))
            else f"{original_filename}.html"
        )
        data = html.encode("utf-8")
        return await self.validate_file_async(
            source=data,
            original_filename=name,
            declared_mime="text/html",
            declared_size=len(data),
        )

    def validate_file(
        self,
        source: bytes | BinaryIO | Path | str,
        original_filename: str,
        declared_mime: str | None = None,
        declared_size: int | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Execute complete defensive preflight validation on an input source.

        Input Typing Notice:
        Callers should prefer explicit entry points (`validate_bytes`, `validate_stream`,
        `validate_local_file`, `validate_text`, `validate_html`) over passing ambiguous string
        references to `validate_file`. Security guard validates inputs fail-closed against
        magic signatures and structural indicators rather than trusting arbitrary user-supplied
        extension strings.

        Guarantees that both concurrency waiting and deep content analysis (PyPDFium2,
        zip parsing) strictly respect preflight_timeout_seconds, release semaphores,
        prevent late promotion, and never leak quarantine files.
        """
        active_id = inspection_id or str(uuid.uuid4())
        start_time = time.monotonic()
        acquired = self._semaphore.acquire(timeout=self.config.preflight_timeout_seconds)
        if not acquired:
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=0,
                content_sha256="",
                sanitized_display_name="unknown",
                error_code=ExtractionErrorCode.EXTRACTION_TIMEOUT,
                error_message="Security inspection timed out waiting for concurrency slot",
            )

        elapsed = time.monotonic() - start_time
        remaining_timeout = max(self.config.preflight_timeout_seconds - elapsed, 0.05)

        try:
            future = self._executor.submit(
                self._validate_file_internal,
                source=source,
                original_filename=original_filename,
                declared_mime=declared_mime,
                declared_size=declared_size,
                inspection_id=active_id,
            )
            try:
                return future.result(timeout=remaining_timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                self.quarantine_mgr.cleanup_inspection(active_id)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                    source_type=SourceType.TEXT,
                    verified_mime_type="application/octet-stream",
                    byte_count=0,
                    content_sha256="",
                    sanitized_display_name="timeout_cancelled",
                    error_code=ExtractionErrorCode.EXTRACTION_TIMEOUT,
                    error_message=(
                        f"Security preflight inspection timed out after "
                        f"{self.config.preflight_timeout_seconds}s during deep analysis"
                    ),
                )
        finally:
            self._semaphore.release()

    async def validate_file_async(
        self,
        source: bytes | BinaryIO | Path | str,
        original_filename: str,
        declared_mime: str | None = None,
        declared_size: int | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        """Asynchronously execute defensive preflight validation without blocking the event loop.

        Guarantees:
        1. CPU-intensive operations (PyPDFium2, zip expansion inspection, hashing)
           execute off the asyncio event loop via thread executor.
        2. Strictly respects preflight_timeout_seconds.
        3. Immediate quarantine cleanup if cancelled or timed out.
        4. Concurrency semaphore is always released, preventing deadlock.
        """
        loop = asyncio.get_running_loop()
        active_id = inspection_id or str(uuid.uuid4())
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    self.validate_file,
                    source,
                    original_filename,
                    declared_mime,
                    declared_size,
                    active_id,
                ),
                timeout=self.config.preflight_timeout_seconds + 0.5,
            )
        except TimeoutError:
            self.quarantine_mgr.cleanup_inspection(active_id)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=0,
                content_sha256="",
                sanitized_display_name="async_timeout",
                error_code=ExtractionErrorCode.EXTRACTION_TIMEOUT,
                error_message=(
                    f"Asynchronous inspection timed out after "
                    f"{self.config.preflight_timeout_seconds}s"
                ),
            )
        except asyncio.CancelledError:
            self.quarantine_mgr.cleanup_inspection(active_id)
            raise

    def _validate_file_internal(
        self,
        source: bytes | BinaryIO | Path | str,
        original_filename: str,
        declared_mime: str | None = None,
        declared_size: int | None = None,
        inspection_id: str | None = None,
    ) -> SecurityValidationDecision:
        # 1. Filename validation
        try:
            sanitized_name = sanitize_and_validate_display_name(original_filename)
        except ValueError as e:
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=0,
                content_sha256="",
                sanitized_display_name="rejected_name",
                error_code=ExtractionErrorCode.ACCESS_DENIED,
                error_message=f"Filename validation failed: {e}",
            )

        ext = Path(sanitized_name).suffix.lower()

        # 2. Pre-quarantine size checks
        if declared_size is not None:
            if declared_size > self.config.max_file_size_bytes:
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.TEXT,
                    verified_mime_type="application/octet-stream",
                    byte_count=declared_size,
                    content_sha256="",
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.FILE_TOO_LARGE,
                    error_message=(
                        f"Declared content length ({declared_size}) exceeds limit "
                        f"({self.config.max_file_size_bytes})"
                    ),
                )

        if isinstance(source, (Path, str)):
            p = Path(source).resolve()
            if not p.is_file():
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.TEXT,
                    verified_mime_type="application/octet-stream",
                    byte_count=0,
                    content_sha256="",
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                    error_message=f"Source path is not an accessible file: {p.name}",
                )
            actual_file_size = p.stat().st_size
            if actual_file_size > self.config.max_file_size_bytes:
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.TEXT,
                    verified_mime_type="application/octet-stream",
                    byte_count=actual_file_size,
                    content_sha256="",
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.FILE_TOO_LARGE,
                    error_message=(
                        f"File size ({actual_file_size} bytes) exceeds limit "
                        f"({self.config.max_file_size_bytes} bytes)"
                    ),
                )

        # 3. Stage into quarantine
        safe_quarantine_ext = ext if ext else ".bin"
        quarantine_path: Path | None = None
        try:
            if isinstance(source, bytes):
                quarantine_path, byte_count, content_sha256 = self.quarantine_mgr.stage_bytes(
                    source,
                    safe_quarantine_ext,
                    self.config.max_file_size_bytes,
                    inspection_id=inspection_id,
                )
            elif isinstance(source, (Path, str)):
                with open(source, "rb") as f:
                    quarantine_path, byte_count, content_sha256 = self.quarantine_mgr.stage_stream(
                        f,
                        safe_quarantine_ext,
                        self.config.max_file_size_bytes,
                        inspection_id=inspection_id,
                    )
            else:
                quarantine_path, byte_count, content_sha256 = self.quarantine_mgr.stage_stream(
                    source,
                    safe_quarantine_ext,
                    self.config.max_file_size_bytes,
                    inspection_id=inspection_id,
                )
        except ValueError as e:
            err_msg = str(e)
            code = (
                ExtractionErrorCode.FILE_TOO_LARGE
                if "exceeds maximum limit" in err_msg
                else ExtractionErrorCode.UNSUPPORTED_FORMAT
            )
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=0,
                content_sha256="",
                sanitized_display_name=sanitized_name,
                error_code=code,
                error_message=err_msg,
            )
        except Exception as e:
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=0,
                content_sha256="",
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
                error_message=f"Failed to stage file into quarantine: {type(e).__name__}",
            )

        # Size mismatch check if declared
        if declared_size is not None and declared_size != byte_count:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                error_message=(
                    f"Declared content length ({declared_size}) does not match "
                    f"actual bytes ({byte_count})"
                ),
            )

        # 4. Probe Magic Bytes
        try:
            with open(quarantine_path, "rb") as f:
                header = f.read(4096)
        except Exception as e:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.INTERNAL_EXTRACTION_ERROR,
                error_message=f"Failed to read quarantined header: {type(e).__name__}",
            )

        # Reject executables
        if header.startswith(MAGIC_MZ) or header.startswith(MAGIC_ELF):
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/x-executable",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message="Executable binaries (MZ/ELF) are strictly prohibited",
            )

        # Reject unsupported archives
        if (
            header.startswith(MAGIC_7Z)
            or header.startswith(MAGIC_RAR)
            or header.startswith(MAGIC_GZIP)
        ):
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/x-archive",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message=(
                    "Standalone archive formats (7z/rar/tar.gz) are strictly prohibited"
                ),
            )

        # 5. Format-Specific Deep Inspection
        final_decision: SecurityValidationDecision
        # A. PDF
        if header.startswith(MAGIC_PDF):
            if ext != ".pdf":
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.PDF,
                    verified_mime_type="application/pdf",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.MIME_MISMATCH,
                    error_message=f"PDF signature detected but filename extension is '{ext}'",
                )
            if declared_mime and declared_mime not in (
                "application/pdf",
                "application/octet-stream",
            ):
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.PDF,
                    verified_mime_type="application/pdf",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.MIME_MISMATCH,
                    error_message=f"Declared MIME '{declared_mime}' does not match PDF content",
                )

            # PDF Preflight
            pdf_decision = self._preflight_pdf(
                quarantine_path, byte_count, content_sha256, sanitized_name
            )
            if pdf_decision.outcome != SecurityDecisionOutcome.ACCEPTED:
                self.quarantine_mgr.cleanup(quarantine_path)
            final_decision = pdf_decision

        # B. Office Containers (DOCX, XLSX, PPTX) or Prohibited Standalone ZIP
        elif header.startswith(MAGIC_ZIP):
            final_decision = self._preflight_zip_container(
                quarantine_path, byte_count, content_sha256, sanitized_name, ext, declared_mime
            )

        # C. Local HTML
        elif ext in (".html", ".htm"):
            final_decision = self._preflight_html(
                quarantine_path, byte_count, content_sha256, sanitized_name, header
            )

        # D. Plain Text / Markdown / CSV
        elif ext in (".txt", ".text", ".md", ".markdown", ".csv"):
            final_decision = self._preflight_text(
                quarantine_path, byte_count, content_sha256, sanitized_name, ext, header
            )

        else:
            # Unrecognized generic binary
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message=(
                    f"Unsupported format or unrecognized binary structure for extension '{ext}'"
                ),
            )

        # Late Promotion Prevention Check:
        # If this inspection timed out or was cancelled while deep analysis was running,
        # inspection_id has been removed from quarantine_mgr._active_files and cleaned up.
        # Under NO circumstances should late execution promote or return an ACCEPTED decision.
        if final_decision.outcome == SecurityDecisionOutcome.ACCEPTED:
            if inspection_id and not self.quarantine_mgr.is_inspection_active(inspection_id):
                if quarantine_path:
                    self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.INSPECTION_FAILED,
                    source_type=final_decision.source_type,
                    verified_mime_type=final_decision.verified_mime_type,
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.EXTRACTION_TIMEOUT,
                    error_message="Inspection was cancelled or timed out during processing",
                )

        return final_decision

    def _preflight_pdf(
        self,
        quarantine_path: Path,
        byte_count: int,
        content_sha256: str,
        sanitized_name: str,
    ) -> SecurityValidationDecision:
        """Execute lightweight PDF preflight using PyPDFium2.

        Security Boundary & Heuristic Notice:
        Raw byte scanning for active markers (/JS, /JavaScript, /Launch, /EmbeddedFiles)
        is a defense-in-depth heuristic check on uncompressed tokens in the document stream.
        Because PDF object streams may be compressed using FlateDecode or encrypted,
        raw token scanning does NOT guarantee detection of all embedded scripts.
        Deep sandboxed extraction in Docling/PyPDFium remains mandatory.
        """
        warnings: list[str] = []

        # Scan for active content markers in raw PDF stream
        try:
            with open(quarantine_path, "rb") as f:
                pdf_bytes = f.read()
            for marker, description in ACTIVE_PDF_PATTERNS:
                if marker in pdf_bytes:
                    warnings.append(f"Security finding: {description}")
        except Exception:
            pass

        try:
            pdf_doc = pypdfium2.PdfDocument(quarantine_path)
            try:
                page_count = len(pdf_doc)
                if page_count > self.config.max_pdf_pages:
                    return SecurityValidationDecision(
                        outcome=SecurityDecisionOutcome.REJECTED,
                        source_type=SourceType.PDF,
                        verified_mime_type="application/pdf",
                        byte_count=byte_count,
                        content_sha256=content_sha256,
                        sanitized_display_name=sanitized_name,
                        page_count=page_count,
                        error_code=ExtractionErrorCode.PAGE_LIMIT_EXCEEDED,
                        error_message=(
                            f"PDF page count ({page_count}) exceeds limit "
                            f"({self.config.max_pdf_pages})"
                        ),
                    )
            finally:
                pdf_doc.close()

            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.ACCEPTED,
                source_type=SourceType.PDF,
                verified_mime_type="application/pdf",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                quarantine_path=str(quarantine_path),
                page_count=page_count,
                warnings=warnings,
            )

        except pypdfium2.PdfiumError as e:
            err_msg = str(e).lower()
            is_pwd = (
                "password" in err_msg
                or pypdfium2.raw.FPDF_GetLastError() == pypdfium2.raw.FPDF_ERR_PASSWORD
            )
            if is_pwd:
                code = ExtractionErrorCode.PASSWORD_PROTECTED
                msg = "PDF document is password protected or encrypted"
            else:
                code = ExtractionErrorCode.CORRUPTED_DOCUMENT
                msg = f"PDF document is malformed or corrupted: {e}"

            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.PDF,
                verified_mime_type="application/pdf",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=code,
                error_message=msg,
            )
        except Exception as e:
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.PDF,
                verified_mime_type="application/pdf",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                error_message=f"Failed to parse PDF document structure: {type(e).__name__}",
            )

    def _preflight_zip_container(
        self,
        quarantine_path: Path,
        byte_count: int,
        content_sha256: str,
        sanitized_name: str,
        ext: str,
        declared_mime: str | None,
    ) -> SecurityValidationDecision:
        """Inspect ZIP-based Office containers without extracting contents."""
        try:
            with zipfile.ZipFile(quarantine_path, "r") as zf:
                infolist = zf.infolist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                error_message=f"Corrupted or malformed ZIP central directory: {e}",
            )

        entry_count = len(infolist)

        if entry_count == 0:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.CORRUPTED_DOCUMENT,
                error_message="ZIP container contains 0 entries",
            )

        if entry_count > self.config.max_office_entries:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                archive_entry_count=entry_count,
                error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                error_message=(
                    f"ZIP container entry count ({entry_count}) exceeds limit "
                    f"({self.config.max_office_entries})"
                ),
            )

        total_uncompressed = 0
        total_compressed = 0
        seen_names: set[str] = set()

        for info in infolist:
            name = info.filename

            # Duplicate member names
            if name in seen_names:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=f"Duplicate member detected in container: {name}",
                )
            seen_names.add(name)

            # Path traversal
            parts = name.replace("\\", "/").split("/")
            if ".." in parts:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=f"Path traversal detected in container member: {name}",
                )

            # Absolute path in member name
            is_abs = (
                name.startswith("/") or name.startswith("\\") or bool(re.match(r"^[a-zA-Z]:", name))
            )
            if is_abs:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=f"Absolute path detected in container member: {name}",
                )

            # NTFS stream or control characters in member name
            if ":" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=(f"Prohibited NTFS stream or control chars in member: {name}"),
                )

            # Reserved Windows device names in member name
            for part in re.split(r"[\\/.]", name):
                if part.upper() in WINDOWS_RESERVED_NAMES:
                    self.quarantine_mgr.cleanup(quarantine_path)
                    return SecurityValidationDecision(
                        outcome=SecurityDecisionOutcome.REJECTED,
                        source_type=SourceType.DOCX,
                        verified_mime_type="application/zip",
                        byte_count=byte_count,
                        content_sha256=content_sha256,
                        sanitized_display_name=sanitized_name,
                        error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                        error_message=f"Reserved device name in container member: {name}",
                    )

            # Nested archives or executables
            lower_name = name.lower()
            bad_exts = (
                ".zip",
                ".tar",
                ".gz",
                ".7z",
                ".rar",
                ".exe",
                ".dll",
                ".bat",
                ".cmd",
                ".ps1",
            )
            if any(lower_name.endswith(bad_ext) for bad_ext in bad_exts):
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=f"Nested archive or executable member detected: {name}",
                )

            # Encryption flag
            if info.flag_bits & 0x1:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.PASSWORD_PROTECTED,
                    error_message="Office container contains encrypted entries",
                )

            # Single entry size limit
            if info.file_size > self.config.max_office_entry_uncompressed_bytes:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=(
                        f"Container member '{name}' uncompressed size ({info.file_size}) "
                        f"exceeds limit ({self.config.max_office_entry_uncompressed_bytes})"
                    ),
                )

            # Per-entry compression ratio
            entry_comp = max(info.compress_size, 1)
            entry_ratio = info.file_size / entry_comp
            if entry_ratio > self.config.max_office_compression_ratio:
                self.quarantine_mgr.cleanup(quarantine_path)
                return SecurityValidationDecision(
                    outcome=SecurityDecisionOutcome.REJECTED,
                    source_type=SourceType.DOCX,
                    verified_mime_type="application/zip",
                    byte_count=byte_count,
                    content_sha256=content_sha256,
                    sanitized_display_name=sanitized_name,
                    error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                    error_message=(
                        f"Container member '{name}' compression ratio "
                        f"({entry_ratio:.1f}:1) exceeds limit"
                    ),
                )

            total_uncompressed += info.file_size
            total_compressed += info.compress_size

        # Aggregate size and ratio limits
        if total_uncompressed > self.config.max_office_total_uncompressed_bytes:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                error_message=(
                    f"Total uncompressed size ({total_uncompressed}) exceeds limit "
                    f"({self.config.max_office_total_uncompressed_bytes})"
                ),
            )

        agg_ratio = total_uncompressed / max(total_compressed, 1)
        if agg_ratio > self.config.max_office_compression_ratio:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.ARCHIVE_LIMIT_EXCEEDED,
                error_message=(
                    f"Total compression ratio ({agg_ratio:.1f}:1) exceeds limit "
                    f"({self.config.max_office_compression_ratio}:1)"
                ),
            )

        # Container Structure Verification: Must have [Content_Types].xml
        if "[Content_Types].xml" not in seen_names:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message=(
                    "Standalone generic ZIP archives without OpenXML structure are prohibited"
                ),
            )

        # Identify exact Office type
        has_word = any(n.startswith("word/") for n in seen_names)
        has_xl = any(n.startswith("xl/") for n in seen_names)
        has_ppt = any(n.startswith("ppt/") for n in seen_names)

        if has_word:
            detected_type = SourceType.DOCX
            detected_mime = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            expected_ext = ".docx"
        elif has_xl:
            detected_type = SourceType.XLSX
            detected_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            expected_ext = ".xlsx"
        elif has_ppt:
            detected_type = SourceType.PPTX
            detected_mime = (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
            expected_ext = ".pptx"
        else:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.DOCX,
                verified_mime_type="application/zip",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message=(
                    "OpenXML package does not contain recognized word/, xl/, or ppt/ content"
                ),
            )

        # Verify extension alignment
        if ext != expected_ext:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=detected_type,
                verified_mime_type=detected_mime,
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.MIME_MISMATCH,
                error_message=(
                    f"Detected {detected_type.value.upper()} container but "
                    f"filename extension is '{ext}'"
                ),
            )

        # Verify declared MIME alignment if specified
        if declared_mime and declared_mime not in (
            detected_mime,
            "application/octet-stream",
            "application/zip",
        ):
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=detected_type,
                verified_mime_type=detected_mime,
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.MIME_MISMATCH,
                error_message=(
                    f"Declared MIME '{declared_mime}' does not match {detected_type.value.upper()}"
                ),
            )

        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=detected_type,
            verified_mime_type=detected_mime,
            byte_count=byte_count,
            content_sha256=content_sha256,
            sanitized_display_name=sanitized_name,
            quarantine_path=str(quarantine_path),
            archive_entry_count=entry_count,
        )

    def _preflight_html(
        self,
        quarantine_path: Path,
        byte_count: int,
        content_sha256: str,
        sanitized_name: str,
        header: bytes,
    ) -> SecurityValidationDecision:
        """Inspect local HTML input and scan for active script content.

        Security Boundary Notice:
        HTML preflight classifies the MIME type and flags active script tags as warnings.
        Preflight acceptance does NOT make the HTML content trusted or safe for arbitrary
        DOM insertion. All web content must undergo strict sandboxing, SSRF guards,
        and CSP filtering in Crawl4AI.
        """
        warnings: list[str] = []

        # Read full sample to scan for active content
        try:
            with open(quarantine_path, "rb") as f:
                content = f.read()
        except Exception:
            content = header

        # Reject null bytes in HTML
        if b"\x00" in content:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.WEB_PAGE,
                verified_mime_type="text/html",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message="HTML contains binary null bytes (corrupted or polyglot payload)",
            )

        # Scan for active script markers
        for pattern in ACTIVE_HTML_PATTERNS:
            if pattern.search(content):
                pat_name = pattern.pattern.decode("ascii", errors="ignore")
                warnings.append(
                    f"Security finding: Active HTML content detected matching {pat_name}"
                )

        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=SourceType.WEB_PAGE,
            verified_mime_type="text/html",
            byte_count=byte_count,
            content_sha256=content_sha256,
            sanitized_display_name=sanitized_name,
            quarantine_path=str(quarantine_path),
            warnings=warnings,
        )

    def _preflight_text(
        self,
        quarantine_path: Path,
        byte_count: int,
        content_sha256: str,
        sanitized_name: str,
        ext: str,
        header: bytes,
    ) -> SecurityValidationDecision:
        """Inspect plain text input for encoding and binary indicators."""
        # Reject null bytes in text
        if b"\x00" in header:
            self.quarantine_mgr.cleanup(quarantine_path)
            return SecurityValidationDecision(
                outcome=SecurityDecisionOutcome.REJECTED,
                source_type=SourceType.TEXT,
                verified_mime_type="application/octet-stream",
                byte_count=byte_count,
                content_sha256=content_sha256,
                sanitized_display_name=sanitized_name,
                error_code=ExtractionErrorCode.UNSUPPORTED_FORMAT,
                error_message=(
                    "Text file contains binary null bytes (corrupted or disguised binary)"
                ),
            )

        mime = "text/plain"
        if ext in (".md", ".markdown"):
            mime = "text/markdown"
        elif ext == ".csv":
            mime = "text/csv"

        return SecurityValidationDecision(
            outcome=SecurityDecisionOutcome.ACCEPTED,
            source_type=SourceType.TEXT,
            verified_mime_type=mime,
            byte_count=byte_count,
            content_sha256=content_sha256,
            sanitized_display_name=sanitized_name,
            quarantine_path=str(quarantine_path),
        )
