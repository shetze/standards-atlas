"""Assertion-centred proposal extraction and deterministic source grounding."""

from .context import assertion_cbox_context
from .grounding import (
    EvidenceGroundingResult,
    evidence_source_text,
    ground_entity_evidence_quote,
    ground_evidence_quote,
)
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
from .unification import (
    KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION,
    DocumentKnowledgeProposalUnifier,
)
from .vocabulary import FormalOntologyVocabulary

__all__ = [
    "assertion_cbox_context",
    "EvidenceGroundingResult",
    "FormalOntologyVocabulary",
    "DocumentKnowledgeProposalUnifier",
    "KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION",
    "KnowledgeProposalExtractionService",
    "ProposalExtractionContext",
    "ProposalExtractionEligibility",
    "ProposalExtractionProgress",
    "SemanticTextProjection",
    "TABLE_KNOWLEDGE_PROJECTION_VERSION",
    "TableKnowledgeProposalProjector",
    "display_clause_reference",
    "evidence_source_text",
    "ground_entity_evidence_quote",
    "ground_evidence_quote",
    "project_clause_content",
    "proposal_extraction_eligibility",
]
