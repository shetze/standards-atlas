"""Adapter composing native Docling persistence, JSON decoding, and formula visuals."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.docling.document_reader import DoclingJsonReader
from standards_atlas.adapters.docling.repository import DoclingArtifactRepository
from standards_atlas.application.model import ExtractedDocument
from standards_atlas.application.ports import FormulaVisualEnricher


class DoclingExtractedDocumentRepository:
    """Load adapter-neutral extracted documents by document key.

    Visual-only formulas are enriched from the original PDF when conversion metadata
    still points to an accessible source file. Formula discovery remains Docling's
    responsibility; the PDF adapter only renders already identified regions.
    """

    def __init__(
        self,
        artifacts: DoclingArtifactRepository,
        reader: DoclingJsonReader | None = None,
        formula_visuals: FormulaVisualEnricher | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._reader = reader or DoclingJsonReader()
        self._formula_visuals = formula_visuals

    def load(self, document_key: str) -> ExtractedDocument:
        document = self._reader.read(self._artifacts.document_path(document_key))
        if self._formula_visuals is None:
            return document
        source_pdf = self._source_pdf(document_key)
        if source_pdf is None:
            return document
        return self._formula_visuals.enrich(document, source_pdf)

    def _source_pdf(self, document_key: str) -> Path | None:
        try:
            metadata = self._artifacts.load_metadata(document_key)
        except (OSError, ValueError):
            return None
        source_path = metadata.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            return None
        source = Path(source_path).expanduser()
        return source if source.is_file() and source.suffix.lower() == ".pdf" else None
