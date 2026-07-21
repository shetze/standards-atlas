"""Map parsed Atlas data into the canonical domain model."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from standards_atlas.adapters.atlasdata.parser import AtlasStandardData, parse_standard_file
from standards_atlas.adapters.atlasdata.structure_expander import StructureItem
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType
from standards_atlas.domain.model import (
    AnnotationId,
    AnnotationType,
    AnnotationVisibility,
    Clause,
    ClauseAnnotation,
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


def map_atlas_data_to_standard(
    atlas_data: AtlasStandardData,
    *,
    key: str,
) -> Standard:
    title_lookup = _build_title_lookup(atlas_data)

    clauses = tuple(
        _map_structure_item_to_clause(
            item=item,
            standard_name=atlas_data.metadata.name,
            year=atlas_data.metadata.official_year,
            title=title_lookup.get((item.volume, item.visible_reference)),
            text=None,
        )
        for item in atlas_data.structure_items
    )

    clauses_by_reference = {(clause.volume, clause.reference.clause): clause for clause in clauses}

    annotations = _map_initialization_records_to_annotations(
        atlas_data=atlas_data,
        clauses_by_reference=clauses_by_reference,
    )

    return Standard(
        key=StandardKey(value=key),
        title=atlas_data.metadata.name,
        name=atlas_data.metadata.name,
        year=atlas_data.metadata.official_year,
        parent_key=(
            StandardKey(value=atlas_data.metadata.parent) if atlas_data.metadata.parent else None
        ),
        clauses=clauses,
        annotations=annotations,
    )


def _map_initialization_records_to_annotations(
    *,
    atlas_data: AtlasStandardData,
    clauses_by_reference: dict[tuple[str | None, str], Clause],
) -> tuple[ClauseAnnotation, ...]:
    annotations: list[ClauseAnnotation] = []

    for index, record in enumerate(atlas_data.initialization_records):
        clause_identity = _extract_clause_identity(
            record.reference,
            atlas_data.metadata.name,
        )

        if clause_identity is None:
            continue

        clause = clauses_by_reference.get(clause_identity)

        if clause is None or not record.content.strip():
            continue

        if record.kind == "TOC":
            annotation_type = AnnotationType.TITLE
            visibility = AnnotationVisibility.PUBLIC
        elif record.kind == "PublicTXT":
            annotation_type = AnnotationType.COMMENT
            visibility = AnnotationVisibility.PUBLIC
        elif record.kind == "LocalTXT":
            annotation_type = AnnotationType.COMMENT
            visibility = AnnotationVisibility.LOCAL
        else:
            continue

        annotations.append(
            ClauseAnnotation(
                id=_build_annotation_id(
                    kind=record.kind,
                    reference=record.reference,
                    content=record.content,
                    index=index,
                ),
                clause_id=clause.id,
                annotation_type=annotation_type,
                visibility=visibility,
                content=record.content,
                source="atlasdata",
            )
        )

    return tuple(annotations)


def _build_title_lookup(
    atlas_data: AtlasStandardData,
) -> dict[tuple[str | None, str], str]:
    titles: dict[tuple[str | None, str], str] = {}

    for record in atlas_data.initialization_records:
        if record.kind != "TOC":
            continue

        clause_identity = _extract_clause_identity(
            record.reference,
            atlas_data.metadata.name,
        )

        if clause_identity is not None:
            titles[clause_identity] = record.content

    return titles


def _build_annotation_id(
    *,
    kind: str,
    reference: str,
    content: str,
    index: int,
) -> AnnotationId:
    raw = f"{kind}|{reference}|{content}|{index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    return AnnotationId(value=f"annotation-{digest}")


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

    if "annex" in normalized_title or re.match(r"^[A-Z]+(?:\.|$)", visible_reference):
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


def _extract_clause_identity(reference: str, standard_name: str) -> tuple[str | None, str] | None:
    """Extract ``(volume, clause)`` from an AtlasData initialization reference."""
    if not reference.startswith(standard_name):
        return None

    remainder = reference[len(standard_name) :].strip()
    if not remainder:
        return None

    document_reference, separator, clause_reference = remainder.partition(" ")
    if not separator or not clause_reference.strip():
        return None

    volume: str | None = None
    before_year = document_reference.split(":", maxsplit=1)[0]
    if before_year.startswith("-") and len(before_year) > 1:
        volume = before_year[1:].replace("-", "§", 1) if "-" in before_year[1:] else before_year[1:]

    return volume, clause_reference.strip()
