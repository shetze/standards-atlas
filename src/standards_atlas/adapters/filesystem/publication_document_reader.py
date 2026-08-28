"""Resolve publication views without polluting the canonical document repository."""

from __future__ import annotations

from standards_atlas.adapters.filesystem.composed_document_view_repository import (
    FileSystemComposedDocumentViewRepository,
)
from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.domain.model import DocumentKey, EngineeringDocument


class FileSystemPublicationDocumentReader:
    """Prefer a composed publication view, otherwise load a canonical document."""

    def __init__(
        self,
        documents: FileSystemEngineeringDocumentRepository,
        views: FileSystemComposedDocumentViewRepository,
    ) -> None:
        self._documents = documents
        self._views = views

    def load(self, key: DocumentKey) -> EngineeringDocument:
        if self._views.exists(key.value):
            return self._views.load(key.value).document
        return self._documents.load(key)

    def list(self) -> tuple[EngineeringDocument, ...]:
        return self._documents.list_readable()
