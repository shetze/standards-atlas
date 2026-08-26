"""Read-only repository for deterministic normalized-table projections."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.services.table_normalization_service import (
    TableNormalizationService,
)
from standards_atlas.domain.model import NormalizedTable


class FileSystemNormalizedTableRepository:
    """Expose T2 normalized tables without duplicating persisted source content."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalizer = TableNormalizationService()

    def list_tables(self, document_keys: tuple[str, ...] = ()) -> tuple[NormalizedTable, ...]:
        allowed = set(document_keys)
        tables = (
            table
            for document in self._documents.list()
            if not allowed or document.key.value in allowed
            for table in self._normalizer.normalize_document(document)
        )
        return tuple(sorted(tables, key=lambda item: (item.document_key, item.reference, item.id)))

    def get_table(self, table_id: str) -> NormalizedTable:
        for table in self.list_tables():
            if table.id == table_id:
                return table
        raise KeyError(f"Unknown normalized table id: {table_id}")
