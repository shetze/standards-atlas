"""Application service orchestrating source conversion and extraction reading."""

from pathlib import Path

from standards_atlas.application.model import ExtractedDocument
from standards_atlas.application.ports.document_converter import DocumentConverter
from standards_atlas.application.ports.extracted_document_reader import ExtractedDocumentReader


class DocumentExtractionService:
    """Convert a source document and expose its adapter-neutral observations."""

    def __init__(
        self,
        converter: DocumentConverter,
        reader: ExtractedDocumentReader,
    ) -> None:
        self._converter = converter
        self._reader = reader

    def convert(
        self,
        source: Path,
        target: Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Convert a source file into an adapter-native persisted document."""
        return self._converter.convert(source, target, overwrite=overwrite)

    def read(self, source: Path) -> ExtractedDocument:
        """Read a persisted extraction without reconverting the source PDF."""
        return self._reader.read(source)

    def convert_and_read(
        self,
        source: Path,
        target: Path,
        *,
        overwrite: bool = False,
    ) -> ExtractedDocument:
        """Convert and immediately read the adapter-neutral result."""
        converted = self.convert(source, target, overwrite=overwrite)
        return self.read(converted)
