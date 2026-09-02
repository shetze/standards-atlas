"""Deterministic subject-candidate vocabulary derived from defined terms."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.ports.document_repositories import EngineeringDocumentReader
from standards_atlas.domain.model import Clause, ClauseType, EngineeringDocument, StandardReference
from standards_atlas.domain.model.subject_normalization import normalize_subject_label

_WHITESPACE = re.compile(r"\s+")
_TERM_CONTAINER = re.compile(r"^terms\b.*\bdefinitions\b", re.IGNORECASE)


class SubjectCandidateProvenance(BaseModel):
    """Authoritative AtlasData origin of one subject-candidate label."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    document_title: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: StandardReference
    source_label: str = Field(min_length=1)


class SubjectCandidate(BaseModel):
    """One normalized candidate with all source spellings and provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_label: str = Field(min_length=1)
    labels: tuple[str, ...] = Field(min_length=1)
    provenance: tuple[SubjectCandidateProvenance, ...] = Field(min_length=1)

    @property
    def document_count(self) -> int:
        return len({item.document_key for item in self.provenance})


class SubjectVocabularyAnalysis(BaseModel):
    """Deterministic quality and overlap measures for candidate extraction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    term_clauses: int = Field(ge=0)
    accepted_term_clauses: int = Field(ge=0)
    ignored_term_containers: int = Field(ge=0)
    missing_headings: int = Field(ge=0)
    unique_candidates: int = Field(ge=0)
    repeated_candidates: int = Field(ge=0)
    cross_document_candidates: int = Field(ge=0)
    extraction_coverage: float = Field(ge=0.0, le=1.0)


class SubjectCandidateVocabulary(BaseModel):
    """Open candidate vocabulary derived only from authoritative term headings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    candidates: tuple[SubjectCandidate, ...] = ()
    analysis: SubjectVocabularyAnalysis

    def find(self, label: str) -> SubjectCandidate | None:
        """Return the candidate matching a label under lexical normalization."""

        normalized = normalize_subject_label(label)
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.normalized_label == normalized
            ),
            None,
        )


class SubjectCandidateVocabularyBuilder:
    """Build a conservative subject vocabulary from ``ClauseType.TERM`` headings.

    This slice intentionally performs no subject assignment and no semantic grouping.
    Normalization merges only lexical variants; every original spelling and source is
    retained for later qualification and taxonomy work.
    """

    def build(self, documents: Iterable[EngineeringDocument]) -> SubjectCandidateVocabulary:
        grouped: dict[str, list[SubjectCandidateProvenance]] = defaultdict(list)
        term_clauses = 0
        ignored_containers = 0
        missing_headings = 0

        ordered_documents = sorted(documents, key=lambda document: document.key.value)
        for document in ordered_documents:
            for clause in document.clauses:
                if clause.clause_type is not ClauseType.TERM:
                    continue
                term_clauses += 1
                heading = _clean_source_label(clause.heading)
                if heading is None:
                    missing_headings += 1
                    continue
                if _is_term_container(heading):
                    ignored_containers += 1
                    continue
                normalized = normalize_subject_label(heading)
                if not normalized:
                    missing_headings += 1
                    continue
                grouped[normalized].append(_provenance(document, clause, heading))

        candidates = tuple(
            _candidate(normalized, provenance) for normalized, provenance in sorted(grouped.items())
        )
        accepted = sum(len(candidate.provenance) for candidate in candidates)
        repeated = sum(1 for candidate in candidates if len(candidate.provenance) > 1)
        cross_document = sum(1 for candidate in candidates if candidate.document_count > 1)
        eligible = term_clauses - ignored_containers
        coverage = accepted / eligible if eligible else 0.0
        return SubjectCandidateVocabulary(
            candidates=candidates,
            analysis=SubjectVocabularyAnalysis(
                term_clauses=term_clauses,
                accepted_term_clauses=accepted,
                ignored_term_containers=ignored_containers,
                missing_headings=missing_headings,
                unique_candidates=len(candidates),
                repeated_candidates=repeated,
                cross_document_candidates=cross_document,
                extraction_coverage=coverage,
            ),
        )


class SubjectCandidateVocabularyService:
    """Build the candidate vocabulary from persisted EngineeringDocuments."""

    def __init__(self, documents: EngineeringDocumentReader) -> None:
        self._documents = documents
        self._builder = SubjectCandidateVocabularyBuilder()

    def build(self) -> SubjectCandidateVocabulary:
        return self._builder.build(self._documents.list())


def _clean_source_label(label: str | None) -> str | None:
    if label is None:
        return None
    cleaned = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", label)).strip()
    return cleaned or None


def _is_term_container(label: str) -> bool:
    return _TERM_CONTAINER.search(label) is not None


def _provenance(
    document: EngineeringDocument,
    clause: Clause,
    source_label: str,
) -> SubjectCandidateProvenance:
    return SubjectCandidateProvenance(
        document_key=document.key.value,
        document_title=document.title,
        clause_id=clause.id.value,
        reference=clause.reference,
        source_label=source_label,
    )


def _candidate(
    normalized_label: str,
    provenance: list[SubjectCandidateProvenance],
) -> SubjectCandidate:
    ordered = tuple(
        sorted(
            provenance,
            key=lambda item: (
                item.document_key,
                item.reference.part or "",
                item.reference.clause,
                item.clause_id,
            ),
        )
    )
    labels = tuple(
        sorted(
            {item.source_label for item in ordered},
            key=lambda value: (
                value != normalized_label,
                value.casefold(),
                value,
            ),
        )
    )
    return SubjectCandidate(
        normalized_label=normalized_label,
        labels=labels,
        provenance=ordered,
    )
