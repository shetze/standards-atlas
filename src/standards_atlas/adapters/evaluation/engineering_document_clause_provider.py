"""Clause access adapter backed by persisted EngineeringDocument objects."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services.evaluation.clause_access import (
    ClauseDescriptor,
    ClauseFilter,
    DocumentDescriptor,
    SamplingStrategy,
)
from standards_atlas.domain.model import Clause, EngineeringDocument


class EngineeringDocumentClauseProvider:
    """Expose persisted EngineeringDocument clauses through the evaluation port."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._repository = FileSystemEngineeringDocumentRepository(workspace)

    def list_documents(self) -> tuple[DocumentDescriptor, ...]:
        descriptors = [self._document_descriptor(document) for document in self._documents()]
        return tuple(sorted(descriptors, key=lambda item: item.key))

    def get_clause(self, clause_id: str) -> ClauseDescriptor:
        for document in self._documents():
            for clause in document.clauses:
                if clause.id.value == clause_id:
                    return self._clause_descriptor(document, clause)
        raise KeyError(f"Unknown clause id: {clause_id}")

    def list_clauses(
        self,
        *,
        filters: ClauseFilter | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[ClauseDescriptor, ...]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        clauses = tuple(self._matching_clauses(filters or ClauseFilter()))
        end = None if limit is None else offset + limit
        return clauses[offset:end]

    def search_clauses(
        self,
        query: str,
        *,
        filters: ClauseFilter | None = None,
        limit: int = 20,
    ) -> tuple[ClauseDescriptor, ...]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit < 1:
            raise ValueError("limit must be positive")

        terms = tuple(term.casefold() for term in query.split() if term.strip())
        matches: list[tuple[int, ClauseDescriptor]] = []
        for clause in self._matching_clauses(filters or ClauseFilter()):
            title = (clause.title or "").casefold()
            text = clause.text.casefold()
            reference = clause.reference.casefold()
            score = sum(3 for term in terms if term in title)
            score += sum(2 for term in terms if term in reference)
            score += sum(1 for term in terms if term in text)
            if score:
                matches.append((score, clause))

        matches.sort(key=lambda item: (-item[0], item[1].document_key, item[1].id))
        return tuple(clause for _, clause in matches[:limit])

    def sample_clauses(
        self,
        *,
        count: int,
        strategy: SamplingStrategy = SamplingStrategy.RANDOM,
        filters: ClauseFilter | None = None,
        seed: int = 0,
    ) -> tuple[ClauseDescriptor, ...]:
        if count < 1:
            raise ValueError("count must be positive")

        population = list(self._matching_clauses(filters or ClauseFilter()))
        if count > len(population):
            raise ValueError(f"sample count {count} exceeds matching population {len(population)}")

        rng = random.Random(seed)
        if strategy is SamplingStrategy.RANDOM:
            return tuple(rng.sample(population, count))
        if strategy is SamplingStrategy.BALANCED_BY_DOCUMENT:
            return self._balanced_sample(population, count, rng)
        raise ValueError(f"Unsupported sampling strategy: {strategy}")

    def _documents(self) -> tuple[EngineeringDocument, ...]:
        return self._repository.list()

    def _matching_clauses(self, filters: ClauseFilter) -> Iterable[ClauseDescriptor]:
        for document in self._documents():
            if filters.document_keys and document.key.value not in filters.document_keys:
                continue
            if filters.document_types and document.document_type not in filters.document_types:
                continue
            for clause in document.clauses:
                descriptor = self._clause_descriptor(document, clause)
                if filters.clause_types and descriptor.clause_type not in filters.clause_types:
                    continue
                if filters.semantic_roles and not set(filters.semantic_roles).issubset(
                    descriptor.semantic_roles
                ):
                    continue
                text_length = len(descriptor.text)
                if filters.min_text_length is not None and text_length < filters.min_text_length:
                    continue
                if filters.max_text_length is not None and text_length > filters.max_text_length:
                    continue
                # Language metadata is not part of EngineeringDocument yet. A requested
                # language therefore yields no matches instead of guessing from text.
                if filters.language is not None:
                    continue
                yield descriptor

    @staticmethod
    def _document_descriptor(document: EngineeringDocument) -> DocumentDescriptor:
        return DocumentDescriptor(
            key=document.key.value,
            title=document.title,
            document_type=document.document_type,
            year=document.year,
            version=document.version,
            clause_count=len(document.clauses),
        )

    @staticmethod
    def _clause_descriptor(document: EngineeringDocument, clause: Clause) -> ClauseDescriptor:
        return ClauseDescriptor(
            id=clause.id.value,
            document_key=document.key.value,
            reference=clause.reference.as_text(),
            clause_reference=clause.reference.clause,
            clause_type=clause.clause_type,
            title=clause.title,
            text=clause.plain_text,
            parent_id=clause.parent_id.value if clause.parent_id else None,
            semantic_roles=clause.semantic_roles,
        )

    @staticmethod
    def _balanced_sample(
        population: list[ClauseDescriptor],
        count: int,
        rng: random.Random,
    ) -> tuple[ClauseDescriptor, ...]:
        buckets: dict[str, list[ClauseDescriptor]] = defaultdict(list)
        for clause in population:
            buckets[clause.document_key].append(clause)
        for bucket in buckets.values():
            rng.shuffle(bucket)

        selected: list[ClauseDescriptor] = []
        keys = sorted(buckets)
        while len(selected) < count:
            made_progress = False
            for key in keys:
                if buckets[key] and len(selected) < count:
                    selected.append(buckets[key].pop())
                    made_progress = True
            if not made_progress:
                break
        return tuple(selected)
