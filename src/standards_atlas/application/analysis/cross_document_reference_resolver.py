"""Resolve explicit references to clauses in other available documents."""

from __future__ import annotations

import re
from collections.abc import Iterable

from standards_atlas.domain.model import (
    Clause,
    EngineeringDocument,
    RelationScope,
    SemanticRelation,
    SemanticRelationKind,
)

_REFERENCE = r"\d+(?:\.\d+){1,7}(?:[a-z])?"
_REFERENCE_PREFIX = r"(?:clauses?|subclauses?|paragraphs?)"


def resolve_cross_document_reference_relations(
    document: EngineeringDocument,
    available_documents: Iterable[EngineeringDocument],
) -> EngineeringDocument:
    """Materialize unambiguous explicit references to clauses in available documents.

    Resolution is deliberately conservative: the referenced document must be named in
    the text (using its key, title, or clause standard designation), followed by a
    clause reference that resolves uniquely in that document.
    """
    documents = tuple(available_documents)
    aliases = _document_aliases(documents)
    patterns = tuple(
        (
            alias,
            targets,
            re.compile(
                rf"(?<![\w-])(?P<document>{re.escape(alias)})"
                rf"(?:\s*:\s*\d{{4}})?"
                rf"\s*(?:,|;|—|–|-)\s*"
                rf"(?:{_REFERENCE_PREFIX}\s+)?"
                rf"(?P<reference>{_REFERENCE})(?![\w]|[.]\d)",
                re.IGNORECASE,
            ),
        )
        for alias, targets in aliases
    )

    clauses: list[Clause] = []
    for clause in document.clauses:
        detected: list[SemanticRelation] = []
        for alias, target_documents, pattern in patterns:
            for match in pattern.finditer(clause.plain_text):
                relation = _resolve_match(
                    source_document=document,
                    source_clause=clause,
                    target_documents=target_documents,
                    matched_alias=alias,
                    reference=match.group("reference"),
                    display_text=match.group(0),
                )
                if relation is not None:
                    detected.append(relation)
        clauses.append(_merge_relations(clause, detected))
    return document.model_copy(update={"clauses": tuple(clauses)})


def _document_aliases(
    documents: tuple[EngineeringDocument, ...],
) -> tuple[tuple[str, tuple[EngineeringDocument, ...]], ...]:
    candidates: dict[str, tuple[str, dict[str, EngineeringDocument]]] = {}
    for document in documents:
        values = {document.key.value, document.title}
        values.update(
            _reference_designation(clause)
            for clause in document.clauses
            if clause.reference.standard.strip()
        )
        for value in values:
            for alias in _alias_variants(value):
                normalized = alias.casefold()
                if normalized not in candidates:
                    candidates[normalized] = (alias, {})
                candidates[normalized][1][document.key.value] = document

    aliases = [(alias, tuple(targets.values())) for alias, targets in candidates.values()]
    return tuple(sorted(aliases, key=lambda item: len(item[0]), reverse=True))


def _reference_designation(clause: Clause) -> str:
    standard = clause.reference.standard.strip()
    return f"{standard}-{clause.reference.part}" if clause.reference.part else standard


def _alias_matches_clause(alias: str, clause: Clause) -> bool:
    """Constrain part-qualified aliases to clauses from that same part."""
    normalized_alias = re.sub(r"[^a-z0-9]", "", alias.casefold())
    standard = re.sub(r"[^a-z0-9]", "", clause.reference.standard.casefold())
    part = clause.reference.part
    if not part:
        return True
    normalized_part = re.sub(r"[^a-z0-9]", "", part.casefold())
    qualified = f"{standard}{normalized_part}"
    if normalized_alias == qualified:
        return True
    # Unqualified standard aliases remain valid, but ambiguity across parts is
    # deliberately preserved by the candidate cardinality check below.
    return normalized_alias == standard or not normalized_alias.startswith(standard)


def _alias_variants(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"\s+", " ", value.strip())
    without_year = re.sub(r"\s*:\s*\d{4}(?:-\d{2})?\s*$", "", cleaned)
    variants = {cleaned, without_year}
    compact = re.sub(r"(?<=[A-Za-z])\s+(?=\d)", "", without_year)
    variants.add(compact)
    spaced = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", without_year)
    variants.add(spaced)
    return tuple(item for item in variants if len(item) >= 4)


def _resolve_match(
    *,
    source_document: EngineeringDocument,
    source_clause: Clause,
    target_documents: tuple[EngineeringDocument, ...],
    matched_alias: str,
    reference: str,
    display_text: str,
) -> SemanticRelation | None:
    normalized = _normalize_reference(reference)
    candidates = [
        (target_document, candidate)
        for target_document in target_documents
        for candidate in target_document.clauses
        if _normalize_reference(candidate.reference.clause) == normalized
        and _alias_matches_clause(matched_alias, candidate)
        and not (target_document.key == source_document.key and candidate.id == source_clause.id)
    ]
    by_clause_id: dict[str, list[tuple[EngineeringDocument, Clause]]] = {}
    for candidate in candidates:
        by_clause_id.setdefault(candidate[1].id.value, []).append(candidate)
    if len(by_clause_id) != 1:
        return None

    equivalent = next(iter(by_clause_id.values()))
    target_document, target = min(
        equivalent,
        key=lambda item: _target_preference(item[0], source_document, matched_alias),
    )
    scope = (
        RelationScope.INTERNAL
        if target_document.key == source_document.key
        else RelationScope.EXTERNAL
    )
    return SemanticRelation(
        kind=SemanticRelationKind.REFERENCES,
        scope=scope,
        target_reference=target.reference.clause,
        target_clause_id=target.id.value,
        target_document_key=(
            target_document.key.value if scope is RelationScope.EXTERNAL else None
        ),
        display_text=display_text,
        confidence=1.0,
        rationale="deterministically resolved explicit cross-document clause reference",
    )


def _target_preference(
    target: EngineeringDocument,
    source: EngineeringDocument,
    matched_alias: str,
) -> tuple[int, int, int, str]:
    normalized_alias = re.sub(r"[^a-z0-9]", "", matched_alias.casefold())
    normalized_key = re.sub(r"[^a-z0-9]", "", target.key.value.casefold())
    return (
        0 if target.key == source.key else 1,
        0 if normalized_key == normalized_alias else 1,
        len(target.key.value),
        target.key.value,
    )


def _merge_relations(clause: Clause, detected: list[SemanticRelation]) -> Clause:
    current = clause.semantic_classification
    keys = {
        (
            relation.kind,
            relation.scope,
            relation.target_reference,
            relation.target_clause_id,
            relation.target_document_key,
            relation.display_text,
        )
        for relation in current.relations
    }
    merged = list(current.relations)
    for relation in detected:
        key = (
            relation.kind,
            relation.scope,
            relation.target_reference,
            relation.target_clause_id,
            relation.target_document_key,
            relation.display_text,
        )
        if key not in keys:
            merged.append(relation)
            keys.add(key)
    if len(merged) == len(current.relations):
        return clause
    return clause.model_copy(
        update={"semantic_classification": current.model_copy(update={"relations": tuple(merged)})}
    )


def _normalize_reference(value: str) -> str:
    return value.strip().rstrip(".,;:)").casefold()
