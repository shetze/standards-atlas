from __future__ import annotations

import pytest

from standards_atlas.application.prompt_workbench.clauses import (
    AmbiguousClauseIdentifierError,
    ClauseNotFoundError,
    ClauseResolver,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    ClauseFilter,
)
from standards_atlas.domain.model import ClauseType


def _clause(clause_id: str, document_key: str, reference: str, human: str) -> ClauseDescriptor:
    return ClauseDescriptor(
        id=clause_id,
        document_key=document_key,
        reference=human,
        clause_reference=reference,
        content_hash="sha256:" + "a" * 64,
        clause_type=ClauseType.CLAUSE,
        text="Clause text.",
    )


class Provider:
    def __init__(self, clauses: tuple[ClauseDescriptor, ...]) -> None:
        self.clauses = clauses

    def get_clause(self, clause_id: str) -> ClauseDescriptor:
        try:
            return next(item for item in self.clauses if item.id == clause_id)
        except StopIteration as exc:
            raise KeyError(clause_id) from exc

    def list_clauses(
        self, *, filters: ClauseFilter | None = None, limit: int | None = None, offset: int = 0
    ) -> tuple[ClauseDescriptor, ...]:
        del filters
        end = None if limit is None else offset + limit
        return self.clauses[offset:end]


def test_resolves_stable_id_qualified_key_and_human_reference() -> None:
    clause = _clause("clause-a", "EN50126-1", "6.2", "EN 50126-1:2017 6.2")
    resolver = ClauseResolver(Provider((clause,)))

    assert resolver.resolve("clause-a") == clause
    assert resolver.resolve("EN50126-1:6.2") == clause
    assert resolver.resolve("EN 50126-1:2017 6.2") == clause
    assert resolver.resolve("6.2") == clause


def test_rejects_ambiguous_unqualified_reference_and_unknown_identifier() -> None:
    clauses = (
        _clause("clause-a", "EN50126-1", "6.2", "EN 50126-1:2017 6.2"),
        _clause("clause-b", "EN50126-2", "6.2", "EN 50126-2:2017 6.2"),
    )
    resolver = ClauseResolver(Provider(clauses))

    with pytest.raises(AmbiguousClauseIdentifierError) as error:
        resolver.resolve("6.2")

    assert [item.id for item in error.value.candidates] == ["clause-a", "clause-b"]
    with pytest.raises(ClauseNotFoundError, match="unknown clause identifier"):
        resolver.resolve("9.9")
