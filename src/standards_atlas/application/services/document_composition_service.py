"""Compose physical part documents into rebuildable publication views."""

from __future__ import annotations

import hashlib

from standards_atlas.application.model import ComposedDocumentView
from standards_atlas.application.ports import (
    ComposedDocumentViewStore,
    EngineeringDocumentRepository,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    EngineeringDocument,
)
from standards_atlas.domain.model.identifiers import StandardKey, StandardReference
from standards_atlas.domain.model.standard import Standard


class DocumentCompositionError(ValueError):
    """Raised when document views cannot be composed safely."""


class DocumentCompositionService:
    """Build a publication-only family view from canonical physical parts."""

    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        views: ComposedDocumentViewStore,
    ) -> None:
        self._documents = documents
        self._views = views

    def compose(
        self,
        family_key: str,
        part_keys: tuple[str, ...],
        *,
        family_title: str | None = None,
    ) -> ComposedDocumentView:
        parts = [self._documents.load(DocumentKey(value=key)) for key in part_keys]
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

        document = _publication_document(
            family_key,
            tuple(parts),
            tuple(composed_clauses),
            family_title=family_title,
        )
        view = ComposedDocumentView(
            family_key=family_key,
            part_keys=part_keys,
            document=document,
        )
        self._views.save(view)
        family_document_key = DocumentKey(value=family_key)
        if self._documents.exists(family_document_key):
            self._documents.delete(family_document_key)
        return view


def _publication_document(
    family_key: str,
    parts: tuple[EngineeringDocument, ...],
    clauses: tuple[Clause, ...],
    *,
    family_title: str | None,
) -> EngineeringDocument:
    first = parts[0]
    title = family_title or _family_title(first, family_key)
    annotations = tuple(annotation for part in parts for annotation in part.annotations)
    tables = tuple(table for part in parts for table in part.tables)
    table_index = tuple(entry for part in parts for entry in part.table_index)
    common = {
        "title": title,
        "clauses": clauses,
        "annotations": annotations,
        "tables": tables,
        "table_index": table_index,
    }
    if isinstance(first, Standard):
        return first.model_copy(
            update={
                **common,
                "key": StandardKey(value=family_key),
                "name": title,
                "parent_key": None,
            }
        )
    return first.model_copy(update={**common, "key": DocumentKey(value=family_key)})


def _family_title(document: EngineeringDocument, family_key: str) -> str:
    title = document.title.strip()
    for separator in (" - Part ", "-Part ", " Part "):
        if separator in title:
            return title.split(separator, 1)[0].strip()
    return family_key


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
