"""Javed Content Extraction Pipeline.

Defines the normalized extraction data contracts, schemas, and metadata models
conforming to BRICK-007 Phase 2 specifications.
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
    "ExtractionErrorCode",
    "ExtractionStatus",
    "ExtractionWarning",
    "ExtractionError",
    "ExtractionElementType",
    "ExtractorDescriptor",
    "MergedCell",
    "NormalizedDocument",
    "SectionReference",
    "SourceDescriptor",
    "SourceType",
    "TableCell",
    "TableRepresentation",
]
