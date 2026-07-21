"""Compose enriched physical document views into their logical family document."""

from __future__ import annotations

import hashlib
from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    EngineeringDocument,
    StandardReference,
)


class DocumentCompositionError(ValueError):
    """Raised when document views cannot be composed safely."""


class DocumentCompositionService:
    """Merge enriched child views into a persisted family document."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)

    def compose(self, family_key: str, part_keys: tuple[str, ...]) -> EngineeringDocument:
        family = self._documents.load(DocumentKey(value=family_key))
        parts = [self._documents.load(DocumentKey(value=key)) for key in part_keys]

        composed_clauses = []
        seen: set[ClauseId] = set()
        for part in parts:
            root = _part_root_clause(part)
            ordered_clauses = (root, *(clause for clause in part.clauses if clause.id != root.id))
            for clause in ordered_clauses:
                if clause.id in seen:
                    raise DocumentCompositionError(
                        f"Clause {clause.id.value!r} occurs in more than one part document."
                    )
                seen.add(clause.id)
                composed_clauses.append(clause)

        if not composed_clauses:
            raise DocumentCompositionError(f"Part documents for {family_key!r} contain no clauses.")

        composed = family.model_copy(update={"clauses": tuple(composed_clauses)})
        self._documents.save(composed)
        return composed


def _part_root_clause(part: EngineeringDocument) -> Clause:
    """Return a persisted part root or create one for legacy supplements."""
    roots = [clause for clause in part.clauses if clause.reference.clause.strip() == "0"]
    if len(roots) > 1:
        raise DocumentCompositionError(
            f"Part document {part.key.value!r} must contain at most one clause 0 "
            f"root, got {len(roots)}."
        )
    if roots:
        return roots[0]

    volumes = {clause.volume for clause in part.clauses if clause.volume is not None}
    if len(volumes) != 1:
        raise DocumentCompositionError(
            f"Part document {part.key.value!r} without a clause 0 root must contain "
            f"exactly one volume, got {sorted(volumes)!r}."
        )
    volume = next(iter(volumes))

    references = {(clause.reference.standard, clause.reference.year) for clause in part.clauses}
    if len(references) != 1:
        raise DocumentCompositionError(
            f"Part document {part.key.value!r} without a clause 0 root contains "
            "multiple standard references."
        )
    standard, year = next(iter(references))
    digest = hashlib.sha1(f"{standard}|{year or ''}|{volume}|root".encode()).hexdigest()[:12]
    return Clause(
        id=ClauseId(value=f"clause-{digest}"),
        reference=StandardReference(standard=standard, year=year, clause="0"),
        clause_type=ClauseType.TOC,
        title=f"Part {volume.replace('§', '-')}",
        volume=volume,
    )
