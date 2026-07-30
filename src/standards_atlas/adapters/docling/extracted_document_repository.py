"""Adapter composing native Docling persistence and JSON decoding."""

from standards_atlas.adapters.docling.document_reader import DoclingJsonReader
from standards_atlas.adapters.docling.repository import DoclingArtifactRepository
from standards_atlas.application.model import ExtractedDocument


class DoclingExtractedDocumentRepository:
    """Load adapter-neutral extracted documents by document key."""

    def __init__(
        self,
        artifacts: DoclingArtifactRepository,
        reader: DoclingJsonReader | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._reader = reader or DoclingJsonReader()

    def load(self, document_key: str) -> ExtractedDocument:
        return self._reader.read(self._artifacts.document_path(document_key))
