"""Structural analysis application logic."""

from standards_atlas.application.analysis.cross_document_reference_resolver import (
    resolve_cross_document_reference_relations,
)
from standards_atlas.application.analysis.internal_reference_resolver import (
    resolve_internal_reference_relations,
)
from standards_atlas.application.analysis.reference_candidate_detector import (
    ReferenceCandidateDetector,
)

__all__ = [
    "ReferenceCandidateDetector",
    "resolve_cross_document_reference_relations",
    "resolve_internal_reference_relations",
]
