"""Assertion-centred proposal extraction and deterministic source grounding."""

from .grounding import EvidenceGroundingResult, ground_evidence_quote
from .service import (
    KnowledgeProposalExtractionService,
    ProposalExtractionContext,
    ProposalExtractionEligibility,
    ProposalExtractionProgress,
    proposal_extraction_eligibility,
)

__all__ = [
    "EvidenceGroundingResult",
    "KnowledgeProposalExtractionService",
    "ProposalExtractionContext",
    "ProposalExtractionEligibility",
    "ProposalExtractionProgress",
    "ground_evidence_quote",
    "proposal_extraction_eligibility",
]
