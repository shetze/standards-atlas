"""Clause access adapter backed by persisted EngineeringDocument objects."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
    ClauseDescriptor,
    ClauseFilter,
    DocumentDescriptor,
    SamplingStrategy,
)
from standards_atlas.domain.model import (
    Clause,
    ContentBlock,
    EngineeringDocument,
    NoteBlock,
    TableBlock,
)
from standards_atlas.domain.model.content import render_block_as_plain_text


class EngineeringDocumentClauseProvider:
    """Expose persisted EngineeringDocument clauses through the evaluation port."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
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
                if filters.statement_functions and not set(filters.statement_functions).issubset(
                    descriptor.statement_functions
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
        table_count, table_length, non_table_length = _content_metrics(clause.content)
        total_length = table_length + non_table_length
        table_dominant = (
            table_count > 0
            and table_length >= 200
            and total_length > 0
            and table_length / total_length >= 0.60
        )
        return ClauseDescriptor(
            id=clause.id.value,
            document_key=document.key.value,
            reference=clause.reference.as_text(),
            clause_reference=clause.reference.clause,
            content_hash=normalized_content_hash(clause.plain_text),
            clause_type=clause.clause_type,
            title=clause.title,
            text=clause.plain_text,
            parent_id=clause.parent_id.value if clause.parent_id else None,
            statement_functions=clause.semantic_classification.statement_functions,
            canonical_section=(
                clause.structural_profile.canonical_section
                if clause.structural_profile is not None
                else None
            ),
            document_categories=(
                tuple(item.category for item in clause.structural_profile.document_categories)
                if clause.structural_profile is not None
                else ()
            ),
            domain_categories=(
                tuple(item.category for item in clause.structural_profile.domain_categories)
                if clause.structural_profile is not None
                else ()
            ),
            semantic_sections=(
                clause.structural_profile.semantic_sections
                if clause.structural_profile is not None
                else ()
            ),
            content_profile=(
                ClauseContentProfile.TABLE_DOMINANT
                if table_dominant
                else ClauseContentProfile.TEXT_DOMINANT
            ),
            table_block_count=table_count,
            table_text_length=table_length,
            non_table_text_length=non_table_length,
            structural_context=(
                clause.structural_context.model_dump(mode="json")
                if clause.structural_context is not None
                else None
            ),
            reference_mentions=tuple(
                mention.model_dump(mode="json") for mention in clause.reference_mentions
            ),
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


def _content_metrics(content: tuple[ContentBlock, ...]) -> tuple[int, int, int]:
    """Return table count, table text length, and other text length recursively."""
    table_count = 0
    table_length = 0
    non_table_length = 0
    for block in content:
        rendered_length = len(render_block_as_plain_text(block).strip())
        if isinstance(block, TableBlock):
            table_count += 1
            table_length += rendered_length
        elif isinstance(block, NoteBlock):
            nested_count, nested_table_length, nested_non_table_length = _content_metrics(
                block.content
            )
            table_count += nested_count
            table_length += nested_table_length
            non_table_length += nested_non_table_length
            if block.note_kind:
                non_table_length += len(block.note_kind.strip())
        else:
            non_table_length += rendered_length
    return table_count, table_length, non_table_length
