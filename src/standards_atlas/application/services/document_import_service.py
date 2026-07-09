"""Application service for importing engineering documents."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.ports import EngineeringDocumentReader
from standards_atlas.domain.model import EngineeringDocument


class DocumentImportService:
    """Application service for importing engineering documents.

    The service coordinates the document import use case while remaining
    independent of concrete adapter implementations.
    """

    def __init__(
        self,
        reader: EngineeringDocumentReader,
    ) -> None:
        self._reader = reader

    def import_document(
        self,
        source: Path,
    ) -> EngineeringDocument:
        """Import a document from an external source."""

        return self._reader.import_document(source)
