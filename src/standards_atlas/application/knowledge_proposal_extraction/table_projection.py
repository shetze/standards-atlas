"""Deterministic projection of supported structured tables into knowledge proposals."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from standards_atlas.application.formal_semantics import ResourceFormalOntologyRepository
from standards_atlas.application.services.knowledge_table_service import (
    KnowledgeTableProjectionService,
)
from standards_atlas.domain.model import (
    FORMAL_SEMANTIC_NAMESPACE,
    Clause,
    DocumentKnowledgeProposal,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    KnowledgeConcept,
    KnowledgeConceptKind,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    KnowledgeRelationKind,
    KnowledgeTable,
    KnowledgeTableKind,
    NormativeAssertionProposal,
    NormativeForce,
    NoteBlock,
    TableBlock,
)
from standards_atlas.domain.model.content import render_block_as_plain_text

TABLE_KNOWLEDGE_PROJECTION_VERSION = "1.0.0"


@dataclass(frozen=True)
class _ProjectionRule:
    source_kind: KnowledgeConceptKind
    target_kind: KnowledgeConceptKind
    source_class: str
    target_class: str
    predicate: str
    reverse: bool = False


@dataclass(frozen=True)
class _CellLocation:
    anchor_row: int
    anchor_column: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class _RenderedContent:
    text: str
    target_offset: int | None = None


_RULES = {
    KnowledgeTableKind.WORK_PRODUCT_MATRIX: _ProjectionRule(
        source_kind=KnowledgeConceptKind.ACTIVITY,
        target_kind=KnowledgeConceptKind.WORK_PRODUCT,
        source_class=f"{FORMAL_SEMANTIC_NAMESPACE}Activity",
        target_class=f"{FORMAL_SEMANTIC_NAMESPACE}WorkProduct",
        predicate=f"{FORMAL_SEMANTIC_NAMESPACE}producedBy",
        reverse=True,
    ),
    KnowledgeTableKind.RESPONSIBILITY_MATRIX: _ProjectionRule(
        source_kind=KnowledgeConceptKind.ROLE,
        target_kind=KnowledgeConceptKind.SUBJECT,
        source_class=f"{FORMAL_SEMANTIC_NAMESPACE}Role",
        target_class=f"{FORMAL_SEMANTIC_NAMESPACE}EngineeringEntity",
        predicate=f"{FORMAL_SEMANTIC_NAMESPACE}responsibleFor",
    ),
    KnowledgeTableKind.TRACEABILITY_MATRIX: _ProjectionRule(
        source_kind=KnowledgeConceptKind.SOURCE,
        target_kind=KnowledgeConceptKind.TARGET,
        source_class=f"{FORMAL_SEMANTIC_NAMESPACE}EngineeringEntity",
        target_class=f"{FORMAL_SEMANTIC_NAMESPACE}EngineeringEntity",
        predicate=f"{FORMAL_SEMANTIC_NAMESPACE}tracesTo",
    ),
    KnowledgeTableKind.VERIFICATION_CRITERIA_MATRIX: _ProjectionRule(
        source_kind=KnowledgeConceptKind.SUBJECT,
        target_kind=KnowledgeConceptKind.CRITERION,
        source_class=f"{FORMAL_SEMANTIC_NAMESPACE}EngineeringEntity",
        target_class=f"{FORMAL_SEMANTIC_NAMESPACE}Criterion",
        predicate=f"{FORMAL_SEMANTIC_NAMESPACE}requires",
    ),
}

_EXPECTED_RELATIONS = {
    KnowledgeTableKind.WORK_PRODUCT_MATRIX: KnowledgeRelationKind.PRODUCES,
    KnowledgeTableKind.RESPONSIBILITY_MATRIX: KnowledgeRelationKind.RESPONSIBLE_FOR,
    KnowledgeTableKind.TRACEABILITY_MATRIX: KnowledgeRelationKind.TRACES_TO,
    KnowledgeTableKind.VERIFICATION_CRITERIA_MATRIX: KnowledgeRelationKind.VERIFIED_BY,
}


class TableKnowledgeProposalProjector:
    """Project supported deterministic table semantics into proposal contracts.

    This projector intentionally does not perform document-level entity resolution. Repeated
    labels in independent cells remain separate entity proposals until Slice 6B. Row-spanning
    cells retain one stable entity identity because they refer to the same structural source cell.
    """

    def __init__(
        self,
        *,
        table_service: KnowledgeTableProjectionService | None = None,
        ontology_repository: ResourceFormalOntologyRepository | None = None,
    ) -> None:
        self._table_service = table_service or KnowledgeTableProjectionService()
        self._ontology_repository = ontology_repository or ResourceFormalOntologyRepository()

    def project_document(
        self,
        document: EngineeringDocument,
        *,
        proposal_run_id: str,
        ontology_versions: tuple[str, ...],
    ) -> DocumentKnowledgeProposal:
        declared_classes, declared_properties = _declared_terms(
            ontology_versions, self._ontology_repository
        )
        clause_by_id = {clause.id.value: clause for clause in document.clauses}

        anchors: dict[str, EvidenceAnchor] = {}
        entities: dict[str, KnowledgeEntityProposal] = {}
        assertions: list[NormativeAssertionProposal] = []

        for table in self._table_service.project_document(document):
            rule = _RULES.get(table.kind)
            if rule is None:
                continue
            _validate_rule(rule, declared_classes, declared_properties)
            clause = clause_by_id.get(table.parent_clause_id)
            if clause is None:
                raise ValueError(
                    f"knowledge table {table.id.value!r} references unknown parent clause "
                    f"{table.parent_clause_id!r}"
                )
            table_block = _find_table_block(clause, table.table_block_id)
            cell_locations = _cell_locations(clause, table_block)
            expected_relation = _EXPECTED_RELATIONS[table.kind]

            for record in table.records:
                semantic = record.structured_knowledge
                if semantic is None:
                    continue
                concepts = {concept.id: concept for concept in semantic.concepts}
                for relation in semantic.relations:
                    if relation.kind is not expected_relation:
                        raise ValueError(
                            f"knowledge table {table.id.value!r} has unexpected relation "
                            f"{relation.kind.value!r} for kind {table.kind.value!r}"
                        )
                    source = concepts[relation.source_concept_id]
                    target = concepts[relation.target_concept_id]
                    _require_concept_kind(source, rule.source_kind, table)
                    _require_concept_kind(target, rule.target_kind, table)

                    source_anchor = _anchor_for_concept(
                        clause,
                        table,
                        record.row_index,
                        source,
                        cell_locations,
                    )
                    target_anchor = _anchor_for_concept(
                        clause,
                        table,
                        record.row_index,
                        target,
                        cell_locations,
                    )
                    anchors[source_anchor.id] = source_anchor
                    anchors[target_anchor.id] = target_anchor

                    source_entity = _entity_proposal(
                        document_key=document.key.value,
                        table=table,
                        concept=source,
                        class_iri=rule.source_class,
                        anchor=source_anchor,
                    )
                    target_entity = _entity_proposal(
                        document_key=document.key.value,
                        table=table,
                        concept=target,
                        class_iri=rule.target_class,
                        anchor=target_anchor,
                    )
                    entities[source_entity.id] = source_entity
                    entities[target_entity.id] = target_entity

                    if rule.reverse:
                        subject = target_entity
                        object_entity = source_entity
                    else:
                        subject = source_entity
                        object_entity = target_entity
                    assertion_anchor_ids = tuple(
                        dict.fromkeys((source_anchor.id, target_anchor.id))
                    )
                    assertions.append(
                        _assertion_proposal(
                            document_key=document.key.value,
                            table=table,
                            row_index=record.row_index,
                            clause=clause,
                            subject=subject,
                            predicate=rule.predicate,
                            object_entity=object_entity,
                            evidence_anchor_ids=assertion_anchor_ids,
                        )
                    )

        return DocumentKnowledgeProposal(
            proposal_run_id=proposal_run_id,
            source_document_key=document.key.value,
            ontology_versions=ontology_versions,
            evidence_anchors=tuple(anchors.values()),
            entity_proposals=tuple(entities.values()),
            assertion_proposals=tuple(assertions),
            proposal_provenance=KnowledgeProposalProvenance(
                extractor="structured-table-projector",
                extractor_version=TABLE_KNOWLEDGE_PROJECTION_VERSION,
                semantic_task="structured-table-knowledge-projection",
            ),
        )


def _declared_terms(
    ontology_versions: tuple[str, ...],
    repository: ResourceFormalOntologyRepository,
) -> tuple[set[str], set[str]]:
    classes: set[str] = set()
    properties: set[str] = set()
    for reference in ontology_versions:
        ontology_id, version = reference.rsplit("@", 1)
        vocabulary = repository.declared_vocabulary(ontology_id, version)
        classes.update(vocabulary.classes)
        properties.update(vocabulary.properties)
    return classes, properties


def _validate_rule(
    rule: _ProjectionRule,
    classes: set[str],
    properties: set[str],
) -> None:
    missing_classes = {rule.source_class, rule.target_class} - classes
    if missing_classes:
        raise ValueError(
            "structured table projection classes are not declared by the selected "
            f"ontologies: {sorted(missing_classes)!r}"
        )
    if rule.predicate not in properties:
        raise ValueError(
            "structured table projection property is not declared by the selected "
            f"ontologies: {rule.predicate!r}"
        )


def _require_concept_kind(
    concept: KnowledgeConcept,
    expected: KnowledgeConceptKind,
    table: KnowledgeTable,
) -> None:
    if concept.kind is not expected:
        raise ValueError(
            f"knowledge table {table.id.value!r} expected concept kind {expected.value!r}, "
            f"got {concept.kind.value!r}"
        )


def _entity_proposal(
    *,
    document_key: str,
    table: KnowledgeTable,
    concept: KnowledgeConcept,
    class_iri: str,
    anchor: EvidenceAnchor,
) -> KnowledgeEntityProposal:
    normalized_label = _normalize_label(concept.label)
    identity = json.dumps(
        {
            "document_key": document_key,
            "table_id": table.id.value,
            "anchor_id": anchor.id,
            "class_iri": class_iri,
            "normalized_label": normalized_label,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    aliases = (concept.label,) if concept.label != normalized_label else ()
    return KnowledgeEntityProposal(
        id=f"entity:{document_key}:table:{digest}",
        class_iri=class_iri,
        normalized_label=normalized_label,
        aliases=aliases,
        source_anchor_ids=(anchor.id,),
        confidence=1.0,
        rationale=(
            f"Deterministic {table.kind.value} projection from source column "
            f"{concept.source_column_index}."
        ),
    )


def _assertion_proposal(
    *,
    document_key: str,
    table: KnowledgeTable,
    row_index: int,
    clause: Clause,
    subject: KnowledgeEntityProposal,
    predicate: str,
    object_entity: KnowledgeEntityProposal,
    evidence_anchor_ids: tuple[str, ...],
) -> NormativeAssertionProposal:
    identity = json.dumps(
        {
            "document_key": document_key,
            "table_id": table.id.value,
            "row_index": row_index,
            "subject_id": subject.id,
            "predicate": predicate,
            "object_id": object_entity.id,
            "evidence_anchor_ids": evidence_anchor_ids,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return NormativeAssertionProposal(
        id=f"assertion:{document_key}:table:{digest}",
        source_clause_id=clause.id,
        subject_id=subject.id,
        predicate=predicate,
        object=EntityAssertionObject(entity_id=object_entity.id),
        normative_force=NormativeForce.UNSPECIFIED,
        evidence_anchor_ids=evidence_anchor_ids,
        confidence=1.0,
        rationale=(
            f"Deterministic relation projected from a recognized {table.kind.value} row; "
            "normative force is not inferred from table shape."
        ),
    )


def _anchor_for_concept(
    clause: Clause,
    table: KnowledgeTable,
    row_index: int,
    concept: KnowledgeConcept,
    locations: dict[tuple[int, int], _CellLocation],
) -> EvidenceAnchor:
    location = locations.get((row_index, concept.source_column_index))
    if location is None:
        raise ValueError(
            f"knowledge table {table.id.value!r} cannot ground row {row_index}, "
            f"column {concept.source_column_index} in clause {clause.id.value!r}"
        )
    evidence_text = clause.plain_text[location.start_offset : location.end_offset]
    if not evidence_text:
        raise ValueError(
            f"knowledge table {table.id.value!r} resolved an empty source cell at row "
            f"{row_index}, column {concept.source_column_index}"
        )
    digest = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()
    anchor_identity = (
        f"{clause.id.value}|{table.table_block_id}|{location.anchor_row}|"
        f"{location.anchor_column}|{location.start_offset}|{location.end_offset}|{digest}"
    )
    anchor_digest = hashlib.sha256(anchor_identity.encode("utf-8")).hexdigest()[:20]
    return EvidenceAnchor(
        id=f"evidence:{clause.id.value}:table:{anchor_digest}",
        clause_id=clause.id,
        start_offset=location.start_offset,
        end_offset=location.end_offset,
        content_hash=digest,
    )


def _find_table_block(clause: Clause, table_block_id: str) -> TableBlock:
    matches = tuple(_iter_table_blocks(clause.content, table_block_id))
    if len(matches) != 1:
        raise ValueError(
            f"clause {clause.id.value!r} must contain exactly one table block "
            f"{table_block_id!r}; found {len(matches)}"
        )
    return matches[0]


def _iter_table_blocks(content: tuple[object, ...], target_id: str):
    for block in content:
        if isinstance(block, TableBlock):
            if block.id == target_id:
                yield block
        elif isinstance(block, NoteBlock):
            yield from _iter_table_blocks(block.content, target_id)


def _cell_locations(clause: Clause, table: TableBlock) -> dict[tuple[int, int], _CellLocation]:
    rendered = _render_content_with_target(clause.content, table.id)
    if rendered.text != clause.plain_text:
        raise ValueError(
            f"table evidence renderer drifted from canonical clause text for {clause.id.value!r}"
        )
    if rendered.target_offset is None:
        raise ValueError(
            f"table block {table.id!r} is not addressable in clause {clause.id.value!r}"
        )

    raw_table = render_block_as_plain_text(table)
    left_trim = len(raw_table) - len(raw_table.lstrip())
    grid: dict[tuple[int, int], _CellLocation] = {}
    occupied: set[tuple[int, int]] = set()
    cursor = len(table.caption) + 1 if table.caption else 0

    for row_index, row in enumerate(table.rows):
        if row_index:
            cursor += 1
        column_index = 0
        for cell_index, cell in enumerate(row.cells):
            while (row_index, column_index) in occupied:
                column_index += 1
            if cell_index:
                cursor += 3
            cell_start = cursor
            cursor += len(cell.text)
            trimmed = cell.text.strip()
            location = None
            if trimmed:
                leading = len(cell.text) - len(cell.text.lstrip())
                local_start = cell_start + leading - left_trim
                local_end = local_start + len(trimmed)
                start = rendered.target_offset + local_start
                end = rendered.target_offset + local_end
                if start < 0 or end > len(clause.plain_text):
                    raise ValueError(
                        f"table cell offsets exceed canonical clause text for {clause.id.value!r}"
                    )
                if clause.plain_text[start:end] != trimmed:
                    raise ValueError(
                        f"table cell evidence does not match canonical clause text for "
                        f"{clause.id.value!r} row {row_index}, column {column_index}"
                    )
                location = _CellLocation(
                    anchor_row=row_index,
                    anchor_column=column_index,
                    start_offset=start,
                    end_offset=end,
                )
            for covered_row in range(row_index, row_index + cell.row_span):
                for covered_column in range(column_index, column_index + cell.column_span):
                    key = (covered_row, covered_column)
                    if key in occupied:
                        raise ValueError(
                            f"table spans overlap at row {covered_row}, column {covered_column}: "
                            f"{table.id}"
                        )
                    occupied.add(key)
                    if location is not None:
                        grid[key] = location
            column_index += cell.column_span

    return grid


def _render_content_with_target(content: tuple[object, ...], target_id: str) -> _RenderedContent:
    parts: list[str] = []
    target_offset: int | None = None
    cursor = 0
    for block in content:
        rendered = _render_block_with_target(block, target_id)
        stripped = rendered.text.strip()
        if not stripped:
            continue
        if parts:
            cursor += 2
        left_trim = len(rendered.text) - len(rendered.text.lstrip())
        if rendered.target_offset is not None:
            if target_offset is not None:
                raise ValueError(f"duplicate table block id in clause content: {target_id!r}")
            target_offset = cursor + rendered.target_offset - left_trim
        parts.append(stripped)
        cursor += len(stripped)
    return _RenderedContent(text="\n\n".join(parts), target_offset=target_offset)


def _render_block_with_target(block: object, target_id: str) -> _RenderedContent:
    if isinstance(block, TableBlock):
        return _RenderedContent(
            text=render_block_as_plain_text(block),
            target_offset=0 if block.id == target_id else None,
        )
    if isinstance(block, NoteBlock):
        body = _render_content_with_target(block.content, target_id)
        if block.note_kind and body.text:
            prefix = f"{block.note_kind}: "
            return _RenderedContent(
                text=f"{prefix}{body.text}",
                target_offset=(
                    len(prefix) + body.target_offset if body.target_offset is not None else None
                ),
            )
        if block.note_kind:
            return _RenderedContent(text=block.note_kind)
        return body
    return _RenderedContent(text=render_block_as_plain_text(block))


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)
