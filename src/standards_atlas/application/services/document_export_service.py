"""Application service for exporting engineering documents."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.model import PublicationDocument
from standards_atlas.application.ports import PublicationDocumentExporter


class DocumentExportService:
    """Export a publication document through an exporter port."""

    def __init__(
        self,
        exporter: PublicationDocumentExporter,
    ) -> None:
        self._exporter = exporter

    def export_document(
        self,
        document: PublicationDocument,
        target: Path,
    ) -> Path:
        """Export a document and return the generated target path."""
        return self._exporter.export_document(
            document=document,
            target=target,
        )
