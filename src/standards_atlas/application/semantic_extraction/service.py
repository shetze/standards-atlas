"""Ontology-guided semantic knowledge extraction orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from standards_atlas.application.ports.semantic_extraction import SemanticKnowledgeExtractor
from standards_atlas.domain.model import (
    Clause,
    DocumentSemanticExtraction,
    EngineeringDocument,
    KnowledgeKind,
    ProcessFunction,
)


@dataclass(frozen=True)
class ExtractionEligibility:
    eligible: bool
    reasons: tuple[str, ...]


def extraction_eligibility(clause: Clause) -> ExtractionEligibility:
    """Use existing taxonomy/ontology annotations as deterministic routing signals."""

    semantic = clause.semantic_classification
    reasons: list[str] = []
    if semantic.knowledge_kinds:
        reasons.append("knowledge-kind")
    if semantic.role_semantics_present:
        reasons.append("role-semantics")
    if semantic.applicability_present:
        reasons.append("applicability")
    if any(
        function in {ProcessFunction.ACTIVITY, ProcessFunction.INPUT, ProcessFunction.OUTPUT}
        for function in semantic.process_functions
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
        for kind in semantic.knowledge_kinds
    ):
        reasons.append("engineering-knowledge")
    unique = tuple(dict.fromkeys(reasons))
    return ExtractionEligibility(bool(unique), unique)


class SemanticExtractionService:
    """Extract only from clauses admitted by existing deterministic semantics."""

    def __init__(self, extractor: SemanticKnowledgeExtractor) -> None:
        self._extractor = extractor

    def extract_document(
        self,
        document: EngineeringDocument,
        *,
        ontology_versions: tuple[str, ...],
    ) -> DocumentSemanticExtraction:
        clauses = []
        for clause in document.clauses:
            if not extraction_eligibility(clause).eligible:
                continue
            clauses.append(
                self._extractor.extract(
                    clause,
                    document_key=document.key.value,
                    ontology_versions=ontology_versions,
                )
            )
        return DocumentSemanticExtraction(
            source_document_key=document.key.value,
            clauses=tuple(clauses),
        )
