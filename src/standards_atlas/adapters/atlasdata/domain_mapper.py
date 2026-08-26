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
    DocumentStructure,
    DocumentStructureClassification,
    DocumentTable,
    DocumentTableId,
    NormativeStatus,
    SemanticClassification,
    Standard,
    StandardKey,
    StandardReference,
    TableIndexEntry,
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
    semantic_tag_lookup = _build_semantic_tag_lookup(atlas_data)
    semantic_profile = atlas_data.metadata.extra_fields.get("semanticProfile")

    annex_statuses = _annex_statuses(atlas_data, title_lookup)
    clauses = tuple(
        _map_structure_item_to_clause(
            item=item,
            standard_name=atlas_data.metadata.name,
            year=atlas_data.metadata.official_year,
            title=title_lookup.get((item.volume, item.visible_reference)),
            semantic_tags=semantic_tag_lookup.get((item.volume, item.visible_reference), ()),
            semantic_profile=semantic_profile,
            annex_status=annex_statuses.get(
                (item.volume, item.visible_reference.split(".", 1)[0]),
                NormativeStatus.UNSPECIFIED,
            ),
        )
        for item in atlas_data.structure_items
    )

    clauses = _materialize_parent_hierarchy(clauses)
    clauses_by_reference = {(clause.volume, clause.reference.clause): clause for clause in clauses}

    annotations = _map_initialization_records_to_annotations(
        atlas_data=atlas_data,
        clauses_by_reference=clauses_by_reference,
    )
    tables, table_index = _map_table_records(
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
        tables=tables,
        table_index=table_index,
        annotations=annotations,
    )


def _materialize_parent_hierarchy(clauses: tuple[Clause, ...]) -> tuple[Clause, ...]:
    """Attach each clause to its nearest materialized structural parent.

    AtlasData structure expansion yields a flat sequence.  The canonical domain
    model carries the hierarchy explicitly through ``Clause.parent_id``.  Resolve
    the nearest existing dotted reference within the same volume, falling back to
    the synthetic ``0`` root when present.
    """
    by_identity = {(clause.volume, clause.reference.clause.strip()): clause for clause in clauses}
    materialized: list[Clause] = []

    for clause in clauses:
        reference = clause.reference.clause.strip()
        parent: Clause | None = None
        candidate = reference

        while "." in candidate:
            candidate = candidate.rsplit(".", 1)[0]
            parent = by_identity.get((clause.volume, candidate))
            if parent is not None:
                break

        if parent is None and reference != "0":
            parent = by_identity.get((clause.volume, "0"))

        materialized.append(
            clause.model_copy(update={"parent_id": parent.id if parent is not None else None})
        )

    return tuple(materialized)


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


def _build_semantic_tag_lookup(
    atlas_data: AtlasStandardData,
) -> dict[tuple[str | None, str], tuple[str, ...]]:
    result: dict[tuple[str | None, str], tuple[str, ...]] = {}
    for record in atlas_data.initialization_records:
        if record.kind != "TOC" or not record.semantic_tags:
            continue
        identity = _extract_clause_identity(record.reference, atlas_data.metadata.name)
        if identity is not None:
            result[identity] = record.semantic_tags
    return result


def _merge_semantic_tags(
    classification: SemanticClassification,
    *,
    semantic_tags: tuple[str, ...],
    semantic_profile: str | None,
) -> SemanticClassification:
    if not semantic_tags:
        return classification
    if not semantic_profile or ":" not in semantic_profile:
        raise ValueError("AtlasData semantic tags require semanticProfile metadata")
    task, version = semantic_profile.rsplit(":", 1)
    from standards_atlas.adapters.atlasdata.semantic_tags import (
        decode_semantic_tags,
        is_supported_semantic_profile,
    )

    if not is_supported_semantic_profile(task):
        raise ValueError(f"Unsupported AtlasData semantic profile: {semantic_profile!r}")
    from standards_atlas.domain.model import (
        ApplicabilityFunction,
        DocumentStructure,
        DocumentStructureClassification,
        KnowledgeKind,
        ProcessFunction,
        RoleRelationType,
        StatementFunction,
    )

    decoded = decode_semantic_tags(semantic_tags, version=version)
    statements = (
        *decoded["primary_statement_function"],
        *decoded["secondary_statement_functions"],
    )
    update: dict[str, object] = {}
    if statements:
        update["statement_functions"] = tuple(StatementFunction(value) for value in statements)
    if decoded["knowledge_kinds"]:
        update["knowledge_kinds"] = tuple(
            KnowledgeKind(value) for value in decoded["knowledge_kinds"]
        )
    if decoded["process_functions"]:
        update["process_functions"] = tuple(
            ProcessFunction(value) for value in decoded["process_functions"]
        )
    if decoded["applicability_functions"]:
        update["applicability_functions"] = tuple(
            ApplicabilityFunction(value) for value in decoded["applicability_functions"]
        )
    if decoded["role_relation_types"]:
        update["role_semantics_present"] = True
        update["role_relation_types"] = tuple(
            RoleRelationType(value) for value in decoded["role_relation_types"]
        )
    if decoded["document_structure"]:
        update["document_structure"] = DocumentStructureClassification(
            family="public_semantic_annotation",
            category=DocumentStructure(decoded["document_structure"][0]),
        )
    if decoded["normative_status"]:
        update["normative_status"] = NormativeStatus(decoded["normative_status"][0])
    return classification.model_copy(update=update)


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
    annex_status: NormativeStatus,
    semantic_tags: tuple[str, ...] = (),
    semantic_profile: str | None = None,
) -> Clause:
    structural_profile = _infer_structural_profile(
        visible_reference=item.visible_reference,
        title=title,
    )
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
        semantic_classification=_merge_semantic_tags(
            _structural_compatibility_classification(
                structural_profile=structural_profile,
                clause_type=_ITEM_TYPE_MAPPING[item.item_type],
                annex_status=annex_status,
            ),
            semantic_tags=semantic_tags,
            semantic_profile=semantic_profile,
        ),
        structural_profile=structural_profile,
        title=title,
        source_token=item.source_token,
        volume=item.volume,
        enum_prefix=item.enum_prefix,
        identifier_width=item.identifier_width,
    )


def _structural_compatibility_classification(
    *,
    structural_profile,
    clause_type: ClauseType,
    annex_status: NormativeStatus,
) -> SemanticClassification:
    """Mirror structural facts into legacy fields without semantic inference.

    ``SemanticClassification`` remains part of the persisted schema for relations and
    imported public annotations. Taxonomy owns structure; this adapter only mirrors
    structural facts needed by older consumers and never infers ontology dimensions.
    """
    from standards_atlas.domain.model.structural_profile import CanonicalDocumentSection

    section_map = {
        CanonicalDocumentSection.FRONT_MATTER: DocumentStructure.FRONT_MATTER,
        CanonicalDocumentSection.INTRODUCTION: DocumentStructure.INTRODUCTION,
        CanonicalDocumentSection.SCOPE: DocumentStructure.SCOPE,
        CanonicalDocumentSection.REFERENCES: DocumentStructure.REFERENCES,
        CanonicalDocumentSection.TERMINOLOGY: DocumentStructure.TERMINOLOGY,
        CanonicalDocumentSection.BODY: DocumentStructure.BODY,
        CanonicalDocumentSection.ANNEX: DocumentStructure.ANNEX,
        CanonicalDocumentSection.BIBLIOGRAPHY: DocumentStructure.BIBLIOGRAPHY,
        CanonicalDocumentSection.BACK_MATTER: DocumentStructure.BACK_MATTER,
    }
    category = section_map.get(structural_profile.canonical_section)
    if clause_type is ClauseType.SCOPE:
        category = DocumentStructure.SCOPE
    elif clause_type is ClauseType.TERM:
        category = DocumentStructure.TERMINOLOGY
    structure = (
        DocumentStructureClassification(family="structural_taxonomy", category=category)
        if category is not None
        else None
    )
    return SemanticClassification(
        document_structure=structure,
        normative_status=annex_status,
    )


def _annex_statuses(
    atlas_data: AtlasStandardData,
    title_lookup: dict[tuple[str | None, str], str],
) -> dict[tuple[str | None, str], NormativeStatus]:
    statuses: dict[tuple[str | None, str], NormativeStatus] = {}
    for item in atlas_data.structure_items:
        reference = item.visible_reference
        if not reference.isalpha():
            continue
        title = title_lookup.get((item.volume, reference), "")
        match = re.search(r"\b(normative|informative)\b", title, re.I)
        if match is not None:
            statuses[(item.volume, reference)] = NormativeStatus(match.group(1).lower())
    return statuses


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


def _infer_structural_profile(
    *,
    visible_reference: str,
    title: str | None,
):
    from standards_atlas.adapters.structure_taxonomies import (
        ResourceStructuralTaxonomyDefinitionRepository,
    )
    from standards_atlas.application.structure import (
        StructuralTaxonomyContext,
        StructuralTaxonomyEngine,
        builtin_structural_taxonomy_registry,
    )

    return StructuralTaxonomyEngine(
        builtin_structural_taxonomy_registry(),
        definitions=ResourceStructuralTaxonomyDefinitionRepository(),
    ).classify(
        StructuralTaxonomyContext(
            reference=visible_reference,
            heading=title or "",
        ),
        document_taxonomy=("document.iec-directives-2", "1.0.0"),
    )


_TABLE_REFERENCE_PATTERN = re.compile(r"^Table\s+(?P<reference>\S+)$", re.IGNORECASE)


def _map_table_records(
    *,
    atlas_data: AtlasStandardData,
    clauses_by_reference: dict[tuple[str | None, str], Clause],
) -> tuple[tuple[DocumentTable, ...], tuple[TableIndexEntry, ...]]:
    declared: dict[tuple[str | None, str], DocumentTable] = {}
    listed: dict[tuple[str | None, str], str | None] = {}

    for record in atlas_data.initialization_records:
        if record.kind not in {"TABLE", "TABLEINDEX"}:
            continue
        identity = _extract_table_identity(record.reference, atlas_data.metadata.name)
        if identity is None:
            continue
        volume, table_reference = identity
        key = (volume, table_reference)
        if record.kind == "TABLEINDEX":
            listed[key] = record.content.strip() or None
            continue
        parent_reference = record.type_marker.strip() or None
        parent = clauses_by_reference.get((volume, parent_reference)) if parent_reference else None
        declared[key] = DocumentTable(
            id=_build_table_id(
                standard_name=atlas_data.metadata.name,
                year=atlas_data.metadata.official_year,
                volume=volume,
                table_reference=table_reference,
            ),
            reference=table_reference,
            title=record.content.strip() or None,
            parent_clause_id=parent.id if parent is not None else None,
            parent_clause_reference=parent_reference,
            sequence_index=len(declared),
            listed_in_table_index=key in listed,
        )

    # TABLEINDEX may precede TABLE in hand-maintained AtlasData.
    tables = tuple(
        table.model_copy(update={"listed_in_table_index": key in listed})
        for key, table in declared.items()
    )
    table_by_key = {key: table for key, table in zip(declared, tables, strict=True)}
    index_entries = tuple(
        TableIndexEntry(
            reference=reference,
            title=title,
            table_id=table_by_key[key].id if key in table_by_key else None,
        )
        for key, title in listed.items()
        for _, reference in (key,)
    )
    return tables, index_entries


def _extract_table_identity(reference: str, standard_name: str) -> tuple[str | None, str] | None:
    if not reference.startswith(standard_name):
        return None
    remainder = reference[len(standard_name) :].strip()
    match = re.search(r"(?:^|\s)Table\s+(?P<table>\S+)\s*$", remainder, re.IGNORECASE)
    if match is None:
        return None
    document_reference = remainder[: match.start()].strip()
    volume: str | None = None
    before_year = document_reference.split(":", maxsplit=1)[0]
    if before_year.startswith("-") and len(before_year) > 1:
        volume = before_year[1:].replace("-", "§", 1) if "-" in before_year[1:] else before_year[1:]
    return volume, match.group("table")


def _build_table_id(
    *, standard_name: str, year: int | None, volume: str | None, table_reference: str
) -> DocumentTableId:
    raw = "|".join((standard_name, str(year or ""), volume or "", "table", table_reference))
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return DocumentTableId(value=f"table-{digest}")
