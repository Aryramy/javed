"""Javed Content Extraction Pipeline.

Defines normalized extraction data contracts, schemas, security guards, quarantine
management, and metadata models conforming to BRICK-007 specifications.
"""

from __future__ import annotations

from javed.extraction.schema import (
    AccessMethod,
    AuthenticatedSourceContext,
    AuthenticationStatus,
    BoundingBox,
    CoordinateOrigin,
    CoordinateSpace,
    DocumentMetadata,
    ElementProvenance,
    ExtractionElement,
    ExtractionElementType,
    ExtractionError,
    ExtractionErrorCode,
    ExtractionStatus,
    ExtractionWarning,
    ExtractorDescriptor,
    MergedCell,
    NormalizedDocument,
    SectionReference,
    SourceDescriptor,
    SourceType,
    TableCell,
    TableRepresentation,
)
from javed.extraction.security import (
    ExtractionSecurityGuard,
    QuarantineManager,
    SecurityDecisionOutcome,
    SecurityGuardConfig,
    SecurityValidationDecision,
    sanitize_and_validate_display_name,
)

__all__ = [
    "AccessMethod",
    "AuthenticatedSourceContext",
    "AuthenticationStatus",
    "BoundingBox",
    "CoordinateOrigin",
    "CoordinateSpace",
    "DocumentMetadata",
    "ElementProvenance",
    "ExtractionElement",
    "ExtractionElementType",
    "ExtractionError",
    "ExtractionErrorCode",
    "ExtractionSecurityGuard",
    "ExtractionStatus",
    "ExtractionWarning",
    "ExtractorDescriptor",
    "MergedCell",
    "NormalizedDocument",
    "QuarantineManager",
    "SectionReference",
    "SecurityDecisionOutcome",
    "SecurityGuardConfig",
    "SecurityValidationDecision",
    "SourceDescriptor",
    "SourceType",
    "TableCell",
    "TableRepresentation",
    "sanitize_and_validate_display_name",
]
