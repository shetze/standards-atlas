"""Deterministic projection from PublicationDocument to Gemara GuidanceCatalog."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from standards_atlas import __version__
from standards_atlas.adapters.gemara.models import (
    GemaraActor,
    GemaraGroup,
    GemaraGuidanceCatalog,
    GemaraGuideline,
    GemaraMetadata,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import Clause, ClauseType
from standards_atlas.domain.model.structural_profile import CanonicalDocumentSection

DEFAULT_GEMARA_VERSION = "v0.17.0-dev"

_OMITTED_SECTIONS = {
    CanonicalDocumentSection.FRONT_MATTER,
    CanonicalDocumentSection.REFERENCES,
    CanonicalDocumentSection.BIBLIOGRAPHY,
    CanonicalDocumentSection.BACK_MATTER,
}
_OMITTED_TYPES = {ClauseType.TOC, ClauseType.TABLE}


class GemaraGuidanceMapper:
    """Build a Gemara GuidanceCatalog without invoking interpretation or LLMs."""

    def __init__(self, *, gemara_version: str = DEFAULT_GEMARA_VERSION) -> None:
        self._gemara_version = gemara_version

    def map(self, document: PublicationDocument) -> GemaraGuidanceCatalog:
        root_group_id = gemara_id(f"{document.key.value}-root")
        children = _children_by_parent(document.clauses)
        group_clause_ids = {
            clause.id.value
            for clause in document.clauses
            if children.get(clause.id.value) and _is_structural_group_candidate(clause)
        }

        groups: list[GemaraGroup] = [
            GemaraGroup(
                id=root_group_id,
                title=document.title,
                description=f"Guidance projected from {document.title}.",
            )
        ]
        for clause in document.clauses:
            if clause.id.value not in group_clause_ids:
                continue
            title = _clause_title(clause)
            groups.append(
                GemaraGroup(
                    id=gemara_id(clause.id.value),
                    title=title,
                    description=f"Section {clause.reference.as_text()}: {title}",
                )
            )

        _ensure_unique_ids((group.id for group in groups), kind="group")

        known_ids = {clause.id.value: clause for clause in document.clauses}
        guidelines: list[GemaraGuideline] = []
        for clause in document.clauses:
            if not _is_exportable_guideline(clause):
                continue
            group_id = _nearest_group_id(
                clause,
                known_ids=known_ids,
                group_clause_ids=group_clause_ids,
                root_group_id=root_group_id,
            )
            guidelines.append(
                GemaraGuideline(
                    id=gemara_id(clause.id.value),
                    title=_clause_title(clause),
                    objective=clause.plain_text.strip(),
                    group=group_id,
                    state="Active",
                )
            )

        _ensure_unique_ids((guideline.id for guideline in guidelines), kind="guideline")

        description = f"Gemara guidance projection of {document.title}."
        if document.source:
            description += f" Source: {document.source}."

        return GemaraGuidanceCatalog(
            title=document.title,
            metadata=GemaraMetadata(
                id=gemara_id(document.key.value),
                **{"gemara-version": self._gemara_version},
                version=(
                    document.version or (str(document.year) if document.year is not None else None)
                ),
                description=description,
                author=GemaraActor(
                    id="standards-atlas",
                    name="Standards Atlas",
                    type="Software",
                    version=__version__,
                ),
            ),
            type="Standard",
            groups=tuple(groups),
            guidelines=tuple(guidelines),
        )


def gemara_id(value: str) -> str:
    """Return a stable, conservative Gemara identifier."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not normalized:
        raise ValueError(f"Cannot derive Gemara id from {value!r}.")
    return normalized


def _children_by_parent(clauses: tuple[Clause, ...]) -> dict[str, tuple[Clause, ...]]:
    children: dict[str, list[Clause]] = defaultdict(list)
    for clause in clauses:
        if clause.parent_id is not None:
            children[clause.parent_id.value].append(clause)
    return {key: tuple(value) for key, value in children.items()}


def _is_structural_group_candidate(clause: Clause) -> bool:
    return clause.clause_type not in _OMITTED_TYPES and not _is_omitted_section(clause)


def _is_exportable_guideline(clause: Clause) -> bool:
    if clause.clause_type in _OMITTED_TYPES or _is_omitted_section(clause):
        return False
    return bool(clause.plain_text.strip())


def _is_omitted_section(clause: Clause) -> bool:
    profile = clause.structural_profile
    return profile is not None and profile.canonical_section in _OMITTED_SECTIONS


def _nearest_group_id(
    clause: Clause,
    *,
    known_ids: dict[str, Clause],
    group_clause_ids: set[str],
    root_group_id: str,
) -> str:
    parent_id = clause.parent_id
    visited: set[str] = set()
    while parent_id is not None and parent_id.value not in visited:
        visited.add(parent_id.value)
        if parent_id.value in group_clause_ids:
            return gemara_id(parent_id.value)
        parent = known_ids.get(parent_id.value)
        if parent is None:
            break
        parent_id = parent.parent_id
    return root_group_id


def _clause_title(clause: Clause) -> str:
    heading = (clause.heading or "").strip()
    if heading:
        return heading
    return clause.reference.as_text()


def _ensure_unique_ids(values: Iterable[str], *, kind: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"Gemara {kind} id collision after normalization: {value!r}.")
        seen.add(value)
