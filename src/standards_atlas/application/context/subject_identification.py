"""Deterministic primary-subject identification from the term vocabulary."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.context.subject_vocabulary import (
    SubjectCandidate,
    SubjectCandidateVocabulary,
    SubjectCandidateVocabularyBuilder,
    normalize_subject_label,
)
from standards_atlas.application.ports.document_repositories import EngineeringDocumentReader
from standards_atlas.domain.model import Clause, EngineeringDocument, SubjectEvidenceKind


class SubjectIdentificationEvidence(BaseModel):
    """One deterministic match between clause context and a subject candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SubjectEvidenceKind
    matched_label: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    source_clause_id: str = Field(min_length=1)
    ancestor_distance: int | None = Field(default=None, ge=1)


class IdentifiedSubject(BaseModel):
    """One selected subject candidate plus the evidence that selected it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: SubjectIdentificationEvidence


class ClauseSubjectIdentification(BaseModel):
    """Deterministic primary-subject result for one clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    primary_subject: IdentifiedSubject | None = None
    ambiguous_candidates: tuple[str, ...] = ()


class SubjectIdentificationAnalysis(BaseModel):
    """Coverage and evidence-source measures for deterministic identification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clauses: int = Field(ge=0)
    resolved_clauses: int = Field(ge=0)
    unresolved_clauses: int = Field(ge=0)
    ambiguous_clauses: int = Field(ge=0)
    resolution_coverage: float = Field(ge=0.0, le=1.0)
    clause_heading_matches: int = Field(ge=0)
    clause_text_matches: int = Field(ge=0)
    ancestor_heading_matches: int = Field(ge=0)
    scope_context_matches: int = Field(ge=0)


class SubjectIdentificationReport(BaseModel):
    """Qualification-friendly artifact produced before CBox projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    vocabulary_schema_version: str
    results: tuple[ClauseSubjectIdentification, ...] = ()
    analysis: SubjectIdentificationAnalysis


class DeterministicSubjectIdentifier:
    """Identify one primary subject for each clause without model inference."""

    def identify(
        self,
        documents: Iterable[EngineeringDocument],
        vocabulary: SubjectCandidateVocabulary,
    ) -> SubjectIdentificationReport:
        ordered_documents = tuple(sorted(documents, key=lambda item: item.key.value))
        results: list[ClauseSubjectIdentification] = []
        source_counts: Counter[SubjectEvidenceKind] = Counter()

        for document in ordered_documents:
            clause_index = {clause.id.value: clause for clause in document.clauses}
            inbound_scopes = _inbound_scope_sources(document)
            for clause in document.clauses:
                selected, ambiguous = self._identify_clause(
                    clause,
                    clause_index=clause_index,
                    inbound_scope_sources=inbound_scopes.get(clause.id.value, ()),
                    candidates=vocabulary.candidates,
                )
                if selected is not None:
                    source_counts[selected.evidence.kind] += 1
                results.append(
                    ClauseSubjectIdentification(
                        document_key=document.key.value,
                        clause_id=clause.id.value,
                        primary_subject=selected,
                        ambiguous_candidates=ambiguous if selected is None else (),
                    )
                )

        resolved = sum(item.primary_subject is not None for item in results)
        ambiguous = sum(bool(item.ambiguous_candidates) for item in results)
        total = len(results)
        return SubjectIdentificationReport(
            vocabulary_schema_version=vocabulary.schema_version,
            results=tuple(results),
            analysis=SubjectIdentificationAnalysis(
                clauses=total,
                resolved_clauses=resolved,
                unresolved_clauses=total - resolved,
                ambiguous_clauses=ambiguous,
                resolution_coverage=resolved / total if total else 0.0,
                clause_heading_matches=source_counts[SubjectEvidenceKind.CLAUSE_HEADING],
                clause_text_matches=source_counts[SubjectEvidenceKind.CLAUSE_TEXT],
                ancestor_heading_matches=source_counts[SubjectEvidenceKind.ANCESTOR_HEADING],
                scope_context_matches=source_counts[SubjectEvidenceKind.SCOPE_CONTEXT],
            ),
        )

    def _identify_clause(
        self,
        clause: Clause,
        *,
        clause_index: dict[str, Clause],
        inbound_scope_sources: tuple[Clause, ...],
        candidates: tuple[SubjectCandidate, ...],
    ) -> tuple[IdentifiedSubject | None, tuple[str, ...]]:
        ambiguities: set[str] = set()
        evidence_sets: tuple[tuple[SubjectEvidenceKind, str, str, int | None, float], ...] = (
            (
                SubjectEvidenceKind.CLAUSE_HEADING,
                clause.heading or "",
                clause.id.value,
                None,
                1.0,
            ),
            (
                SubjectEvidenceKind.CLAUSE_TEXT,
                clause.plain_text,
                clause.id.value,
                None,
                0.95,
            ),
        )

        selected, ambiguous = _best_from_evidence_sets(evidence_sets, candidates)
        ambiguities.update(ambiguous)
        if selected is not None:
            return selected, ()

        for distance, ancestor in enumerate(_ancestors(clause, clause_index), start=1):
            if not ancestor.heading:
                continue
            selected, ambiguous = _best_from_evidence_sets(
                (
                    (
                        SubjectEvidenceKind.ANCESTOR_HEADING,
                        ancestor.heading,
                        ancestor.id.value,
                        distance,
                        max(0.75, 0.90 - (distance - 1) * 0.03),
                    ),
                ),
                candidates,
            )
            ambiguities.update(ambiguous)
            if selected is not None:
                return selected, ()

        for scope_clause in inbound_scope_sources:
            selected, ambiguous = _best_from_evidence_sets(
                (
                    (
                        SubjectEvidenceKind.SCOPE_CONTEXT,
                        " ".join(
                            part for part in (scope_clause.heading, scope_clause.plain_text) if part
                        ),
                        scope_clause.id.value,
                        None,
                        0.75,
                    ),
                ),
                candidates,
            )
            ambiguities.update(ambiguous)
            if selected is not None:
                return selected, ()
        return None, tuple(sorted(ambiguities))


class SubjectIdentificationService:
    """Build vocabulary and identify subjects from persisted EngineeringDocuments."""

    def __init__(self, documents: EngineeringDocumentReader) -> None:
        self._documents = documents
        self._vocabulary_builder = SubjectCandidateVocabularyBuilder()
        self._identifier = DeterministicSubjectIdentifier()

    def identify(self) -> SubjectIdentificationReport:
        documents = self._documents.list()
        vocabulary = self._vocabulary_builder.build(documents)
        return self._identifier.identify(documents, vocabulary)


def _best_from_evidence_sets(
    evidence_sets: tuple[tuple[SubjectEvidenceKind, str, str, int | None, float], ...],
    candidates: tuple[SubjectCandidate, ...],
) -> tuple[IdentifiedSubject | None, tuple[str, ...]]:
    ambiguities: set[str] = set()
    for kind, source_text, source_clause_id, distance, confidence in evidence_sets:
        matches = _matching_candidates(source_text, candidates)
        if not matches:
            continue
        exact = [
            candidate
            for candidate in matches
            if candidate.normalized_label == normalize_subject_label(source_text)
        ]
        if exact:
            chosen = exact[0]
        else:
            max_words = max(len(candidate.normalized_label.split()) for candidate in matches)
            most_specific = [
                candidate
                for candidate in matches
                if len(candidate.normalized_label.split()) == max_words
            ]
            if len(most_specific) != 1:
                ambiguities.update(candidate.normalized_label for candidate in most_specific)
                continue
            chosen = most_specific[0]
        return (
            IdentifiedSubject(
                normalized_label=chosen.normalized_label,
                confidence=confidence,
                evidence=SubjectIdentificationEvidence(
                    kind=kind,
                    matched_label=chosen.normalized_label,
                    source_text=source_text,
                    source_clause_id=source_clause_id,
                    ancestor_distance=distance,
                ),
            ),
            (),
        )
    return None, tuple(sorted(ambiguities))


def _matching_candidates(
    text: str,
    candidates: tuple[SubjectCandidate, ...],
) -> tuple[SubjectCandidate, ...]:
    normalized_text = normalize_subject_label(text)
    if not normalized_text:
        return ()
    matches = [
        candidate
        for candidate in candidates
        if _contains_normalized_label(normalized_text, candidate.normalized_label)
    ]
    return tuple(sorted(matches, key=lambda candidate: candidate.normalized_label))


def _contains_normalized_label(text: str, label: str) -> bool:
    pattern = rf"(?<![\w-]){re.escape(label)}(?![\w-])"
    return re.search(pattern, text) is not None


def _ancestors(clause: Clause, clause_index: dict[str, Clause]) -> tuple[Clause, ...]:
    if clause.structural_context is not None and clause.structural_context.ancestors:
        resolved = [
            clause_index[item.clause_id]
            for item in reversed(clause.structural_context.ancestors)
            if item.clause_id in clause_index
        ]
        return tuple(resolved)

    ancestors: list[Clause] = []
    current = clause
    seen = {clause.id.value}
    while current.parent_id is not None:
        parent = clause_index.get(current.parent_id.value)
        if parent is None or parent.id.value in seen:
            break
        ancestors.append(parent)
        seen.add(parent.id.value)
        current = parent
    return tuple(ancestors)


def _inbound_scope_sources(
    document: EngineeringDocument,
) -> dict[str, tuple[Clause, ...]]:
    sources: dict[str, list[Clause]] = {}
    for source_clause in document.clauses:
        context = source_clause.structural_context
        if context is None:
            continue
        for edge in context.scopes:
            if edge.target_clause_id is None:
                continue
            sources.setdefault(edge.target_clause_id, []).append(source_clause)
    return {
        target: tuple(sorted(clauses, key=lambda clause: clause.id.value))
        for target, clauses in sources.items()
    }
