"""Ontology-guided semantic knowledge extraction orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from standards_atlas.application.ports.llm_gateway import (
    LlmGatewayError,
    LlmResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from standards_atlas.application.ports.semantic_extraction import SemanticKnowledgeExtractor
from standards_atlas.domain.model import (
    Clause,
    ClauseApplicability,
    ClauseType,
    DocumentSemanticExtraction,
    EngineeringDocument,
    ExtractionAttempt,
    ExtractionFailure,
)

from .references import display_clause_reference


@dataclass(frozen=True)
class ExtractionEligibility:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionEligibilityContext:
    """Qualification-time semantic context used without mutating EngineeringDocument."""

    applicability: ClauseApplicability = ClauseApplicability()


def extraction_eligibility(
    clause: Clause,
    *,
    context: ExtractionEligibilityContext | None = None,
) -> ExtractionEligibility:
    """Route extraction from retained canonical context only."""

    applicability = context.applicability if context is not None else clause.applicability
    reasons: list[str] = []
    if applicability.present:
        reasons.append("applicability")
    if clause.primary_subject is not None:
        reasons.append("primary-subject")
    if clause.clause_type in {ClauseType.REQUIREMENT, ClauseType.OBJECTIVE}:
        reasons.append("engineering-statement")
    if clause.reference_relations:
        reasons.append("reference-relation")
    unique = tuple(dict.fromkeys(reasons))
    return ExtractionEligibility(bool(unique), unique)


@dataclass(frozen=True)
class ExtractionProgress:
    """Progress event emitted around one clause extraction attempt."""

    document_key: str
    clause_id: str
    clause_reference: str
    clause_title: str | None
    phase: str
    status: str | None = None
    duration_seconds: float | None = None
    entity_count: int = 0
    relation_count: int = 0
    message: str | None = None


class SemanticExtractionService:
    """Extract only from clauses admitted by deterministic or qualification semantics."""

    def __init__(self, extractor: SemanticKnowledgeExtractor) -> None:
        self._extractor = extractor

    def extract_document(
        self,
        document: EngineeringDocument,
        *,
        ontology_versions: tuple[str, ...],
        clause_ids: frozenset[str] | None = None,
        eligibility_by_clause: Mapping[str, ExtractionEligibilityContext] | None = None,
        progress: Callable[[ExtractionProgress], None] | None = None,
    ) -> DocumentSemanticExtraction:
        clauses = []
        failures: list[ExtractionFailure] = []
        attempts: list[ExtractionAttempt] = []
        for clause in document.clauses:
            clause_id = clause.id.value
            if clause_ids is not None and clause_id not in clause_ids:
                continue
            context = (
                eligibility_by_clause.get(clause_id) if eligibility_by_clause is not None else None
            )
            if eligibility_by_clause is not None and context is None:
                continue
            if not extraction_eligibility(clause, context=context).eligible:
                continue
            semantic_context = _semantic_context(clause, context)
            clause_reference = display_clause_reference(document.key.value, clause.reference)
            if progress is not None:
                progress(
                    ExtractionProgress(
                        document_key=document.key.value,
                        clause_id=clause_id,
                        clause_reference=clause_reference,
                        clause_title=clause.heading,
                        phase="started",
                    )
                )
            started = time.monotonic()
            try:
                extracted = self._extractor.extract(
                    clause,
                    document_key=document.key.value,
                    ontology_versions=ontology_versions,
                    semantic_context=semantic_context,
                )
            except LlmGatewayError as error:
                duration = time.monotonic() - started
                if isinstance(error, LlmTimeoutError):
                    kind = "timeout"
                elif isinstance(error, LlmResponseError):
                    kind = "response_error"
                elif isinstance(error, LlmUnavailableError):
                    kind = "unavailable"
                else:
                    kind = "response_error"
                attempts.append(
                    ExtractionAttempt(
                        clause_id=clause_id,
                        status=kind,
                        duration_seconds=duration,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                failures.append(
                    ExtractionFailure(
                        clause_id=clause_id,
                        clause_reference=clause_reference,
                        clause_title=clause.heading,
                        kind=kind,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                if progress is not None:
                    progress(
                        ExtractionProgress(
                            document_key=document.key.value,
                            clause_id=clause_id,
                            clause_reference=clause_reference,
                            clause_title=clause.heading,
                            phase="finished",
                            status=kind,
                            duration_seconds=duration,
                            message=str(error),
                        )
                    )
                continue
            duration = time.monotonic() - started
            attempts.append(
                ExtractionAttempt(
                    clause_id=clause_id,
                    status="ok",
                    duration_seconds=duration,
                )
            )
            clauses.append(extracted)
            if progress is not None:
                progress(
                    ExtractionProgress(
                        document_key=document.key.value,
                        clause_id=clause_id,
                        clause_reference=clause_reference,
                        clause_title=clause.heading,
                        phase="finished",
                        status="ok",
                        duration_seconds=duration,
                        entity_count=len(extracted.entities),
                        relation_count=len(extracted.relations),
                    )
                )
        return DocumentSemanticExtraction(
            source_document_key=document.key.value,
            clauses=tuple(clauses),
            failures=tuple(failures),
            attempts=tuple(attempts),
        )


def _semantic_context(
    clause: Clause,
    context: ExtractionEligibilityContext | None,
) -> dict[str, object]:
    """Build extractor context from canonical structure and context enrichments."""

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
