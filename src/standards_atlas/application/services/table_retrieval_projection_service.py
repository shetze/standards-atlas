"""Deterministic T4 retrieval projections for structured table knowledge."""

from __future__ import annotations

import hashlib

from standards_atlas.domain.model import (
    KnowledgeConcept,
    KnowledgeRecord,
    KnowledgeRelation,
    KnowledgeTable,
    RetrievalDocument,
    RetrievalDocumentKind,
    RetrievalProjection,
    RetrievalTokenizationProfile,
)

PROJECTION_VERSION = "1.0.0"
_PROFILE = RetrievalTokenizationProfile.STRUCTURED_TABLE_V1


class TableRetrievalProjectionService:
    """Project T3 knowledge tables into disposable table-specific retrieval documents."""

    def project_tables(self, tables: tuple[KnowledgeTable, ...]) -> tuple[RetrievalProjection, ...]:
        return tuple(self.project_table(table) for table in tables)

    def project_table(self, table: KnowledgeTable) -> RetrievalProjection:
        documents: list[RetrievalDocument] = [_table_document(table)]
        for record in table.records:
            if record.is_header:
                continue
            documents.append(_row_document(table, record))
            structured = record.structured_knowledge
            if structured is None:
                continue
            concepts = {concept.id: concept for concept in structured.concepts}
            documents.extend(
                _concept_document(table, record, concept) for concept in concepts.values()
            )
            documents.extend(
                _relation_document(table, record, relation, concepts)
                for relation in structured.relations
            )
        return RetrievalProjection(
            source_table_id=table.id.value,
            document_key=table.document_key,
            documents=tuple(documents),
            projection_version=PROJECTION_VERSION,
        )


def _table_document(table: KnowledgeTable) -> RetrievalDocument:
    header = [f"Table: {table.reference}"]
    if table.title:
        header.append(f"Title: {table.title}")
    header.append(f"Kind: {table.kind.value}")
    for row in table.header_rows:
        header.append("Headers: " + " | ".join(row))
    return _document(
        table,
        kind=RetrievalDocumentKind.TABLE,
        source_id=table.id.value,
        text="\n".join(header),
        metadata={"table_reference": table.reference, "table_kind": table.kind.value},
    )


def _row_document(table: KnowledgeTable, record: KnowledgeRecord) -> RetrievalDocument:
    parts = [f"Table: {table.reference}"]
    if table.title:
        parts.append(f"Title: {table.title}")
    parts.append(f"Row: {record.row_index + 1}")
    for cell in sorted(record.cells, key=lambda item: item.column_index):
        header = _header_label(table, cell.column_index)
        parts.append(f"{header}: {cell.text}" if header else cell.text)
    return _document(
        table,
        kind=RetrievalDocumentKind.ROW,
        source_id=record.id.value,
        text="\n".join(parts),
        metadata={"table_reference": table.reference, "row_index": str(record.row_index)},
    )


def _concept_document(
    table: KnowledgeTable,
    record: KnowledgeRecord,
    concept: KnowledgeConcept,
) -> RetrievalDocument:
    text = "\n".join(
        (
            f"Table: {table.reference}",
            f"Concept: {concept.label}",
            f"Concept kind: {concept.kind.value}",
            f"Source header: {concept.source_header or ''}",
        )
    )
    return _document(
        table,
        kind=RetrievalDocumentKind.CONCEPT,
        source_id=f"{record.id.value}:concept:{concept.id}",
        text=text,
        metadata={
            "record_id": record.id.value,
            "concept_id": concept.id,
            "concept_kind": concept.kind.value,
        },
    )


def _relation_document(
    table: KnowledgeTable,
    record: KnowledgeRecord,
    relation: KnowledgeRelation,
    concepts: dict[str, KnowledgeConcept],
) -> RetrievalDocument:
    source = concepts[relation.source_concept_id]
    target = concepts[relation.target_concept_id]
    parts = [
        f"Table: {table.reference}",
        f"Relation: {source.label} {relation.kind.value} {target.label}",
    ]
    if relation.qualifier:
        parts.append(f"Qualifier: {relation.qualifier}")
    source_id = f"{record.id.value}:relation:{_digest(relation)}"
    return _document(
        table,
        kind=RetrievalDocumentKind.RELATION,
        source_id=source_id,
        text="\n".join(parts),
        metadata={
            "record_id": record.id.value,
            "relation_kind": relation.kind.value,
            "source_concept_id": source.id,
            "target_concept_id": target.id,
        },
    )


def _header_label(table: KnowledgeTable, column_index: int) -> str:
    labels = [
        row[column_index]
        for row in table.header_rows
        if column_index < len(row) and row[column_index]
    ]
    return " / ".join(dict.fromkeys(labels))


def _document(
    table: KnowledgeTable,
    *,
    kind: RetrievalDocumentKind,
    source_id: str,
    text: str,
    metadata: dict[str, str],
) -> RetrievalDocument:
    return RetrievalDocument(
        id=f"retrieval:{_digest((table.id.value, kind.value, source_id, PROJECTION_VERSION))}",
        kind=kind,
        document_key=table.document_key,
        source_id=source_id,
        text=text,
        tokenization_profile=_PROFILE,
        metadata=metadata,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:16]
