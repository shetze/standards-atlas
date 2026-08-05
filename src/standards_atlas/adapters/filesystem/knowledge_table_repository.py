"""Read-only knowledge-table repository backed by engineering documents."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.services.knowledge_table_service import (
    KnowledgeTableProjectionService,
)
from standards_atlas.domain.model import DocumentKey
from standards_atlas.domain.model.knowledge_table import KnowledgeRecord, KnowledgeTable


class FileSystemKnowledgeTableRepository:
    """Expose deterministic table projections without duplicating persisted content."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._projection = KnowledgeTableProjectionService()

    def list_tables(self, document_keys: tuple[str, ...] = ()) -> tuple[KnowledgeTable, ...]:
        allowed = set(document_keys)
        tables = (
            table
            for document in self._documents.list()
            if not allowed or document.key.value in allowed
            for table in self._projection.project_document(document)
        )
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
