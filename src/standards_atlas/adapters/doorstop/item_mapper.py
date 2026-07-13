"""Map EngineeringDocument objects to Doorstop export items."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from standards_atlas.adapters.doorstop.id_generator import (
    DoorstopIdContext,
    generate_doorstop_id,
    generate_doorstop_level,
)
from standards_atlas.adapters.doorstop.models import DoorstopItemModel
from standards_atlas.domain.model import (
    AnnotationType,
    Clause,
    ClauseAnnotation,
    EngineeringDocument,
)
from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopReference,
)


class DoorstopItemMapper:
    """Maps EngineeringDocument clauses to Doorstop items."""

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
        document: EngineeringDocument,
    ) -> tuple[DoorstopItemModel, ...]:
        """Map all clauses of a document."""

        annotations = self._group_annotations(document)

        return tuple(
            self._map_clause(
                clause,
                annotations.get(clause.id.value, ()),
            )
            for clause in document.clauses
        )

    def _map_clause(
        self,
        clause: Clause,
        annotations: tuple[ClauseAnnotation, ...],
    ) -> DoorstopItemModel:
        numeric_id = generate_doorstop_id(
            visible_reference=clause.reference.clause,
            volume=clause.volume,
            enum_prefix=clause.enum_prefix,
            identifier_width=clause.identifier_width,
            context=self._id_context,
        )

        uid = uid = f"{self._prefix}{self._separator}{numeric_id}"

        doorstop = clause.doorstop

        return DoorstopItemModel(
            uid=uid,
            level=(
                doorstop.level
                if doorstop and doorstop.level is not None
                else generate_doorstop_level(
                    visible_reference=clause.reference.clause,
                    enum_prefix=clause.enum_prefix,
                )
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
                        keyword=clause.reference.as_text(),
                        path=r".*\.md",
                        type="pattern",
                    ),
                )
            ),
            attributes={
                **(doorstop.extended if doorstop else {}),
                "idx": clause.reference.as_text(),
                "standard": {
                    "name": clause.reference.standard,
                    "numID": numeric_id,
                    "refID": _generate_reference_hash(clause.reference.as_text()),
                },
                "atlas-clause-id": clause.id.value,
                "atlas-reference": clause.reference.as_text(),
                "atlas-clause-type": clause.clause_type.value,
                "semantic-roles": [role.value for role in clause.semantic_roles],
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

        if clause.title:
            return clause.title

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
        document: EngineeringDocument,
    ) -> dict[str, tuple[ClauseAnnotation, ...]]:
        grouped: dict[str, list[ClauseAnnotation]] = defaultdict(list)

        for annotation in document.annotations:
            grouped[annotation.clause_id.value].append(annotation)

        return {clause_id: tuple(values) for clause_id, values in grouped.items()}


@staticmethod
def _generate_reference_hash(reference: str) -> str:
    return hashlib.md5(reference.encode("utf-8")).hexdigest()
