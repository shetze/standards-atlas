"""Generate publicly distributable AtlasData initialization records."""

from __future__ import annotations

import hashlib

from standards_atlas.adapters.atlasdata.parser import InitializationRecord
from standards_atlas.domain.model import (
    AnnotationType,
    AnnotationVisibility,
    Clause,
    ClauseAnnotation,
    ClauseType,
    EngineeringDocument,
)

_TYPE_MARKERS: dict[ClauseType, str] = {
    ClauseType.TOC: "u",
    ClauseType.CLAUSE: "u",
    ClauseType.REQUIREMENT: "r",
    ClauseType.SCOPE: "s",
    ClauseType.TERM: "t",
    ClauseType.OBJECTIVE: "o",
    ClauseType.MISC: "m",
}


_DEFAULT_HEADINGS: dict[ClauseType, str] = {
    ClauseType.TOC: "Heading",
    ClauseType.CLAUSE: "Heading",
    ClauseType.REQUIREMENT: "Requirement",
    ClauseType.SCOPE: "Scope",
    ClauseType.TERM: "Term",
    ClauseType.OBJECTIVE: "Objective",
    ClauseType.MISC: "Misc",
}


def generate_toc_records(
    document: EngineeringDocument,
) -> list[InitializationRecord]:
    """Generate publicly distributable TOC records."""
    annotations_by_clause = _annotations_by_clause(document)

    return [
        _generate_toc_record(
            clause,
            annotations_by_clause.get(clause.id.value, ()),
        )
        for clause in document.clauses
    ]


def generate_public_text_records(
    document: EngineeringDocument,
) -> list[InitializationRecord]:
    """Generate PublicTXT records from explicitly public annotations.

    Clause.text is intentionally never exported.
    """
    clauses_by_id = {clause.id: clause for clause in document.clauses}

    records: list[InitializationRecord] = []

    for annotation in document.annotations:
        if annotation.visibility != AnnotationVisibility.PUBLIC:
            continue

        if annotation.annotation_type == AnnotationType.TITLE:
            continue

        clause = clauses_by_id.get(annotation.clause_id)

        if clause is None:
            continue

        records.append(
            _generate_public_text_record(
                clause=clause,
                annotation=annotation,
            )
        )

    return records


def generate_public_initialization_records(
    document: EngineeringDocument,
) -> list[InitializationRecord]:
    """Generate every record allowed in public AtlasData files."""
    return [
        *generate_toc_records(document),
        *generate_public_text_records(document),
    ]


def _generate_toc_record(
    clause: Clause,
    annotations: tuple[ClauseAnnotation, ...],
) -> InitializationRecord:
    reference = _atlasdata_reference(clause)

    return InitializationRecord(
        kind="TOC",
        hash_value=_hash_value(reference),
        reference=reference,
        content=_public_heading(clause, annotations),
        type_marker=_type_marker(clause),
    )


def _generate_public_text_record(
    *,
    clause: Clause,
    annotation: ClauseAnnotation,
) -> InitializationRecord:
    reference = _atlasdata_reference(clause)

    return InitializationRecord(
        kind="PublicTXT",
        hash_value=_hash_value(annotation.id.value),
        reference=reference,
        content=annotation.content,
        type_marker=_type_marker(clause),
    )


def _atlasdata_reference(clause: Clause) -> str:
    """Serialize a clause reference using AtlasData part notation."""
    standard = clause.reference.standard

    if clause.volume:
        part = clause.volume.replace("§", "-")
        standard = f"{standard}-{part}"

    if clause.reference.year is None:
        return f"{standard} {clause.reference.clause}"

    return f"{standard}:{clause.reference.year} {clause.reference.clause}"


def _public_heading(
    clause: Clause,
    annotations: tuple[ClauseAnnotation, ...],
) -> str:
    public_title_annotations = [
        annotation
        for annotation in annotations
        if annotation.visibility == AnnotationVisibility.PUBLIC
        and annotation.annotation_type == AnnotationType.TITLE
        and annotation.content.strip()
    ]

    if public_title_annotations:
        return public_title_annotations[-1].content.strip()

    if clause.title and clause.title.strip():
        return clause.title.strip()

    return _DEFAULT_HEADINGS.get(clause.clause_type, "Heading")


def _annotations_by_clause(
    document: EngineeringDocument,
) -> dict[str, tuple[ClauseAnnotation, ...]]:
    result: dict[str, list[ClauseAnnotation]] = {}

    for annotation in document.annotations:
        result.setdefault(annotation.clause_id.value, []).append(annotation)

    return {clause_id: tuple(annotations) for clause_id, annotations in result.items()}


def _type_marker(clause: Clause) -> str:
    return _TYPE_MARKERS.get(clause.clause_type, "u")


def _hash_value(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()
