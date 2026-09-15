"""Assertion-centred document knowledge proposal extraction orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from standards_atlas.application.knowledge_proposal_extraction.references import (
    display_clause_reference,
)
from standards_atlas.application.ports.knowledge_proposals import KnowledgeProposalExtractor
from standards_atlas.application.ports.llm_gateway import (
    LlmGatewayError,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseApplicability,
    ClauseType,
    DocumentKnowledgeProposal,
    EngineeringDocument,
    KnowledgeProposalAttempt,
    KnowledgeProposalFailure,
    ProposalAttemptStatus,
    ProposalFailureKind,
)


@dataclass(frozen=True)
class ProposalExtractionContext:
    """Qualification-time CBox context supplied without mutating the document."""

    applicability: ClauseApplicability = ClauseApplicability()


@dataclass(frozen=True)
class ProposalExtractionEligibility:
    eligible: bool
    reason: str


@dataclass(frozen=True)
class ProposalExtractionProgress:
    """Progress event around one assertion-proposal extraction attempt."""

    document_key: str
    clause_id: str
    clause_reference: str
    clause_title: str | None
    phase: str
    status: str | None = None
    duration_seconds: float | None = None
    entity_count: int = 0
    assertion_count: int = 0
    violation_count: int = 0
    message: str | None = None


def proposal_extraction_eligibility(clause: Clause) -> ProposalExtractionEligibility:
    """Admit substantive prose without depending on prior semantic classifications."""

    if clause.clause_type is ClauseType.TOC:
        return ProposalExtractionEligibility(False, "table-of-contents")
    if clause.clause_type is ClauseType.TABLE:
        return ProposalExtractionEligibility(False, "structured-table-deferred-to-slice-6")
    if not clause.plain_text.strip():
        return ProposalExtractionEligibility(False, "empty-source-text")
    return ProposalExtractionEligibility(True, "substantive-source-clause")


class KnowledgeProposalExtractionService:
    """Aggregate per-clause assertion candidates into one run-scoped proposal."""

    def __init__(self, extractor: KnowledgeProposalExtractor) -> None:
        self._extractor = extractor

    def extract_document(
        self,
        document: EngineeringDocument,
        *,
        proposal_run_id: str,
        ontology_versions: tuple[str, ...],
        clause_ids: frozenset[str] | None = None,
        context_by_clause: Mapping[str, ProposalExtractionContext] | None = None,
        progress: Callable[[ProposalExtractionProgress], None] | None = None,
    ) -> DocumentKnowledgeProposal:
        anchors = []
        entities = []
        assertions = []
        violations = []
        failures: list[KnowledgeProposalFailure] = []
        attempts: list[KnowledgeProposalAttempt] = []
        run_provenance = None

        for clause in document.clauses:
            clause_id = clause.id.value
            if clause_ids is not None and clause_id not in clause_ids:
                continue
            if context_by_clause is not None and clause_id not in context_by_clause:
                continue
            if not proposal_extraction_eligibility(clause).eligible:
                continue

            context = context_by_clause.get(clause_id) if context_by_clause is not None else None
            clause_reference = display_clause_reference(document.key.value, clause.reference)
            if progress is not None:
                progress(
                    ProposalExtractionProgress(
                        document_key=document.key.value,
                        clause_id=clause_id,
                        clause_reference=clause_reference,
                        clause_title=clause.heading,
                        phase="started",
                    )
                )
            started = time.monotonic()
            try:
                result = self._extractor.extract(
                    clause,
                    document_key=document.key.value,
                    ontology_versions=ontology_versions,
                    semantic_context=_semantic_context(clause, context),
                )
                if result.clause_id != clause.id:
                    raise ValueError(
                        "knowledge proposal extractor returned a result for a different clause"
                    )
                candidate_provenance = result.proposal_provenance or self._extractor.provenance()
                if run_provenance is None:
                    run_provenance = candidate_provenance
                elif candidate_provenance != run_provenance:
                    raise ValueError(
                        "knowledge proposal extractor provenance changed within one run"
                    )
            except (LlmGatewayError, ValueError) as error:
                duration = time.monotonic() - started
                kind, status = _failure_kind(error)
                attempts.append(
                    KnowledgeProposalAttempt(
                        clause_id=clause.id,
                        status=status,
                        duration_seconds=duration,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                failures.append(
                    KnowledgeProposalFailure(
                        clause_id=clause.id,
                        kind=kind,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                if progress is not None:
                    progress(
                        ProposalExtractionProgress(
                            document_key=document.key.value,
                            clause_id=clause_id,
                            clause_reference=clause_reference,
                            clause_title=clause.heading,
                            phase="finished",
                            status=status.value,
                            duration_seconds=duration,
                            message=str(error),
                        )
                    )
                continue

            duration = time.monotonic() - started
            attempts.append(
                KnowledgeProposalAttempt(
                    clause_id=clause.id,
                    status=ProposalAttemptStatus.OK,
                    duration_seconds=duration,
                    input_hash=result.input_hash,
                    raw_response_hash=result.raw_response_hash,
                )
            )
            anchors.extend(result.evidence_anchors)
            entities.extend(result.entity_proposals)
            assertions.extend(result.assertion_proposals)
            violations.extend(result.violations)
            if progress is not None:
                progress(
                    ProposalExtractionProgress(
                        document_key=document.key.value,
                        clause_id=clause_id,
                        clause_reference=clause_reference,
                        clause_title=clause.heading,
                        phase="finished",
                        status=ProposalAttemptStatus.OK.value,
                        duration_seconds=duration,
                        entity_count=len(result.entity_proposals),
                        assertion_count=len(result.assertion_proposals),
                        violation_count=len(result.violations),
                    )
                )

        return DocumentKnowledgeProposal(
            proposal_run_id=proposal_run_id,
            source_document_key=document.key.value,
            ontology_versions=ontology_versions,
            evidence_anchors=tuple(anchors),
            entity_proposals=tuple(entities),
            assertion_proposals=tuple(assertions),
            violations=tuple(violations),
            failures=tuple(failures),
            attempts=tuple(attempts),
            proposal_provenance=run_provenance or self._extractor.provenance(),
        )


def _failure_kind(
    error: LlmGatewayError | ValueError,
) -> tuple[ProposalFailureKind, ProposalAttemptStatus]:
    if isinstance(error, LlmTimeoutError):
        return ProposalFailureKind.TIMEOUT, ProposalAttemptStatus.TIMEOUT
    if isinstance(error, LlmUnavailableError):
        return ProposalFailureKind.UNAVAILABLE, ProposalAttemptStatus.UNAVAILABLE
    if isinstance(error, LlmResponseError):
        return ProposalFailureKind.RESPONSE_ERROR, ProposalAttemptStatus.RESPONSE_ERROR
    return ProposalFailureKind.VALIDATION_ERROR, ProposalAttemptStatus.VALIDATION_ERROR


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
