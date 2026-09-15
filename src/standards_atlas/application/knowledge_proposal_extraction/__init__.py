"""Assertion-centred proposal extraction and deterministic source grounding."""

from .grounding import EvidenceGroundingResult, ground_evidence_quote
from .projection import SemanticTextProjection, project_clause_content
from .references import display_clause_reference
from .service import (
    KnowledgeProposalExtractionService,
    ProposalExtractionContext,
    ProposalExtractionEligibility,
    ProposalExtractionProgress,
    proposal_extraction_eligibility,
)
from .table_projection import (
    TABLE_KNOWLEDGE_PROJECTION_VERSION,
    TableKnowledgeProposalProjector,
)
from .vocabulary import FormalOntologyVocabulary

__all__ = [
    "EvidenceGroundingResult",
    "FormalOntologyVocabulary",
    "KnowledgeProposalExtractionService",
    "ProposalExtractionContext",
    "ProposalExtractionEligibility",
    "ProposalExtractionProgress",
    "SemanticTextProjection",
    "TABLE_KNOWLEDGE_PROJECTION_VERSION",
    "TableKnowledgeProposalProjector",
    "display_clause_reference",
    "ground_evidence_quote",
    "project_clause_content",
    "proposal_extraction_eligibility",
]
