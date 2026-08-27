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
    ApplicabilityFunction,
    Clause,
    DocumentSemanticExtraction,
    EngineeringDocument,
    ExtractionAttempt,
    ExtractionFailure,
    KnowledgeKind,
    ProcessFunction,
)

from .references import display_clause_reference


@dataclass(frozen=True)
class ExtractionEligibility:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionEligibilityContext:
    """Qualification-time semantic context used without mutating EngineeringDocument."""

    knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    process_functions: tuple[ProcessFunction, ...] = ()
    applicability_present: bool = False
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    role_semantics_present: bool = False


def extraction_eligibility(
    clause: Clause,
    *,
    context: ExtractionEligibilityContext | None = None,
) -> ExtractionEligibility:
    """Use persisted or qualification-time semantics as deterministic routing signals."""

    semantic = clause.semantic_classification
    knowledge_kinds = context.knowledge_kinds if context is not None else semantic.knowledge_kinds
    process_functions = (
        context.process_functions if context is not None else semantic.process_functions
    )
    applicability_present = (
        context.applicability_present if context is not None else semantic.applicability_present
    )
    role_semantics_present = (
        context.role_semantics_present if context is not None else semantic.role_semantics_present
    )

    reasons: list[str] = []
    if knowledge_kinds:
        reasons.append("knowledge-kind")
    if role_semantics_present:
        reasons.append("role-semantics")
    if applicability_present:
        reasons.append("applicability")
    if any(
        function in {ProcessFunction.ACTIVITY, ProcessFunction.INPUT, ProcessFunction.OUTPUT}
        for function in process_functions
    ):
        reasons.append("process-function")
    if any(
        kind
        in {
            KnowledgeKind.TECHNIQUE,
            KnowledgeKind.METHOD_OR_MEASURE,
            KnowledgeKind.TECHNIQUE_OR_MEASURE,
            KnowledgeKind.PROCESS,
            KnowledgeKind.ARTIFACT,
            KnowledgeKind.ROLE,
            KnowledgeKind.EVIDENCE,
            KnowledgeKind.CONCEPT,
        }
        for kind in knowledge_kinds
    ):
        reasons.append("engineering-knowledge")
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
            effective_clause = _clause_with_context(clause, context)
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
                    effective_clause,
                    document_key=document.key.value,
                    ontology_versions=ontology_versions,
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


def _clause_with_context(
    clause: Clause,
    context: ExtractionEligibilityContext | None,
) -> Clause:
    if context is None:
        return clause
    semantic = clause.semantic_classification.model_copy(
        update={
            "knowledge_kinds": context.knowledge_kinds,
            "process_functions": context.process_functions,
            "applicability_present": context.applicability_present,
            "applicability_functions": context.applicability_functions,
            "role_semantics_present": context.role_semantics_present,
        }
    )
    return clause.model_copy(update={"semantic_classification": semantic})
