"""briefs.py — Task types, evidence models, and Pre-Edit Brief schemas for JAVED.

Defines the core data structures for Pre-Edit Briefs (DEFECT, FEATURE, DOCUMENTATION,
REFACTOR, SECURITY_FIX, MIGRATION, INVESTIGATION), evidence validation contracts,
and deterministic quality assertions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskType(StrEnum):
    """Canonical task types governing pre-edit gating rules."""

    DEFECT = "DEFECT"
    FEATURE = "FEATURE"
    DOCUMENTATION = "DOCUMENTATION"
    REFACTOR = "REFACTOR"
    SECURITY_FIX = "SECURITY_FIX"
    MIGRATION = "MIGRATION"
    INVESTIGATION = "INVESTIGATION"


class RootCauseConfidence(StrEnum):
    """Bounded root cause confidence levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERIFIED = "VERIFIED"


class EvidenceType(StrEnum):
    """Supported evidence categories grounded in repository and test telemetry."""

    SOURCE_CODE = "SOURCE_CODE"
    STACK_TRACE = "STACK_TRACE"
    TEST_FAILURE = "TEST_FAILURE"
    API_RESPONSE = "API_RESPONSE"
    UI_OBSERVATION = "UI_OBSERVATION"
    LOG_EVENT = "LOG_EVENT"
    GRAPHIFY_RESULT = "GRAPHIFY_RESULT"
    CONTRACT_DIFF = "CONTRACT_DIFF"
    OWNER_REQUIREMENT = "OWNER_REQUIREMENT"
    DOCUMENTATION = "DOCUMENTATION"


# Disallowed trivial/symptom root-cause phrases
INVALID_ROOT_CAUSE_PHRASES: tuple[str, ...] = (
    "page is broken",
    "test fails",
    "test failed",
    "model returned an error",
    "code probably needs updating",
    "something went wrong",
    "unknown error",
    "syntax error",
    "unexpected behavior",
    "needs fixing",
)


@dataclass(frozen=True)
class TargetLineRange:
    """Target file line range authorized for modification."""

    relative_path: str
    start_line: int
    end_line: int
    owning_symbol: str = ""
    expected_content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.relative_path.strip():
            raise ValueError("relative_path cannot be empty")
        if self.start_line < 0 or self.end_line < 0:
            raise ValueError("Line numbers must be non-negative")
        if self.start_line > self.end_line and self.end_line != 0:
            raise ValueError("start_line cannot exceed end_line")

    def contains_line(self, line_num: int, allowance: int = 20) -> bool:
        """Check if line falls within target range including boundary allowance."""
        # 0 to 0 indicates whole new file authorization
        if self.start_line == 0 and self.end_line == 0:
            return True
        return (self.start_line - allowance) <= line_num <= (self.end_line + allowance)


@dataclass(frozen=True)
class EvidenceItem:
    """Immutable evidence item grounding analysis in verified telemetry."""

    evidence_id: str
    evidence_type: EvidenceType
    source: str
    relative_path: str
    summary: str
    collected_at: str
    line_range: str = ""
    symbol: str = ""
    content_hash: str = ""
    confidence: str = "EXTRACTED"
    graphify_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id cannot be empty")
        if not self.summary.strip():
            raise ValueError("summary cannot be empty")
        # Security: reject secret tokens or raw headers in evidence
        lower_summary = self.summary.lower()
        for s in ("api_key", "authorization", "bearer ", "password", "secret_token"):
            if s in lower_summary:
                raise ValueError(f"Sensitive credential detected in evidence: {s}")


@dataclass(frozen=True)
class PreEditBrief:
    """Authoritative Pre-Edit Brief required before code write authorization."""

    task_id: str
    task_type: TaskType
    objective: str
    repository_head: str
    files_read: list[str]
    files_to_modify: list[str]
    files_not_to_modify: list[str]
    target_line_ranges: list[TargetLineRange]
    evidence: list[EvidenceItem]
    security_risks: list[str]
    regression_risks: list[str]
    rollback_strategy: str
    test_strategy: str
    created_at: str
    created_by: str = "Antigravity"
    repository_context_hash: str = ""

    # Defect-specific fields
    current_behavior: str = ""
    expected_behavior: str = ""
    root_cause: str = ""
    root_cause_confidence: RootCauseConfidence = RootCauseConfidence.LOW
    affected_symbols: list[str] = field(default_factory=list)
    patch_strategy: str = ""

    # Feature/Design-specific fields
    current_architecture: str = ""
    design_rationale: str = ""
    owning_components: list[str] = field(default_factory=list)
    affected_contracts: list[str] = field(default_factory=list)
    compatibility_requirements: list[str] = field(default_factory=list)
    implementation_strategy: str = ""

    # Security/Migration-specific fields
    threat_analysis: str = ""
    compatibility_plan: str = ""

    def compute_brief_hash(self) -> str:
        """Compute deterministic SHA-256 hash across canonical fields."""
        canonical_dict = {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "objective": self.objective.strip(),
            "repository_head": self.repository_head,
            "files_to_modify": sorted(self.files_to_modify),
            "files_not_to_modify": sorted(self.files_not_to_modify),
            "target_ranges": [
                f"{r.relative_path}:{r.start_line}-{r.end_line}" for r in self.target_line_ranges
            ],
            "root_cause": self.root_cause.strip(),
            "root_cause_confidence": self.root_cause_confidence.value,
            "affected_symbols": sorted(self.affected_symbols),
            "owning_components": sorted(self.owning_components),
            "affected_contracts": sorted(self.affected_contracts),
            "patch_strategy": self.patch_strategy.strip(),
            "implementation_strategy": self.implementation_strategy.strip(),
            "rollback_strategy": self.rollback_strategy.strip(),
            "test_strategy": self.test_strategy.strip(),
        }
        raw_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def validate_structure(self) -> tuple[bool, list[str]]:
        """Validate structural completeness and quality contracts according to TaskType."""
        errors: list[str] = []

        if not self.task_id.strip():
            errors.append("task_id is missing or empty")
        if not self.objective.strip():
            errors.append("objective is missing or empty")
        if not self.repository_head.strip():
            errors.append("repository_head is missing or empty")
        if not self.rollback_strategy.strip():
            errors.append("rollback_strategy is missing or empty")
        if not self.test_strategy.strip():
            errors.append("test_strategy is missing or empty")

        # Scope validation
        if not self.files_to_modify and self.task_type != TaskType.INVESTIGATION:
            errors.append("files_to_modify must declare at least one target file")
        if not self.files_not_to_modify and self.task_type not in {
            TaskType.DOCUMENTATION,
            TaskType.INVESTIGATION,
        }:
            errors.append("files_not_to_modify must explicitly declare adjacent protected files")
        if not self.target_line_ranges and self.task_type not in {
            TaskType.DOCUMENTATION,
            TaskType.INVESTIGATION,
        }:
            errors.append("target_line_ranges must be declared for write tasks")

        # Traversal and sensitive path defense
        for fp in self.files_to_modify:
            norm_p = fp.replace("\\", "/").strip()
            if ".." in norm_p or norm_p.startswith(("/", "\\")):
                errors.append(f"Path traversal rejected in files_to_modify: {fp}")
            if any(s in norm_p for s in [".env", ".git", "node_modules", ".venv"]):
                errors.append(f"Protected path rejected in files_to_modify: {fp}")

        # Evidence requirements
        if not self.evidence and self.task_type != TaskType.INVESTIGATION:
            errors.append("evidence must contain at least one verified telemetry item")

        # Type-specific rules
        if self.task_type == TaskType.DEFECT:
            if not self.current_behavior.strip():
                errors.append("DEFECT brief requires current_behavior")
            if not self.expected_behavior.strip():
                errors.append("DEFECT brief requires expected_behavior")
            if not self.root_cause.strip():
                errors.append("DEFECT brief requires root_cause")
            else:
                rc_lower = self.root_cause.lower().strip()
                for phrase in INVALID_ROOT_CAUSE_PHRASES:
                    if rc_lower == phrase or rc_lower.startswith(phrase):
                        errors.append(
                            f"Symptom rejected as root cause: '{self.root_cause}'. "
                            "Must identify responsible mechanism or state."
                        )
            if not self.patch_strategy.strip():
                errors.append("DEFECT brief requires patch_strategy")

        elif self.task_type == TaskType.FEATURE:
            if not self.design_rationale.strip():
                errors.append("FEATURE brief requires design_rationale")
            if not self.owning_components:
                errors.append("FEATURE brief requires owning_components")
            if not self.affected_contracts:
                errors.append("FEATURE brief requires affected_contracts")
            if not self.implementation_strategy.strip():
                errors.append("FEATURE brief requires implementation_strategy")

        elif self.task_type == TaskType.SECURITY_FIX:
            if not self.threat_analysis.strip():
                errors.append("SECURITY_FIX brief requires threat_analysis")
            if not self.root_cause.strip():
                errors.append("SECURITY_FIX brief requires root_cause")
            if not self.security_risks:
                errors.append("SECURITY_FIX brief requires security_risks")

        elif self.task_type == TaskType.MIGRATION:
            if not self.compatibility_plan.strip():
                errors.append("MIGRATION brief requires compatibility_plan")
            if not self.compatibility_requirements:
                errors.append("MIGRATION brief requires compatibility_requirements")

        elif self.task_type == TaskType.DOCUMENTATION:
            for fp in self.files_to_modify:
                if not fp.endswith((".md", ".txt", ".rst", ".doc")):
                    errors.append(f"DOCUMENTATION task cannot modify source code file: {fp}")

        elif self.task_type == TaskType.INVESTIGATION:
            if self.files_to_modify:
                errors.append("INVESTIGATION task is strictly read-only; cannot modify files")

        return len(errors) == 0, errors
