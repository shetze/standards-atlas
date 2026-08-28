"""Map PublicationDocument objects to Doorstop export items."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import replace

from standards_atlas.adapters.doorstop.id_generator import (
    DoorstopIdContext,
    generate_doorstop_id,
    generate_doorstop_level,
    required_doorstop_id_width,
)
from standards_atlas.adapters.doorstop.models import DoorstopItemModel
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    AnnotationType,
    Clause,
    ClauseAnnotation,
    ClauseType,
)
from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopReference,
)


class DoorstopItemMapper:
    """Maps PublicationDocument clauses to Doorstop items."""

    def __init__(
        self,
        *,
        prefix: str,
        separator: str,
        id_context: DoorstopIdContext,
    ) -> None:
        self._prefix = prefix
        self._separator = separator
        self._id_context = id_context

    def map_document(
        self,
        document: PublicationDocument,
    ) -> tuple[DoorstopItemModel, ...]:
        """Map all clauses of a document."""

        annotations = self._group_annotations(document)
        clauses = tuple(
            clause for clause in document.clauses if clause.clause_type != ClauseType.TABLE
        )
        context = _document_id_context(clauses, self._id_context)
        _ensure_identifier_width(document, clauses, context)

        items = tuple(
            self._map_clause(
                clause,
                annotations.get(clause.id.value, ()),
                context,
            )
            for clause in clauses
        )
        _ensure_unique_uids(items)
        return items

    def _map_clause(
        self,
        clause: Clause,
        annotations: tuple[ClauseAnnotation, ...],
        context: DoorstopIdContext,
    ) -> DoorstopItemModel:
        numeric_id = generate_doorstop_id(
            visible_reference=clause.reference.clause,
            volume=clause.reference.part,
            enum_prefix=clause.enum_prefix,
            identifier_width=clause.identifier_width,
            context=context,
        )

        uid = f"{self._prefix}{self._separator}{numeric_id}"

        doorstop = clause.doorstop
        qualified_reference = _qualified_reference(clause)

        return DoorstopItemModel(
            uid=uid,
            level=(
                doorstop.level
                if doorstop and doorstop.level is not None
                else _doorstop_level(clause, context)
            ),
            header=self._select_header(
                clause,
                annotations,
            ),
            text=self._render_text(
                clause,
                annotations,
            ),
            active=(doorstop.active if doorstop and doorstop.active is not None else True),
            derived=(doorstop.derived if doorstop and doorstop.derived is not None else False),
            normative=(
                doorstop.normative if doorstop and doorstop.normative is not None else False
            ),
            reviewed=(doorstop.reviewed if doorstop else None),
            links=(doorstop.links if doorstop else ()),
            references=(
                doorstop.references
                if doorstop and doorstop.references
                else (
                    DoorstopReference(
                        keyword=qualified_reference,
                        path=r".*\.md",
                        type="pattern",
                    ),
                )
            ),
            attributes={
                **(doorstop.extended if doorstop else {}),
                "idx": qualified_reference,
                "standard": {
                    "name": clause.reference.standard,
                    "numID": numeric_id,
                    "refID": _generate_reference_hash(qualified_reference),
                },
                "atlas-clause-id": clause.id.value,
                "atlas-reference": qualified_reference,
                "atlas-clause-type": clause.clause_type.value,
                "statement-functions": [
                    role.value for role in clause.semantic_classification.statement_functions
                ],
                **_structural_profile_attributes(clause),
            },
        )

    @staticmethod
    def _select_header(
        clause: Clause,
        annotations: tuple[ClauseAnnotation, ...],
    ) -> str:
        title_annotations = [
            annotation.content.strip()
            for annotation in annotations
            if annotation.annotation_type == AnnotationType.TITLE and annotation.content.strip()
        ]

        if title_annotations:
            return title_annotations[-1]

        if clause.heading:
            return clause.heading

        return ""

    @staticmethod
    def _render_text(
        clause: Clause,
        annotations: tuple[ClauseAnnotation, ...],
    ) -> str:
        sections: list[str] = []

        if clause.plain_text:
            sections.append(clause.plain_text.strip())

        grouped: dict[AnnotationType, list[str]] = defaultdict(list)

        for annotation in annotations:
            if annotation.annotation_type == AnnotationType.TITLE:
                continue

            grouped[annotation.annotation_type].append(annotation.content.strip())

        for annotation_type in AnnotationType:
            contents = grouped.get(annotation_type)

            if not contents:
                continue

            heading = annotation_type.value.replace(
                "_",
                " ",
            ).title()

            sections.append(f"## {heading}\n\n" + "\n\n".join(contents))

        return "\n\n".join(sections)

    @staticmethod
    def _group_annotations(
        document: PublicationDocument,
    ) -> dict[str, tuple[ClauseAnnotation, ...]]:
        grouped: dict[str, list[ClauseAnnotation]] = defaultdict(list)

        for annotation in document.annotations:
            grouped[annotation.clause_id.value].append(annotation)

        return {clause_id: tuple(values) for clause_id, values in grouped.items()}


def _ensure_identifier_width(
    document: PublicationDocument,
    clauses: tuple[Clause, ...],
    context: DoorstopIdContext,
) -> None:
    """Fail early when the configured document UID width is insufficient."""
    if not clauses:
        return

    required = max(
        required_doorstop_id_width(
            visible_reference=clause.reference.clause,
            volume=clause.reference.part,
            enum_prefix=clause.enum_prefix,
            identifier_width=clause.identifier_width,
            context=context,
        )
        for clause in clauses
    )
    if required <= context.digits:
        return

    raise ValueError(
        f"Doorstop identifier width {context.digits} is insufficient for "
        f"{document.key.value}; minimum required width is {required}."
    )


def _document_id_context(
    clauses: tuple[Clause, ...],
    context: DoorstopIdContext,
) -> DoorstopIdContext:
    """Reserve a fixed-width namespace for the document volume hierarchy."""
    volumes = tuple(
        clause.reference.part for clause in clauses if clause.reference.part is not None
    )
    if not volumes:
        return context

    volume_depth = max(len(volume.split("§")) for volume in volumes)
    return replace(context, volume_depth=volume_depth)


def _qualified_reference(clause: Clause) -> str:
    """Return a clause reference qualified by its physical part."""
    standard = clause.reference.standard
    if clause.reference.part is not None:
        part = clause.reference.part.replace("§", "-")
        standard = f"{standard}-{part}"
    if clause.reference.year is None:
        return f"{standard} {clause.reference.clause}"
    return f"{standard}:{clause.reference.year} {clause.reference.clause}"


@staticmethod
def _generate_reference_hash(reference: str) -> str:
    return hashlib.md5(reference.encode("utf-8")).hexdigest()


def _doorstop_level(clause: Clause, context: DoorstopIdContext) -> str:
    """Nest clauses below a distinct root for every physical part."""
    level = generate_doorstop_level(
        visible_reference=clause.reference.clause,
        enum_prefix=clause.enum_prefix,
    )
    if clause.reference.part is None:
        return level
    root_level = _volume_root_level(clause.reference.part, context)
    if clause.reference.clause == "0":
        return root_level
    return f"{root_level}.{level}"


def _volume_root_level(volume: str, context: DoorstopIdContext) -> str:
    components = volume.split("§")
    if any(not component.isdigit() for component in components):
        raise ValueError(f"Volume hierarchy must be numeric, got {volume!r}.")
    primary = int(components[0]) + context.part_shift
    if primary < 0:
        raise ValueError(f"Shifted volume must not be negative, got {primary}.")
    if len(components) == 1:
        return str(primary)
    encoded = str(primary) + "".join(f"{int(component):02d}" for component in components[1:])
    return str(int(encoded))


def _structural_profile_attributes(clause: Clause) -> dict[str, object]:
    profile = clause.structural_profile
    if profile is None:
        return {}
    return {
        "structural-profile": profile.model_dump(mode="json", exclude_none=True),
    }


def _ensure_unique_uids(items: tuple[DoorstopItemModel, ...]) -> None:
    by_uid: dict[str, list[DoorstopItemModel]] = defaultdict(list)
    for item in items:
        by_uid[item.uid].append(item)

    duplicates = {uid: values for uid, values in by_uid.items() if len(values) > 1}
    if not duplicates:
        return

    details = "; ".join(
        f"{uid} ({', '.join(str(item.attributes.get('atlas-reference', '')) for item in values)})"
        for uid, values in sorted(duplicates.items())
    )
    raise ValueError(f"Duplicate Doorstop item UID(s): {details}")
