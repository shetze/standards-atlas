"""Slice-7B Efficient → Verify → Escalate assertion qualification cascade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCascadeClauseReport,
    AssertionCascadeProposalSource,
    AssertionCascadeReason,
    AssertionCascadeRoute,
    AssertionClauseVerification,
    AssertionQualificationCascadeReport,
    AssertionVerificationDisposition,
)
from standards_atlas.application.assertion_qualification.evaluation import proposal_sha256
from standards_atlas.application.knowledge_proposal_extraction import (
    KnowledgeProposalExtractionService,
    ProposalExtractionContext,
    proposal_extraction_eligibility,
)
from standards_atlas.application.ports.knowledge_proposals import (
    AssertionProposalVerifier,
    KnowledgeProposalExtractor,
)
from standards_atlas.application.ports.llm_gateway import LlmGatewayError
from standards_atlas.domain.model import (
    Clause,
    DocumentKnowledgeProposal,
    EngineeringDocument,
    EvidenceAnchor,
    KnowledgeEntityProposal,
    NormativeAssertionProposal,
)


@dataclass(frozen=True)
class AssertionQualificationCascadeResult:
    """Non-persisted cascade outputs kept separate from canonical document knowledge."""

    efficient_proposal: DocumentKnowledgeProposal
    escalation_proposal: DocumentKnowledgeProposal | None
    report: AssertionQualificationCascadeReport


class AssertionQualificationCascadeService:
    """Run an efficient extractor, independent verifier and targeted escalator.

    Verification is exhaustive over every eligible source clause, including clauses where the
    efficient extractor proposed no semantic items. That invariant is what lets the verifier
    detect false negatives instead of merely confirming already-proposed assertions.
    """

    def __init__(
        self,
        *,
        efficient_extractor: KnowledgeProposalExtractor,
        verifier: AssertionProposalVerifier,
        escalation_extractor: KnowledgeProposalExtractor,
    ) -> None:
        self._efficient_extractor = efficient_extractor
        self._verifier = verifier
        self._escalation_extractor = escalation_extractor

    def run_document(
        self,
        document: EngineeringDocument,
        *,
        cascade_run_id: str,
        efficient_proposal_run_id: str,
        escalation_proposal_run_id: str,
        ontology_versions: tuple[str, ...],
        clause_ids: frozenset[str] | None = None,
        context_by_clause: Mapping[str, ProposalExtractionContext] | None = None,
    ) -> AssertionQualificationCascadeResult:
        if len({cascade_run_id, efficient_proposal_run_id, escalation_proposal_run_id}) != 3:
            raise ValueError("cascade, efficient and escalation run ids must be distinct")

        efficient = KnowledgeProposalExtractionService(self._efficient_extractor).extract_document(
            document,
            proposal_run_id=efficient_proposal_run_id,
            ontology_versions=ontology_versions,
            clause_ids=clause_ids,
            context_by_clause=context_by_clause,
        )

        eligible = tuple(
            clause
            for clause in document.clauses
            if _clause_is_selected(
                clause,
                clause_ids=clause_ids,
                context_by_clause=context_by_clause,
            )
        )
        reports: list[AssertionCascadeClauseReport] = []
        escalated_clause_ids: set[str] = set()

        for clause in eligible:
            candidates = _clause_candidates(efficient, clause)
            reasons = _efficient_escalation_reasons(efficient, clause)
            verification: AssertionClauseVerification | None = None
            verification_error_type: str | None = None
            verification_error_message: str | None = None

            if not reasons:
                try:
                    verification = self._verifier.verify(
                        clause,
                        document_key=document.key.value,
                        ontology_versions=ontology_versions,
                        evidence_anchors=candidates.anchors,
                        entity_proposals=candidates.entities,
                        assertion_proposals=candidates.assertions,
                        semantic_context=_semantic_context(
                            clause,
                            context_by_clause.get(clause.id.value)
                            if context_by_clause is not None
                            else None,
                        ),
                    )
                    _validate_verification_completeness(verification, clause, candidates)
                    reasons = _verification_escalation_reasons(verification)
                except (LlmGatewayError, ValueError) as error:
                    reasons = (AssertionCascadeReason.VERIFICATION_ERROR,)
                    verification_error_type = type(error).__name__
                    verification_error_message = str(error)

            route = (
                AssertionCascadeRoute.ESCALATED
                if reasons
                else AssertionCascadeRoute.EFFICIENT_ACCEPTED
            )
            if route is AssertionCascadeRoute.ESCALATED:
                escalated_clause_ids.add(clause.id.value)
            reports.append(
                AssertionCascadeClauseReport(
                    clause_id=clause.id,
                    route=route,
                    reasons=reasons,
                    verification=verification,
                    verification_error_type=verification_error_type,
                    verification_error_message=verification_error_message,
                    efficient_entities=len(candidates.entities),
                    efficient_assertions=len(candidates.assertions),
                    efficient_violations=_clause_violation_count(efficient, clause),
                    efficient_failures=_clause_failure_count(efficient, clause),
                )
            )

        escalation: DocumentKnowledgeProposal | None = None
        if escalated_clause_ids:
            escalation = KnowledgeProposalExtractionService(
                self._escalation_extractor
            ).extract_document(
                document,
                proposal_run_id=escalation_proposal_run_id,
                ontology_versions=ontology_versions,
                clause_ids=frozenset(escalated_clause_ids),
                context_by_clause=context_by_clause,
            )
            updated_reports: list[AssertionCascadeClauseReport] = []
            for report in reports:
                if report.route is AssertionCascadeRoute.ESCALATED:
                    source_clause = _clause_by_id(document, report.clause_id.value)
                    escalation_candidates = _clause_candidates(escalation, source_clause)
                    report = report.model_copy(
                        update={
                            "escalation_entities": len(escalation_candidates.entities),
                            "escalation_assertions": len(escalation_candidates.assertions),
                            "escalation_violations": _clause_violation_count(
                                escalation, source_clause
                            ),
                            "escalation_failures": _clause_failure_count(escalation, source_clause),
                        }
                    )
                updated_reports.append(report)
            reports = updated_reports

        sources = [_proposal_source("efficient", efficient)]
        if escalation is not None:
            sources.append(_proposal_source("escalation", escalation))
        report = AssertionQualificationCascadeReport(
            cascade_run_id=cascade_run_id,
            source_document_key=document.key.value,
            ontology_versions=ontology_versions,
            proposal_sources=tuple(sources),
            verifier_provenance=self._verifier.provenance(),
            clauses=tuple(reports),
            efficient_accepted_clauses=sum(
                item.route is AssertionCascadeRoute.EFFICIENT_ACCEPTED for item in reports
            ),
            escalated_clauses=len(escalated_clause_ids),
        )
        return AssertionQualificationCascadeResult(
            efficient_proposal=efficient,
            escalation_proposal=escalation,
            report=report,
        )


@dataclass(frozen=True)
class _ClauseCandidates:
    anchors: tuple[EvidenceAnchor, ...]
    entities: tuple[KnowledgeEntityProposal, ...]
    assertions: tuple[NormativeAssertionProposal, ...]


def _clause_is_selected(
    clause: Clause,
    *,
    clause_ids: frozenset[str] | None,
    context_by_clause: Mapping[str, ProposalExtractionContext] | None,
) -> bool:
    clause_id = clause.id.value
    if clause_ids is not None and clause_id not in clause_ids:
        return False
    if context_by_clause is not None and clause_id not in context_by_clause:
        return False
    return proposal_extraction_eligibility(clause).eligible


def _clause_candidates(
    proposal: DocumentKnowledgeProposal,
    clause: Clause,
) -> _ClauseCandidates:
    clause_id = clause.id.value
    anchor_by_id = {anchor.id: anchor for anchor in proposal.evidence_anchors}
    assertions = tuple(
        item for item in proposal.assertion_proposals if item.source_clause_id.value == clause_id
    )
    assertion_entity_ids = {
        entity_id for assertion in assertions for entity_id in _assertion_entity_ids(assertion)
    }
    entities = tuple(
        entity
        for entity in proposal.entity_proposals
        if entity.id in assertion_entity_ids
        or any(
            anchor_by_id[anchor_id].clause_id.value == clause_id
            for anchor_id in entity.source_anchor_ids
        )
    )
    anchor_ids = {anchor_id for entity in entities for anchor_id in entity.source_anchor_ids} | {
        anchor_id for assertion in assertions for anchor_id in assertion.evidence_anchor_ids
    }
    anchors = tuple(
        anchor
        for anchor in proposal.evidence_anchors
        if anchor.id in anchor_ids and anchor.clause_id.value == clause_id
    )
    return _ClauseCandidates(anchors=anchors, entities=entities, assertions=assertions)


def _assertion_entity_ids(assertion: NormativeAssertionProposal) -> tuple[str, ...]:
    object_ = assertion.object
    if object_.kind == "entity":
        return (assertion.subject_id, object_.entity_id)
    return (assertion.subject_id,)


def _clause_violation_count(proposal: DocumentKnowledgeProposal, clause: Clause) -> int:
    return sum(item.clause_id == clause.id for item in proposal.violations)


def _clause_failure_count(proposal: DocumentKnowledgeProposal, clause: Clause) -> int:
    return sum(item.clause_id == clause.id for item in proposal.failures)


def _efficient_escalation_reasons(
    proposal: DocumentKnowledgeProposal,
    clause: Clause,
) -> tuple[AssertionCascadeReason, ...]:
    clause_id = clause.id.value
    reasons: set[AssertionCascadeReason] = set()
    if any(item.clause_id.value == clause_id for item in proposal.failures):
        reasons.add(AssertionCascadeReason.EFFICIENT_FAILURE)
    if any(item.clause_id.value == clause_id for item in proposal.violations):
        reasons.add(AssertionCascadeReason.EFFICIENT_VIOLATION)
    return tuple(sorted(reasons, key=lambda item: item.value))


def _verification_escalation_reasons(
    verification: AssertionClauseVerification,
) -> tuple[AssertionCascadeReason, ...]:
    reasons: set[AssertionCascadeReason] = set()
    reviews = (*verification.entity_reviews, *verification.assertion_reviews)
    if any(review.disposition is AssertionVerificationDisposition.REJECTED for review in reviews):
        reasons.add(AssertionCascadeReason.REJECTED_CANDIDATE)
    if any(review.disposition is AssertionVerificationDisposition.UNCERTAIN for review in reviews):
        reasons.add(AssertionCascadeReason.UNCERTAIN_CANDIDATE)
    if verification.missing_entity_detected:
        reasons.add(AssertionCascadeReason.MISSING_ENTITY)
    if verification.missing_assertion_detected:
        reasons.add(AssertionCascadeReason.MISSING_ASSERTION)
    return tuple(sorted(reasons, key=lambda item: item.value))


def _validate_verification_completeness(
    verification: AssertionClauseVerification,
    clause: Clause,
    candidates: _ClauseCandidates,
) -> None:
    if verification.clause_id != clause.id:
        raise ValueError("assertion verifier returned a result for a different clause")
    expected_entities = {item.id for item in candidates.entities}
    reviewed_entities = {item.candidate_id for item in verification.entity_reviews}
    if expected_entities != reviewed_entities:
        raise ValueError(
            "assertion verifier must review every efficient entity candidate exactly once"
        )
    expected_assertions = {item.id for item in candidates.assertions}
    reviewed_assertions = {item.candidate_id for item in verification.assertion_reviews}
    if expected_assertions != reviewed_assertions:
        raise ValueError(
            "assertion verifier must review every efficient assertion candidate exactly once"
        )


def _proposal_source(
    stage: str,
    proposal: DocumentKnowledgeProposal,
) -> AssertionCascadeProposalSource:
    provenance = proposal.proposal_provenance
    return AssertionCascadeProposalSource(
        stage=stage,
        proposal_run_id=proposal.proposal_run_id,
        proposal_hash=proposal_sha256(proposal),
        extractor=provenance.extractor,
        extractor_version=provenance.extractor_version,
        model=provenance.model,
        provider=provenance.provider,
    )


def _clause_by_id(document: EngineeringDocument, clause_id: str) -> Clause:
    for clause in document.clauses:
        if clause.id.value == clause_id:
            return clause
    raise ValueError(f"cascade clause is not present in document: {clause_id!r}")


def _semantic_context(
    clause: Clause,
    context: ProposalExtractionContext | None,
) -> dict[str, object]:
    applicability = context.applicability if context is not None else clause.applicability
    return {
        "applicability": applicability.model_dump(mode="json"),
        "normative_status": clause.normative_status.value,
        "clause_type": clause.clause_type.value,
        "primary_subject": (
            clause.primary_subject.normalized_label if clause.primary_subject is not None else None
        ),
        "reference_relations": [
            item.model_dump(mode="json") for item in clause.reference_relations
        ],
    }
