"""Read-only structured-knowledge repository backed by T2 normalized tables."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.filesystem.normalized_table_repository import (
    FileSystemNormalizedTableRepository,
)
from standards_atlas.application.services.structured_knowledge_mapping_service import (
    StructuredKnowledgeMappingService,
)
from standards_atlas.domain.model import DocumentKey
from standards_atlas.domain.model.knowledge_table import KnowledgeRecord, KnowledgeTable


class FileSystemKnowledgeTableRepository:
    """Expose deterministic T3 mappings without duplicating persisted table content."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalized = FileSystemNormalizedTableRepository(workspace)
        self._mapping = StructuredKnowledgeMappingService()

    def list_tables(self, document_keys: tuple[str, ...] = ()) -> tuple[KnowledgeTable, ...]:
        tables = self._mapping.map_tables(self._normalized.list_tables(document_keys))
        return tuple(
            sorted(
                tables,
                key=lambda item: (item.document_key, item.reference, item.id.value),
            )
        )

    def get_table(self, table_id: str) -> KnowledgeTable:
        for table in self.list_tables():
            if table.id.value == table_id:
                return table
        raise KeyError(f"Unknown knowledge table id: {table_id}")

    def list_records(
        self,
        table_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[KnowledgeRecord, ...]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        records = self.get_table(table_id).records
        end = None if limit is None else offset + limit
        return records[offset:end]

    def get_record(self, record_id: str) -> KnowledgeRecord:
        table_id = record_id.rsplit(":row:", maxsplit=1)[0]
        for record in self.get_table(table_id).records:
            if record.id.value == record_id:
                return record
        raise KeyError(f"Unknown knowledge record id: {record_id}")

    def tables_for_document(self, document_key: str) -> tuple[KnowledgeTable, ...]:
        if not self._documents.exists(DocumentKey(value=document_key)):
            raise KeyError(f"Unknown document key: {document_key}")
        return self.list_tables((document_key,))
