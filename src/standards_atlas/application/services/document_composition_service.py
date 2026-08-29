"""Compose canonical physical parts into runtime publication projections."""

from __future__ import annotations

from standards_atlas.application.model import PublicationDocument
from standards_atlas.application.ports import EngineeringDocumentRepository
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    EngineeringDocument,
)


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
            root = _part_publication_root(part)
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


def _part_publication_root(part: EngineeringDocument) -> Clause:
    """Return the persisted part root or a runtime-only supplement root.

    Canonical physical parts are expected to persist exactly one clause-0 root.
    Supplements are represented by a hierarchical part reference such as ``3§1``
    and may legitimately start at clause 1.  Publication composition supplies a
    synthetic root for those supplements only; the canonical EngineeringDocument
    remains unchanged.
    """
    roots = [clause for clause in part.clauses if clause.reference.clause.strip() == "0"]
    if len(roots) == 1:
        return roots[0]
    if len(roots) > 1:
        raise DocumentCompositionError(
            f"Part document {part.key.value!r} must contain exactly one clause 0 root, "
            f"got {len(roots)}."
        )
    if _is_supplement(part):
        return _supplement_publication_root(part)
    raise DocumentCompositionError(
        f"Part document {part.key.value!r} must contain exactly one clause 0 root, got 0."
    )


def _is_supplement(part: EngineeringDocument) -> bool:
    volumes = {
        clause.reference.part for clause in part.clauses if clause.reference.part is not None
    }
    return len(volumes) == 1 and "§" in next(iter(volumes), "")


def _supplement_publication_root(part: EngineeringDocument) -> Clause:
    if not part.clauses:
        raise DocumentCompositionError(
            f"Supplement document {part.key.value!r} contains no clauses."
        )
    first = part.clauses[0]
    return Clause(
        id=ClauseId(value=f"{part.key.value}-publication-root"),
        reference=first.reference.model_copy(update={"clause": "0"}),
        clause_type=ClauseType.TOC,
        heading=part.title,
    )
