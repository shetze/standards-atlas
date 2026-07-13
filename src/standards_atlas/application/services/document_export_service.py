"""Application service for exporting engineering documents."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.application.ports import EngineeringDocumentExporter
from standards_atlas.domain.model import EngineeringDocument


class DocumentExportService:
    """Export an EngineeringDocument through an exporter port."""

    def __init__(
        self,
        exporter: EngineeringDocumentExporter,
    ) -> None:
        self._exporter = exporter

    def export_document(
        self,
        document: EngineeringDocument,
        target: Path,
    ) -> Path:
        """Export a document and return the generated target path."""
        return self._exporter.export_document(
            document=document,
            target=target,
        )
