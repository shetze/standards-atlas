"""Shared pure clause projection; no invented productive proposal or model run."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.application.assertion_qualification.audit import (
    AssertionReviewAudit,
    canonical_sha256,
)
from standards_atlas.application.assertion_qualification.models import (
    CandidateProvenance,
    NativeProposalProvenance,
    ReviewSnapshotProvenance,
)
from standards_atlas.application.assertion_qualification.review_pilot_models import (
    AssertionProposalAssertionSnapshot,
    AssertionProposalEntitySnapshot,
    AssertionProposalEvidenceSnapshot,
)
from standards_atlas.domain.model import DocumentKnowledgeProposal, EvidenceAnchor


@dataclass(frozen=True)
class ClauseEvaluationCandidate:
    """Non-persisted local candidate view shared by all evaluation entrances."""

    source_document_key: str
    clause_id: str
    entities: tuple[AssertionProposalEntitySnapshot, ...]
    assertions: tuple[AssertionProposalAssertionSnapshot, ...]
    violations: tuple[str, ...]
    failures: tuple[str, ...]
    provenance: CandidateProvenance

    @property
    def candidate_sha256(self) -> str:
        return canonical_sha256(
            {
                "source_document_key": self.source_document_key,
                "clause_id": self.clause_id,
                "entities": [item.model_dump(mode="json") for item in self.entities],
                "assertions": [item.model_dump(mode="json") for item in self.assertions],
                "violations": self.violations,
                "failures": self.failures,
            }
        )


def project_native_proposal(
    proposal: DocumentKnowledgeProposal,
    clause_id: str,
    *,
    proposal_hash: str | None = None,
) -> ClauseEvaluationCandidate:
    """Select assertion owners, their endpoints and explicitly assigned entities.

    Foreign evidence anchors never create extra cases. Entity-only cases retain
    entities through proposal_clause_ids. Input order and diagnostics are kept.
    """
    anchor_by_id = {anchor.id: anchor for anchor in proposal.evidence_anchors}
    assertions = tuple(
        item for item in proposal.assertion_proposals if item.source_clause_id.value == clause_id
    )
    entity_ids = {item.subject_id for item in assertions}
    entity_ids.update(item.object.entity_id for item in assertions if item.object.kind == "entity")
    entity_ids.update(
        entity.id
        for entity in proposal.entity_proposals
        if any(item.value == clause_id for item in entity.proposal_clause_ids)
    )
    entities = tuple(item for item in proposal.entity_proposals if item.id in entity_ids)
    return ClauseEvaluationCandidate(
        source_document_key=proposal.source_document_key,
        clause_id=clause_id,
        entities=tuple(
            AssertionProposalEntitySnapshot(
                id=entity.id,
                class_iri=entity.class_iri,
                normalized_label=entity.normalized_label,
                confidence=entity.confidence,
                rationale=entity.rationale,
                evidence=tuple(
                    _anchor_snapshot(anchor_by_id[key]) for key in entity.source_anchor_ids
                ),
            )
            for entity in entities
        ),
        assertions=tuple(
            AssertionProposalAssertionSnapshot(
                id=assertion.id,
                subject_id=assertion.subject_id,
                predicate=assertion.predicate,
                object=assertion.object,
                normative_force=assertion.normative_force,
                confidence=assertion.confidence,
                rationale=assertion.rationale,
                evidence=tuple(
                    _anchor_snapshot(anchor_by_id[key]) for key in assertion.evidence_anchor_ids
                ),
            )
            for assertion in assertions
        ),
        violations=tuple(
            f"{item.kind.value}: {item.term}: {item.reason}"
            for item in proposal.violations
            if item.clause_id.value == clause_id
        ),
        failures=tuple(
            f"{item.kind.value}: {item.error_type}: {item.message}"
            for item in proposal.failures
            if item.clause_id.value == clause_id
        ),
        provenance=NativeProposalProvenance(
            proposal_run_id=proposal.proposal_run_id,
            proposal_hash=proposal_hash or canonical_sha256(proposal.model_dump(mode="json")),
        ),
    )


def _anchor_snapshot(anchor: EvidenceAnchor) -> AssertionProposalEvidenceSnapshot:
    return AssertionProposalEvidenceSnapshot(
        anchor_id=anchor.id,
        source_clause_id=anchor.source_clause_id.value,
        source_kind=anchor.source_kind,
        start_offset=anchor.start_offset,
        end_offset=anchor.end_offset,
        content_hash=anchor.content_hash,
    )


def project_review_snapshot(
    audit: AssertionReviewAudit,
    *,
    document_key: str,
    clause_id: str,
) -> ClauseEvaluationCandidate:
    """Use every stored candidate and diagnostic, without re-running its route.

    Resolve the case from the bound bytes rather than trusting a caller-supplied
    edited review object. No productive proposal is reconstructed.
    """
    case = next(
        (
            case
            for case in audit.review.cases
            if (case.document_key, case.clause_id) == (document_key, clause_id)
        ),
        None,
    )
    if case is None:
        raise ValueError(f"unknown audit case: {(document_key, clause_id)!r}")
    snapshot = case.proposal
    fingerprint = audit.snapshot_sha256(document_key, clause_id)
    if snapshot is None or fingerprint is None:
        raise ValueError(f"missing proposal snapshot for audit case {(document_key, clause_id)!r}")
    return ClauseEvaluationCandidate(
        source_document_key=document_key,
        clause_id=clause_id,
        entities=snapshot.entities,
        assertions=snapshot.assertions,
        violations=snapshot.violations,
        failures=snapshot.failures,
        provenance=ReviewSnapshotProvenance(
            audit_sha256=audit.audit_sha256,
            snapshot_sha256=fingerprint,
            declared_proposal_sha256=snapshot.proposal_sha256,
            proposal_run_id=snapshot.proposal_run_id,
            cascade_run_id=snapshot.cascade_run_id,
            proposal_stage=snapshot.proposal_stage,
            route=snapshot.route,
            reasons=snapshot.reasons,
            verifier_dispositions=snapshot.verifier_dispositions,
            missing_entity_detected=snapshot.missing_entity_detected,
            missing_assertion_detected=snapshot.missing_assertion_detected,
        ),
    )
