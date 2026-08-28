"""Compose canonical physical parts into runtime publication projections."""

from __future__ import annotations

import hashlib

from standards_atlas.application.model import PublicationDocument
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    EngineeringDocument,
)
from standards_atlas.domain.model.identifiers import StandardReference


class DocumentCompositionError(ValueError):
    """Raised when document views cannot be composed safely."""


class DocumentCompositionService:
    """Build a runtime-only family publication from canonical physical parts."""

    def __init__(self, documents: EngineeringDocumentRepository) -> None:
        self._documents = documents

    def compose(
        self,
        family_key: str,
        part_keys: tuple[str, ...],
        *,
        family_title: str | None = None,
    ) -> PublicationDocument:
        parts = tuple(self._documents.load(DocumentKey(value=key)) for key in part_keys)
        if not parts:
            raise DocumentCompositionError(f"Part documents for {family_key!r} contain no parts.")

        composed_clauses: list[Clause] = []
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

        first = parts[0]
        return PublicationDocument(
            key=DocumentKey(value=family_key),
            title=family_title or _family_title(first, family_key),
            clauses=tuple(composed_clauses),
            annotations=tuple(annotation for part in parts for annotation in part.annotations),
            tables=tuple(table for part in parts for table in part.tables),
            table_index=tuple(entry for part in parts for entry in part.table_index),
            source_artifacts=tuple(
                part.lineage.artifact for part in parts if part.lineage is not None
            ),
            part_keys=part_keys,
        )

    def project(self, document_key: str) -> PublicationDocument:
        """Project one canonical physical document into the publication model."""
        return PublicationDocument.from_engineering_document(
            self._documents.load(DocumentKey(value=document_key))
        )

    def list_physical(self) -> tuple[PublicationDocument, ...]:
        """Return runtime projections of all readable canonical physical documents."""
        return tuple(
            PublicationDocument.from_engineering_document(document)
            for document in self._documents.list_readable()
        )


def _family_title(document: EngineeringDocument, family_key: str) -> str:
    title = document.title.strip()
    for separator in (" - Part ", "-Part ", " Part "):
        if separator in title:
            return title.split(separator, 1)[0].strip()
    return family_key


def _part_root_clause(part: EngineeringDocument) -> Clause:
    """Return the persisted part root or derive a publication-only root."""
    roots = [clause for clause in part.clauses if clause.reference.clause.strip() == "0"]
    if len(roots) > 1:
        raise DocumentCompositionError(
            f"Part document {part.key.value!r} must contain at most one clause 0 "
            f"root, got {len(roots)}."
        )
    if roots:
        return roots[0]

    volumes = {
        clause.reference.part for clause in part.clauses if clause.reference.part is not None
    }
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
        reference=StandardReference(standard=standard, year=year, clause="0", part=volume),
        clause_type=ClauseType.TOC,
        heading=f"Part {volume.replace('§', '-')}",
    )
