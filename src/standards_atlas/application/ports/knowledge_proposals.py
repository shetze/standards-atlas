"""Ports for rebuildable assertion-centred knowledge proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    DocumentKnowledgeProposal,
    EvidenceAnchor,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    KnowledgeProposalViolation,
    NormativeAssertionProposal,
)

if TYPE_CHECKING:
    from standards_atlas.application.assertion_qualification.cascade_models import (
        AssertionClauseVerification,
        AssertionVerifierProvenance,
    )


@dataclass(frozen=True)
class ClauseKnowledgeProposalResult:
    """Non-persisted result of extracting one source clause.

    The document-level application service owns aggregation, retries, failures and
    run persistence. The adapter returns only source-grounded semantic candidates
    plus request hashes required for auditability.
    """

    clause_id: ClauseId
    evidence_anchors: tuple[EvidenceAnchor, ...] = ()
    entity_proposals: tuple[KnowledgeEntityProposal, ...] = ()
    assertion_proposals: tuple[NormativeAssertionProposal, ...] = ()
    violations: tuple[KnowledgeProposalViolation, ...] = ()
    proposal_provenance: KnowledgeProposalProvenance | None = None
    input_hash: str | None = None
    raw_response_hash: str | None = None


class KnowledgeProposalExtractor(Protocol):
    """Extract ontology-grounded entities and assertions from one source clause."""

    def provenance(self) -> KnowledgeProposalProvenance:
        """Return stable run-level extractor provenance."""
        ...

    def extract(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        semantic_context: Mapping[str, object] | None = None,
    ) -> ClauseKnowledgeProposalResult: ...


class DocumentKnowledgeProposalRepository(Protocol):
    """Persistence boundary for non-canonical document knowledge proposals."""

    def save(self, proposal: DocumentKnowledgeProposal) -> None: ...

    def load(self, proposal_run_id: str, document_key: str) -> DocumentKnowledgeProposal | None: ...


class AssertionProposalVerifier(Protocol):
    """Independently verify efficient candidates and detect missing semantics."""

    def provenance(self) -> AssertionVerifierProvenance:
        """Return stable verifier provenance for the cascade report."""
        ...

    def verify(
        self,
        clause: Clause,
        *,
        document_key: str,
        ontology_versions: tuple[str, ...],
        evidence_anchors: Sequence[EvidenceAnchor],
        entity_proposals: Sequence[KnowledgeEntityProposal],
        assertion_proposals: Sequence[NormativeAssertionProposal],
        semantic_context: Mapping[str, object] | None = None,
    ) -> AssertionClauseVerification: ...
