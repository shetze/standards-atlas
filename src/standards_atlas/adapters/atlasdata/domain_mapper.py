"""Map parsed Atlas data into the canonical domain model."""

from __future__ import annotations

import hashlib
from pathlib import Path

from standards_atlas.adapters.atlasdata.parser import AtlasStandardData, parse_standard_file
from standards_atlas.adapters.atlasdata.structure_expander import StructureItem
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType, TYPE_PREFIXES
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    SemanticRole,
    Standard,
    StandardKey,
    StandardReference,
)


_ITEM_TYPE_MAPPING: dict[AtlasItemType, ClauseType] = {
    AtlasItemType.TOC: ClauseType.TOC,
    AtlasItemType.CLAUSE: ClauseType.CLAUSE,
    AtlasItemType.REQUIREMENT: ClauseType.REQUIREMENT,
    AtlasItemType.SCOPE: ClauseType.SCOPE,
    AtlasItemType.TERM: ClauseType.TERM,
    AtlasItemType.OBJECTIVE: ClauseType.OBJECTIVE,
    AtlasItemType.MISC: ClauseType.MISC,
}


def parse_standard_domain_file(path: Path, *, key: str | None = None) -> Standard:
    """Parse an Atlas data file and map it into the canonical domain model.

    Prefer AtlasDataImporter for application code.
    """
    atlas_data = parse_standard_file(path)
    standard_key = key or path.name

    return map_atlas_data_to_standard(atlas_data, key=standard_key)


def map_atlas_data_to_standard(atlas_data: AtlasStandardData, *, key: str) -> Standard:
    """Map parsed Atlas data into a Standard domain object."""
    title_lookup, text_lookup = _build_initialization_lookup(atlas_data)

    clauses = tuple(
        _map_structure_item_to_clause(
            item=item,
            standard_name=atlas_data.metadata.name,
            year=atlas_data.metadata.official_year,
            title=title_lookup.get(item.visible_reference),
            text=text_lookup.get(item.visible_reference),
        )
        for item in atlas_data.structure_items
    )

    return Standard(
        key=StandardKey(value=key),
        title=atlas_data.metadata.name,
        name=atlas_data.metadata.name,
        year=atlas_data.metadata.official_year,
        parent_key=(
            StandardKey(value=atlas_data.metadata.parent)
            if atlas_data.metadata.parent
            else None
        ),
        clauses=clauses,
    )


def _map_structure_item_to_clause(
    *,
    item: StructureItem,
    standard_name: str,
    year: int | None,
    title: str | None,
    text: str | None,
) -> Clause:
    return Clause(
        id=_build_clause_id(
            standard_name=standard_name,
            year=item.publication_year or year,
            visible_reference=item.visible_reference,
            volume=item.volume,
        ),
        reference=StandardReference(
            standard=standard_name,
            year=item.publication_year or year,
            clause=item.visible_reference,
        ),
        clause_type=_ITEM_TYPE_MAPPING[item.item_type],
        semantic_roles=_infer_semantic_roles(
            clause_type=_ITEM_TYPE_MAPPING[item.item_type],
            visible_reference=item.visible_reference,
            title=title,
        ),
        title=title,
        text=text,
        source_token=item.source_token,
        volume=item.volume,
        enum_prefix=item.enum_prefix,
        identifier_width=item.identifier_width,
    )

def _infer_semantic_roles(
    *,
    clause_type: ClauseType,
    visible_reference: str,
    title: str | None,
) -> tuple[SemanticRole, ...]:
    """Infer semantic roles from clause type, reference and title.

    This is intentionally conservative. More advanced classification
    should later move into a dedicated semantic classification service.
    """
    roles: list[SemanticRole] = []

    normalized_title = (title or "").strip().lower()

    if clause_type == ClauseType.SCOPE:
        roles.append(SemanticRole.SCOPE)

    if clause_type == ClauseType.TERM:
        roles.append(SemanticRole.TERMS_AND_DEFINITIONS)

    if clause_type == ClauseType.OBJECTIVE:
        roles.append(SemanticRole.OBJECTIVES)

    if clause_type == ClauseType.REQUIREMENT:
        roles.append(SemanticRole.REQUIREMENTS)

    if "normative reference" in normalized_title:
        roles.append(SemanticRole.NORMATIVE_REFERENCES)

    if "terms and definition" in normalized_title:
        roles.append(SemanticRole.TERMS_AND_DEFINITIONS)

    if "abbreviation" in normalized_title:
        roles.append(SemanticRole.ABBREVIATIONS)

    if "objective" in normalized_title:
        roles.append(SemanticRole.OBJECTIVES)

    if "requirement" in normalized_title:
        roles.append(SemanticRole.REQUIREMENTS)

    if "recommendation" in normalized_title:
        roles.append(SemanticRole.RECOMMENDATIONS)

    if "input" in normalized_title:
        roles.append(SemanticRole.INPUTS)

    if "output" in normalized_title:
        roles.append(SemanticRole.OUTPUTS)

    if "work product" in normalized_title:
        roles.append(SemanticRole.WORK_PRODUCTS)

    if "annex" in normalized_title or visible_reference.startswith(("A", "B", "C", "D", "E", "F", "G", "ZZ")):
        roles.append(SemanticRole.ANNEX)

    if "bibliography" in normalized_title:
        roles.append(SemanticRole.BIBLIOGRAPHY)

    if "compliance" in normalized_title:
        roles.append(SemanticRole.COMPLIANCE)

    if "conformance" in normalized_title:
        roles.append(SemanticRole.CONFORMANCE)

    return tuple(dict.fromkeys(roles))

def _build_clause_id(
    *,
    standard_name: str,
    year: int | None,
    visible_reference: str,
    volume: str | None,
) -> ClauseId:
    """Build a stable internal clause identifier.

    This intentionally does not use the legacy hash field.
    """
    raw = "|".join(
        part
        for part in [
            standard_name,
            str(year) if year is not None else "",
            volume or "",
            visible_reference,
        ]
    )

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return ClauseId(value=f"clause-{digest}")


def _build_initialization_lookup(
    atlas_data: AtlasStandardData,
) -> tuple[dict[str, str], dict[str, str]]:
    title_lookup: dict[str, str] = {}
    text_lookup: dict[str, str] = {}

    for record in atlas_data.initialization_records:
        clause_ref = _extract_clause_reference(record.reference, atlas_data.metadata.name)

        if clause_ref is None:
            continue

        if record.kind == "TOC":
            title_lookup[clause_ref] = record.content
        elif record.kind == "TEXT":
            text_lookup[clause_ref] = record.content

    return title_lookup, text_lookup


def _extract_clause_reference(reference: str, standard_name: str) -> str | None:
    """Extract the visible clause part from a full standard reference.

    Example:
        EN 50716:2023 5.1.2 -> 5.1.2
    """
    if not reference.startswith(standard_name):
        return None

    remainder = reference[len(standard_name):].strip()

    if not remainder:
        return None

    parts = remainder.split(maxsplit=1)

    if len(parts) == 1:
        return None

    return parts[1].strip()
