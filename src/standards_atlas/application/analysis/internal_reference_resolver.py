"""Resolve document-local clause references into semantic relations."""

from __future__ import annotations

import re

from standards_atlas.domain.model import (
    Clause,
    EngineeringDocument,
    RelationScope,
    SemanticRelation,
    SemanticRelationKind,
)

_REFERENCE = r"\d+(?:\.\d+){1,7}(?:[a-z])?"
_RANGE_RE = re.compile(
    rf"(?P<prefix>requirements?|clauses?|subclauses?|paragraphs?)?\s*"
    rf"(?P<start>{_REFERENCE})\s*(?:to|through|–|—|-)\s*(?P<end>{_REFERENCE})",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    rf"(?P<prefix>requirements?|clauses?|subclauses?|paragraphs?|see|according\s+to|under|in)?"
    rf"\s*(?P<reference>{_REFERENCE})",
    re.IGNORECASE,
)


def resolve_internal_reference_relations(
    document: EngineeringDocument,
) -> dict[str, tuple[SemanticRelation, ...]]:
    """Return resolved same-document clause-reference relations by source clause id.

    Only references that resolve uniquely against the current document are emitted.
    Existing semantic relation typing is deliberately not inferred beyond the generic
    ``references`` relation kind.
    """
    by_reference: dict[str, list[Clause]] = {}
    for clause in document.clauses:
        by_reference.setdefault(_normalize_reference(clause.reference.clause), []).append(clause)

    return {
        clause.id.value: _relations_for_clause(clause, by_reference) for clause in document.clauses
    }


def _relations_for_clause(
    clause: Clause,
    by_reference: dict[str, list[Clause]],
) -> tuple[SemanticRelation, ...]:
    text = clause.plain_text
    occupied: list[tuple[int, int]] = []
    relations: list[SemanticRelation] = []

    for match in _RANGE_RE.finditer(text):
        occupied.append(match.span())
        for group in ("start", "end"):
            reference = match.group(group)
            relation = _resolved_relation(reference, clause.id.value, by_reference)
            if relation is not None:
                relations.append(relation)

    for match in _SINGLE_RE.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        reference = match.group("reference")
        normalized = _normalize_reference(reference)
        if match.group("prefix") is None and normalized not in by_reference:
            continue
        relation = _resolved_relation(reference, clause.id.value, by_reference)
        if relation is not None:
            relations.append(relation)

    unique: dict[tuple[str, str], SemanticRelation] = {}
    for relation in relations:
        unique[(relation.target_clause_id or "", relation.display_text or "")] = relation
    return tuple(unique.values())


def _resolved_relation(
    reference: str,
    source_clause_id: str,
    by_reference: dict[str, list[Clause]],
) -> SemanticRelation | None:
    candidates = [
        candidate
        for candidate in by_reference.get(_normalize_reference(reference), ())
        if candidate.id.value != source_clause_id
    ]
    if len(candidates) != 1:
        return None
    target = candidates[0]
    return SemanticRelation(
        kind=SemanticRelationKind.REFERENCES,
        scope=RelationScope.INTERNAL,
        target_reference=target.reference.clause,
        target_clause_id=target.id.value,
        display_text=reference,
        confidence=1.0,
        rationale="deterministically resolved same-document clause reference",
    )


def _normalize_reference(value: str) -> str:
    return value.strip().rstrip(".,;:)").casefold()
