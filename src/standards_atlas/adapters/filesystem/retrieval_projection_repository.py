"""Read-only T4 table retrieval projections derived from T3 structured knowledge."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.filesystem.knowledge_table_repository import (
    FileSystemKnowledgeTableRepository,
)
from standards_atlas.application.services.table_retrieval_projection_service import (
    TableRetrievalProjectionService,
)
from standards_atlas.domain.model import RetrievalProjection


class FileSystemTableRetrievalProjectionRepository:
    """Expose reproducible retrieval projections without owning an index or embedding store."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._knowledge = FileSystemKnowledgeTableRepository(workspace)
        self._projector = TableRetrievalProjectionService()

    def list_projections(
        self, document_keys: tuple[str, ...] = ()
    ) -> tuple[RetrievalProjection, ...]:
        tables = self._knowledge.list_tables(document_keys)
        return self._projector.project_tables(tables)

    def get_projection(self, table_id: str) -> RetrievalProjection:
        return self._projector.project_table(self._knowledge.get_table(table_id))
