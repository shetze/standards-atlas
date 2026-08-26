"""Compatibility facade for T2 normalization and T3 structured knowledge mapping."""

from __future__ import annotations

from standards_atlas.application.services.structured_knowledge_mapping_service import (
    StructuredKnowledgeMappingService,
)
from standards_atlas.application.services.table_normalization_service import (
    TableNormalizationService,
)
from standards_atlas.domain.model import Clause, EngineeringDocument, KnowledgeTable


class KnowledgeTableProjectionService:
    """Expose historical knowledge-table APIs through the canonical T2 -> T3 path."""

    def __init__(self) -> None:
        self._normalizer = TableNormalizationService()
        self._mapper = StructuredKnowledgeMappingService()

    def project_document(self, document: EngineeringDocument) -> tuple[KnowledgeTable, ...]:
        return self._mapper.map_tables(self._normalizer.normalize_document(document))

    def project_clause(
        self,
        document: EngineeringDocument,
        clause: Clause,
    ) -> tuple[KnowledgeTable, ...]:
        clause_id = clause.id.value
        return tuple(
            table
            for table in self.project_document(document)
            if table.parent_clause_id == clause_id
        )
