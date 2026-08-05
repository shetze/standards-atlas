"""Projection service for addressable knowledge tables and records."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from standards_atlas.domain.model import Clause, EngineeringDocument, NoteBlock, TableBlock
from standards_atlas.domain.model.knowledge_table import (
    IntegrityLevelRecommendation,
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
    RecommendationLevel,
    StructuredKnowledgeRecord,
    TechniqueRecommendation,
)

_CONTEXT_REFERENCE = re.compile(r"\bsee\s+((?:\d+\.)*\d+)\b", re.IGNORECASE)
_DESCRIPTION_REFERENCE = re.compile(r"\b([A-Z]\.\d+(?:\.\d+)*)\b")
_LOCAL_IDENTIFIER = re.compile(r"^\s*(\d+)([a-z])?\s*$", re.IGNORECASE)
_SIL_HEADER = re.compile(r"\bSIL\s*([1-4])\b", re.IGNORECASE)
_RECOMMENDATION_LEVELS = {
    "HR": RecommendationLevel.HIGHLY_RECOMMENDED,
    "R": RecommendationLevel.RECOMMENDED,
    "—": RecommendationLevel.NEUTRAL,
    "-": RecommendationLevel.NEUTRAL,
    "NR": RecommendationLevel.NOT_RECOMMENDED,
}

_TABLE_REFERENCE = re.compile(r"\b(?:Table|Tabelle)\s+([A-Z0-9]+(?:[.-][A-Z0-9]+)*)", re.IGNORECASE)


class KnowledgeTableProjectionService:
    """Create deterministic knowledge artifacts from canonical table blocks."""

    def project_document(self, document: EngineeringDocument) -> tuple[KnowledgeTable, ...]:
        tables: list[KnowledgeTable] = []
        for clause in document.clauses:
            tables.extend(self.project_clause(document, clause))
        return tuple(tables)

    def project_clause(
        self,
        document: EngineeringDocument,
        clause: Clause,
    ) -> tuple[KnowledgeTable, ...]:
        projected: list[KnowledgeTable] = []
        for ordinal, table in enumerate(_iter_tables(clause.content), start=1):
            projected.append(self._project_table(document, clause, table, ordinal))
        return tuple(projected)

    def _project_table(
        self,
        document: EngineeringDocument,
        clause: Clause,
        table: TableBlock,
        ordinal: int,
    ) -> KnowledgeTable:
        table_id = KnowledgeTableId(
            value=_stable_table_id(document.key.value, clause.id.value, table.id)
        )
        records = tuple(
            KnowledgeRecord(
                id=KnowledgeRecordId(value=f"{table_id.value}:row:{row_index + 1}"),
                table_id=table_id,
                document_key=document.key.value,
                parent_clause_id=clause.id.value,
                parent_clause_reference=clause.reference.as_text(),
                row_index=row_index,
                cells=tuple(
                    KnowledgeCell(
                        column_index=column_index,
                        text=cell.text,
                        row_span=cell.row_span,
                        column_span=cell.column_span,
                        is_header=cell.is_header,
                    )
                    for column_index, cell in enumerate(row.cells)
                ),
                is_header=bool(row.cells) and all(cell.is_header for cell in row.cells),
                source=KnowledgeRecordSource(
                    table_block_id=table.id,
                    row_index=row_index,
                    source_evidence=table.source_evidence,
                ),
            )
            for row_index, row in enumerate(table.rows)
        )
        header_rows = tuple(
            tuple(cell.text for cell in row.cells)
            for row in table.rows
            if row.cells and all(cell.is_header for cell in row.cells)
        )
        reference = _table_reference(table.caption, clause.reference.clause, ordinal)
        kind, context_references, records = _interpret_iec61508_recommendation_table(
            document_key=document.key.value,
            caption=table.caption,
            header_rows=header_rows,
            records=records,
        )
        if kind is KnowledgeTableKind.GENERIC:
            kind, records = _interpret_portable_table_ontology(
                header_rows=header_rows,
                records=records,
            )
        return KnowledgeTable(
            id=table_id,
            document_key=document.key.value,
            parent_clause_id=clause.id.value,
            parent_clause_reference=clause.reference.as_text(),
            reference=reference,
            title=table.caption,
            table_block_id=table.id,
            ordinal_in_clause=ordinal,
            header_rows=header_rows,
            records=records,
            source_evidence=table.source_evidence,
            kind=kind,
            context_references=context_references,
        )


def _interpret_iec61508_recommendation_table(
    *,
    document_key: str,
    caption: str | None,
    header_rows: tuple[tuple[str, ...], ...],
    records: tuple[KnowledgeRecord, ...],
) -> tuple[KnowledgeTableKind, tuple[str, ...], tuple[KnowledgeRecord, ...]]:
    """Interpret IEC 61508-3 Annex A recommendation matrices conservatively."""
    if not document_key.upper().replace(" ", "").startswith("IEC61508-3"):
        return KnowledgeTableKind.GENERIC, (), records

    headers = _effective_headers(header_rows, records)
    sil_columns = {
        index: f"SIL {match.group(1)}"
        for index, header in enumerate(headers)
        if (match := _SIL_HEADER.search(header))
    }
    signal = " ".join((*headers, caption or "")).casefold()
    if len(sil_columns) < 2 or not any(
        word in signal for word in ("technique", "method", "measure")
    ):
        return KnowledgeTableKind.GENERIC, (), records

    context_references = _context_references(document_key, caption)
    interpreted: list[KnowledgeRecord] = []
    for record in records:
        if record.is_header:
            interpreted.append(record)
            continue
        semantic = _interpret_recommendation_record(
            record,
            headers=headers,
            sil_columns=sil_columns,
            context_references=context_references,
        )
        interpreted.append(record.model_copy(update={"technique_recommendation": semantic}))
    return (
        KnowledgeTableKind.TECHNIQUE_RECOMMENDATION_MATRIX,
        context_references,
        tuple(interpreted),
    )


def _effective_headers(
    header_rows: tuple[tuple[str, ...], ...],
    records: tuple[KnowledgeRecord, ...],
) -> tuple[str, ...]:
    if header_rows:
        width = max(len(row) for row in header_rows)
        return tuple(
            " ".join(row[index] for row in header_rows if index < len(row)).strip()
            for index in range(width)
        )
    for record in records:
        values = tuple(cell.text for cell in record.cells)
        if sum(bool(_SIL_HEADER.search(value)) for value in values) >= 2:
            return values
    return ()


def _interpret_recommendation_record(
    record: KnowledgeRecord,
    *,
    headers: tuple[str, ...],
    sil_columns: dict[int, str],
    context_references: tuple[str, ...],
) -> TechniqueRecommendation | None:
    values = {cell.column_index: cell.text.strip() for cell in record.cells}
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
        return None

    non_sil = [(index, value) for index, value in values.items() if index not in sil_columns]
    local_identifier = None
    alternative_group = None
    if non_sil and (match := _LOCAL_IDENTIFIER.fullmatch(non_sil[0][1])):
        local_identifier = non_sil.pop(0)[1]
        alternative_group = match.group(1) if match.group(2) else None

    reference_values: list[str] = []
    technique_candidates: list[str] = []
    for index, value in non_sil:
        header = headers[index].casefold() if index < len(headers) else ""
        refs = _DESCRIPTION_REFERENCE.findall(value)
        reference_column = any(signal in header for signal in ("ref", "clause", "see", "61508-7"))
        if refs and (reference_column or len(refs) * 5 >= len(value)):
            reference_values.extend(refs)
        elif value and _normalize_marker(value) not in _RECOMMENDATION_LEVELS:
            technique_candidates.append(value)
    if not technique_candidates:
        return None
    technique = max(technique_candidates, key=len)
    return TechniqueRecommendation(
        local_identifier=local_identifier,
        alternative_group=alternative_group,
        technique=technique,
        description_references=tuple(
            dict.fromkeys(f"IEC61508-7:{reference}" for reference in reference_values)
        ),
        recommendations=recommendations,
        context_references=context_references,
    )


def _normalize_marker(value: str) -> str:
    return " ".join(value.upper().split()).replace("–", "—")


def _context_references(document_key: str, caption: str | None) -> tuple[str, ...]:
    if not caption:
        return ()
    return tuple(
        dict.fromkeys(
            f"{document_key}:{match.group(1)}" for match in _CONTEXT_REFERENCE.finditer(caption)
        )
    )


def _iter_tables(content: tuple[object, ...]) -> Iterable[TableBlock]:
    for block in content:
        if isinstance(block, TableBlock):
            yield block
        elif isinstance(block, NoteBlock):
            yield from _iter_tables(block.content)


def _stable_table_id(document_key: str, clause_id: str, table_block_id: str) -> str:
    identity = f"{document_key}\x1f{clause_id}\x1f{table_block_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"knowledge-table:{digest}"


def _table_reference(caption: str | None, clause_reference: str, ordinal: int) -> str:
    if caption and (match := _TABLE_REFERENCE.search(caption)):
        return f"Table {match.group(1)}"
    return f"{clause_reference}:table:{ordinal}"


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


def _interpret_portable_table_ontology(
    *,
    header_rows: tuple[tuple[str, ...], ...],
    records: tuple[KnowledgeRecord, ...],
) -> tuple[KnowledgeTableKind, tuple[KnowledgeRecord, ...]]:
    """Project common matrix shapes into a small domain-neutral ontology."""
    headers = _effective_headers(header_rows, records)
    if len(headers) < 2:
        return KnowledgeTableKind.GENERIC, records
    normalized = tuple(header.casefold().strip() for header in headers)
    for kind, signal_groups in _PORTABLE_SCHEMAS:
        columns = tuple(_find_signal_column(normalized, signals) for signals in signal_groups)
        if any(column is None for column in columns) or len(set(columns)) != len(columns):
            continue
        source_column, target_column = (int(column) for column in columns)
        interpreted = tuple(
            _with_structured_knowledge(
                record,
                headers=headers,
                kind=kind,
                source_column=source_column,
                target_column=target_column,
            )
            for record in records
        )
        return kind, interpreted
    return KnowledgeTableKind.GENERIC, records


def _find_signal_column(headers: tuple[str, ...], signals: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(signal in header for signal in signals):
            return index
    return None


def _with_structured_knowledge(
    record: KnowledgeRecord,
    *,
    headers: tuple[str, ...],
    kind: KnowledgeTableKind,
    source_column: int,
    target_column: int,
) -> KnowledgeRecord:
    if record.is_header:
        return record
    values = {cell.column_index: cell.text.strip() for cell in record.cells}
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
                source_header=headers[source_column] if source_column < len(headers) else None,
            ),
            KnowledgeConcept(
                id=target_id,
                kind=target_kind,
                label=target_label,
                source_column_index=target_column,
                source_header=headers[target_column] if target_column < len(headers) else None,
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
