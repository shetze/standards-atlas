"""Deterministic semantic mapping from normalized tables to structured knowledge."""

from __future__ import annotations

import hashlib
import re

from standards_atlas.domain.model import (
    KnowledgeCell,
    KnowledgeConcept,
    KnowledgeConceptKind,
    KnowledgeRecord,
    KnowledgeRecordId,
    KnowledgeRecordSource,
    KnowledgeRelation,
    KnowledgeRelationKind,
    KnowledgeTable,
    KnowledgeTableId,
    KnowledgeTableKind,
    NormalizedTable,
    NormalizedTableCell,
    NormalizedTableRowKind,
    RecommendationLevel,
    StructuredKnowledgeRecord,
)
from standards_atlas.domain.model.knowledge_table import (
    IntegrityLevelRecommendation,
    TechniqueRecommendation,
)

MAPPING_VERSION = "1.0.0"

_CONTEXT_REFERENCE = re.compile(r"\bsee\s+((?:\d+\.)*\d+)\b", re.IGNORECASE)
_DESCRIPTION_REFERENCE = re.compile(r"\b([A-Z]\.\d+(?:\.\d+)*)\b")
_LOCAL_IDENTIFIER = re.compile(r"^\s*(\d+)([a-z])?\s*$", re.IGNORECASE)
_SIL_HEADER = re.compile(r"\bSIL\s*([1-4])\b", re.IGNORECASE)
_TABLE_REFERENCE = re.compile(r"\b(?:Table|Tabelle)\s+([A-Z0-9]+(?:[.-][A-Z0-9]+)*)", re.IGNORECASE)
_RECOMMENDATION_LEVELS = {
    "HR": RecommendationLevel.HIGHLY_RECOMMENDED,
    "R": RecommendationLevel.RECOMMENDED,
    "—": RecommendationLevel.NEUTRAL,
    "-": RecommendationLevel.NEUTRAL,
    "NR": RecommendationLevel.NOT_RECOMMENDED,
}

_PORTABLE_SCHEMAS: tuple[tuple[KnowledgeTableKind, tuple[tuple[str, ...], ...]], ...] = (
    (
        KnowledgeTableKind.RESPONSIBILITY_MATRIX,
        (
            ("role", "responsible", "responsibility", "owner"),
            ("activity", "task", "work product", "deliverable", "item"),
        ),
    ),
    (
        KnowledgeTableKind.TRACEABILITY_MATRIX,
        (("source", "from", "requirement"), ("target", "to", "trace", "linked")),
    ),
    (
        KnowledgeTableKind.WORK_PRODUCT_MATRIX,
        (("activity", "process", "task"), ("work product", "deliverable", "output")),
    ),
    (
        KnowledgeTableKind.VERIFICATION_CRITERIA_MATRIX,
        (
            ("subject", "item", "requirement", "work product"),
            ("criterion", "criteria", "verification", "acceptance"),
        ),
    ),
    (
        KnowledgeTableKind.APPLICABILITY_MATRIX,
        (
            ("subject", "item", "method", "requirement"),
            ("applicable", "applicability", "scope", "context", "condition"),
        ),
    ),
)


class StructuredKnowledgeMappingService:
    """Map T2 ``NormalizedTable`` projections into T3 knowledge records.

    Mapping is deliberately deterministic and schema-driven. Unknown or ambiguous
    tables remain generic and do not receive invented concepts or relations.
    """

    def map_tables(self, tables: tuple[NormalizedTable, ...]) -> tuple[KnowledgeTable, ...]:
        return tuple(self.map_table(table) for table in tables)

    def map_table(self, table: NormalizedTable) -> KnowledgeTable:
        table_id = KnowledgeTableId(
            value=_stable_table_id(table.document_key, table.parent_clause_id, table.table_block_id)
        )
        grid = _logical_grid(table)
        records = tuple(_knowledge_record(table, table_id, row.index) for row in table.rows)
        kind = KnowledgeTableKind.GENERIC
        context_references: tuple[str, ...] = ()

        if _is_iec61508_recommendation_table(table):
            kind = KnowledgeTableKind.TECHNIQUE_RECOMMENDATION_MATRIX
            context_references = _context_references(table.document_key, table.title)
            records = tuple(
                _with_technique_recommendation(
                    record,
                    table=table,
                    grid=grid,
                    context_references=context_references,
                )
                for record in records
            )
        else:
            portable_kind, columns = _portable_schema(table)
            if portable_kind is not KnowledgeTableKind.GENERIC and columns is not None:
                kind = portable_kind
                source_column, target_column = columns
                records = tuple(
                    _with_portable_knowledge(
                        record,
                        table=table,
                        grid=grid,
                        kind=kind,
                        source_column=source_column,
                        target_column=target_column,
                    )
                    for record in records
                )

        return KnowledgeTable(
            id=table_id,
            document_key=table.document_key,
            parent_clause_id=table.parent_clause_id,
            parent_clause_reference=table.parent_clause_reference,
            reference=_knowledge_table_reference(table),
            title=table.title,
            table_block_id=table.table_block_id,
            ordinal_in_clause=_ordinal_from_reference(table.reference),
            header_rows=_header_rows(table, grid),
            records=records,
            source_evidence=table.source_evidence,
            kind=kind,
            context_references=context_references,
            normalized_table_id=table.id,
            mapping_version=MAPPING_VERSION,
        )


def _knowledge_record(
    table: NormalizedTable,
    table_id: KnowledgeTableId,
    row_index: int,
) -> KnowledgeRecord:
    row = table.rows[row_index]
    return KnowledgeRecord(
        id=KnowledgeRecordId(value=f"{table_id.value}:row:{row_index + 1}"),
        table_id=table_id,
        document_key=table.document_key,
        parent_clause_id=table.parent_clause_id,
        parent_clause_reference=table.parent_clause_reference,
        row_index=row_index,
        cells=tuple(
            KnowledgeCell(
                column_index=cell.column_index,
                text=cell.text,
                row_span=cell.row_span,
                column_span=cell.column_span,
                is_header=cell.is_header,
            )
            for cell in row.cells
        ),
        is_header=row.kind is NormalizedTableRowKind.HEADER,
        source=KnowledgeRecordSource(
            table_block_id=table.table_block_id,
            row_index=row_index,
            source_evidence=table.source_evidence,
        ),
    )


def _logical_grid(table: NormalizedTable) -> dict[tuple[int, int], NormalizedTableCell]:
    grid: dict[tuple[int, int], NormalizedTableCell] = {}
    for row in table.rows:
        for cell in row.cells:
            for row_index in range(cell.row_index, cell.row_index + cell.row_span):
                for column_index in range(cell.column_index, cell.column_index + cell.column_span):
                    grid[(row_index, column_index)] = cell
    return grid


def _row_values(
    table: NormalizedTable,
    grid: dict[tuple[int, int], NormalizedTableCell],
    row_index: int,
) -> dict[int, str]:
    return {
        column.index: _normalize_text(grid[(row_index, column.index)].text)
        for column in table.columns
        if (row_index, column.index) in grid
    }


def _header_rows(
    table: NormalizedTable,
    grid: dict[tuple[int, int], NormalizedTableCell],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(
            _normalize_text(grid[(row_index, column_index)].text)
            if (row_index, column_index) in grid
            else ""
            for column_index in range(table.width)
        )
        for row_index in range(table.header_row_count)
    )


def _column_header(table: NormalizedTable, column_index: int) -> str:
    if column_index >= len(table.columns):
        return ""
    column = table.columns[column_index]
    return column.label or " / ".join(column.header_path)


def _is_iec61508_recommendation_table(table: NormalizedTable) -> bool:
    if not table.document_key.upper().replace(" ", "").startswith("IEC61508-3"):
        return False
    sil_count = sum(
        bool(_SIL_HEADER.search(_column_header(table, column.index))) for column in table.columns
    )
    signal = " ".join(
        [*(column.label or "" for column in table.columns), table.title or ""]
    ).casefold()
    return sil_count >= 2 and any(word in signal for word in ("technique", "method", "measure"))


def _with_technique_recommendation(
    record: KnowledgeRecord,
    *,
    table: NormalizedTable,
    grid: dict[tuple[int, int], NormalizedTableCell],
    context_references: tuple[str, ...],
) -> KnowledgeRecord:
    if record.is_header or table.rows[record.row_index].kind is not NormalizedTableRowKind.DATA:
        return record
    values = _row_values(table, grid, record.row_index)
    sil_columns = {
        column.index: f"SIL {match.group(1)}"
        for column in table.columns
        if (match := _SIL_HEADER.search(_column_header(table, column.index)))
    }
    recommendations = tuple(
        IntegrityLevelRecommendation(
            integrity_level=integrity_level,
            level=_RECOMMENDATION_LEVELS[marker],
            source_column_index=column_index,
            source_marker=values[column_index],
        )
        for column_index, integrity_level in sil_columns.items()
        if column_index in values
        and (marker := _normalize_marker(values[column_index])) in _RECOMMENDATION_LEVELS
    )
    if not recommendations:
        return record

    non_sil = [(index, value) for index, value in values.items() if index not in sil_columns]
    local_identifier = None
    alternative_group = None
    if non_sil and (match := _LOCAL_IDENTIFIER.fullmatch(non_sil[0][1])):
        local_identifier = non_sil.pop(0)[1]
        alternative_group = match.group(1) if match.group(2) else None

    reference_values: list[str] = []
    technique_candidates: list[tuple[int, str]] = []
    for index, value in non_sil:
        header = _column_header(table, index).casefold()
        refs = _DESCRIPTION_REFERENCE.findall(value)
        reference_column = any(signal in header for signal in ("ref", "clause", "see", "61508-7"))
        if refs and (reference_column or len(refs) * 5 >= len(value)):
            reference_values.extend(refs)
        elif value and _normalize_marker(value) not in _RECOMMENDATION_LEVELS:
            technique_candidates.append((index, value))
    if not technique_candidates:
        return record
    technique_column, technique = max(technique_candidates, key=lambda item: len(item[1]))
    technique_recommendation = TechniqueRecommendation(
        local_identifier=local_identifier,
        alternative_group=alternative_group,
        technique=technique,
        description_references=tuple(
            dict.fromkeys(f"IEC61508-7:{reference}" for reference in reference_values)
        ),
        recommendations=recommendations,
        context_references=context_references,
    )
    technique_id = f"{record.id.value}:concept:{technique_column}"
    concepts: list[KnowledgeConcept] = [
        KnowledgeConcept(
            id=technique_id,
            kind=KnowledgeConceptKind.TECHNIQUE_OR_MEASURE,
            label=technique,
            source_column_index=technique_column,
            source_header=_column_header(table, technique_column) or None,
        )
    ]
    relations: list[KnowledgeRelation] = []
    for recommendation in recommendations:
        sil_id = f"{record.id.value}:concept:{recommendation.source_column_index}"
        concepts.append(
            KnowledgeConcept(
                id=sil_id,
                kind=KnowledgeConceptKind.INTEGRITY_LEVEL,
                label=recommendation.integrity_level,
                source_column_index=recommendation.source_column_index,
                source_header=_column_header(table, recommendation.source_column_index) or None,
            )
        )
        relations.append(
            KnowledgeRelation(
                kind=KnowledgeRelationKind.RECOMMENDED_FOR,
                source_concept_id=technique_id,
                target_concept_id=sil_id,
                qualifier=recommendation.level.value,
            )
        )
    return record.model_copy(
        update={
            "technique_recommendation": technique_recommendation,
            "structured_knowledge": StructuredKnowledgeRecord(
                concepts=tuple(concepts), relations=tuple(relations)
            ),
        }
    )


def _portable_schema(
    table: NormalizedTable,
) -> tuple[KnowledgeTableKind, tuple[int, int] | None]:
    headers = tuple(_column_header(table, column.index).casefold() for column in table.columns)
    if len(headers) < 2:
        return KnowledgeTableKind.GENERIC, None
    for kind, signal_groups in _PORTABLE_SCHEMAS:
        columns = tuple(_find_signal_column(headers, signals) for signals in signal_groups)
        if any(column is None for column in columns) or len(set(columns)) != len(columns):
            continue
        return kind, (int(columns[0]), int(columns[1]))
    return KnowledgeTableKind.GENERIC, None


def _find_signal_column(headers: tuple[str, ...], signals: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(signal in header for signal in signals):
            return index
    return None


def _with_portable_knowledge(
    record: KnowledgeRecord,
    *,
    table: NormalizedTable,
    grid: dict[tuple[int, int], NormalizedTableCell],
    kind: KnowledgeTableKind,
    source_column: int,
    target_column: int,
) -> KnowledgeRecord:
    if record.is_header or table.rows[record.row_index].kind is not NormalizedTableRowKind.DATA:
        return record
    values = _row_values(table, grid, record.row_index)
    source_label = values.get(source_column, "")
    target_label = values.get(target_column, "")
    if not source_label or not target_label:
        return record
    source_kind, target_kind, relation_kind = _portable_semantics(kind)
    source_id = f"{record.id.value}:concept:{source_column}"
    target_id = f"{record.id.value}:concept:{target_column}"
    semantic = StructuredKnowledgeRecord(
        concepts=(
            KnowledgeConcept(
                id=source_id,
                kind=source_kind,
                label=source_label,
                source_column_index=source_column,
                source_header=_column_header(table, source_column) or None,
            ),
            KnowledgeConcept(
                id=target_id,
                kind=target_kind,
                label=target_label,
                source_column_index=target_column,
                source_header=_column_header(table, target_column) or None,
            ),
        ),
        relations=(
            KnowledgeRelation(
                kind=relation_kind,
                source_concept_id=source_id,
                target_concept_id=target_id,
            ),
        ),
    )
    return record.model_copy(update={"structured_knowledge": semantic})


def _portable_semantics(
    kind: KnowledgeTableKind,
) -> tuple[KnowledgeConceptKind, KnowledgeConceptKind, KnowledgeRelationKind]:
    mapping = {
        KnowledgeTableKind.RESPONSIBILITY_MATRIX: (
            KnowledgeConceptKind.ROLE,
            KnowledgeConceptKind.SUBJECT,
            KnowledgeRelationKind.RESPONSIBLE_FOR,
        ),
        KnowledgeTableKind.TRACEABILITY_MATRIX: (
            KnowledgeConceptKind.SOURCE,
            KnowledgeConceptKind.TARGET,
            KnowledgeRelationKind.TRACES_TO,
        ),
        KnowledgeTableKind.WORK_PRODUCT_MATRIX: (
            KnowledgeConceptKind.ACTIVITY,
            KnowledgeConceptKind.WORK_PRODUCT,
            KnowledgeRelationKind.PRODUCES,
        ),
        KnowledgeTableKind.VERIFICATION_CRITERIA_MATRIX: (
            KnowledgeConceptKind.SUBJECT,
            KnowledgeConceptKind.CRITERION,
            KnowledgeRelationKind.VERIFIED_BY,
        ),
        KnowledgeTableKind.APPLICABILITY_MATRIX: (
            KnowledgeConceptKind.SUBJECT,
            KnowledgeConceptKind.CONTEXT,
            KnowledgeRelationKind.APPLICABLE_TO,
        ),
    }
    return mapping[kind]


def _context_references(document_key: str, title: str | None) -> tuple[str, ...]:
    if not title:
        return ()
    return tuple(
        dict.fromkeys(
            f"{document_key}:{match.group(1)}" for match in _CONTEXT_REFERENCE.finditer(title)
        )
    )


def _normalize_marker(value: str) -> str:
    return " ".join(value.upper().split()).replace("–", "—")


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _stable_table_id(document_key: str, clause_id: str, table_block_id: str) -> str:
    identity = f"{document_key}\x1f{clause_id}\x1f{table_block_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"knowledge-table:{digest}"


def _ordinal_from_reference(reference: str) -> int:
    match = re.search(r":table:(\d+)$", reference)
    return int(match.group(1)) if match else 1


def _knowledge_table_reference(table: NormalizedTable) -> str:
    if table.title and (match := _TABLE_REFERENCE.search(table.title)):
        return f"Table {match.group(1)}"
    return table.reference
