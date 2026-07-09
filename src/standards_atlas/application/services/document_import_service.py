"""Application service for importing engineering documents."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.ports import EngineeringDocumentImporter
from standards_atlas.application.repositories import EngineeringDocumentRepository
from standards_atlas.domain.model import EngineeringDocument


class DocumentImportService:
    """Application service for importing engineering documents."""

    def __init__(
        self,
        importer: EngineeringDocumentImporter,
        repository: EngineeringDocumentRepository | None = None,
    ) -> None:
        self._importer = importer
        self._repository = repository

    def import_document(self, source: Path) -> EngineeringDocument:
        """Import a document from an external source."""
        document = self._importer.import_document(source)

        if self._repository is not None:
            self._repository.save(document)

        return document
