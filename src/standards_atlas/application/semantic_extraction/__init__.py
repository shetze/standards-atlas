"""Ontology-guided concept and relation extraction."""

from .projection import SemanticTextProjection, project_clause_content
from .references import display_clause_reference
from .service import (
    ExtractionEligibility,
    ExtractionEligibilityContext,
    ExtractionProgress,
    SemanticExtractionService,
    extraction_eligibility,
)
from .vocabulary import FormalOntologyVocabulary

__all__ = [
    "ExtractionEligibility",
    "ExtractionEligibilityContext",
    "ExtractionProgress",
    "SemanticTextProjection",
    "FormalOntologyVocabulary",
    "SemanticExtractionService",
    "display_clause_reference",
    "project_clause_content",
    "extraction_eligibility",
]
