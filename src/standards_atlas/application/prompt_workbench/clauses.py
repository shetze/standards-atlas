"""Exact clause-identifier resolution independent of inbound transports."""

from __future__ import annotations

from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseDescriptor,
    ClauseProvider,
)


class ClauseNotFoundError(KeyError):
    """Raised when no persisted clause has the supplied identifier."""


class AmbiguousClauseIdentifierError(ValueError):
    """Raised when an unqualified human reference identifies multiple clauses."""

    def __init__(self, identifier: str, candidates: tuple[ClauseDescriptor, ...]) -> None:
        self.identifier = identifier
        self.candidates = candidates
        labels = ", ".join(_qualified_reference(item) for item in candidates)
        super().__init__(f"ambiguous clause identifier {identifier!r}; candidates: {labels}")


class ClauseResolver:
    """Resolve stable IDs and exact human-readable reference keys."""

    def __init__(self, provider: ClauseProvider) -> None:
        self._provider = provider

    def resolve(self, identifier: str) -> ClauseDescriptor:
        normalized = " ".join(identifier.split())
        if not normalized:
            raise ValueError("clause identifier must not be empty")

        try:
            return self._provider.get_clause(normalized)
        except KeyError:
            pass

        clauses = self._provider.list_clauses()
        exact = tuple(
            clause
            for clause in clauses
            if normalized.casefold()
            in {
                _qualified_reference(clause).casefold(),
                clause.reference.casefold(),
            }
        )
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AmbiguousClauseIdentifierError(normalized, exact)

        unqualified = tuple(
            clause
            for clause in clauses
            if clause.clause_reference.casefold() == normalized.casefold()
        )
        if len(unqualified) == 1:
            return unqualified[0]
        if len(unqualified) > 1:
            raise AmbiguousClauseIdentifierError(normalized, unqualified)
        raise ClauseNotFoundError(f"unknown clause identifier: {identifier}")


def _qualified_reference(clause: ClauseDescriptor) -> str:
    return f"{clause.document_key}:{clause.clause_reference}"
