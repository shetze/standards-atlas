"""Consumer-oriented document persistence ports."""

from typing import Protocol

from standards_atlas.application.model import ExtractedDocument
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.domain.model import DocumentKey, EngineeringDocument


class ExtractedDocumentRepository(Protocol):
    """Load an extracted document by its stable document key."""

    def load(self, document_key: str) -> ExtractedDocument: ...


class NormalizedDocumentRepository(Protocol):
    """Persist and load normalized extraction results."""

    def save(self, document_key: str, document: NormalizedExtractedDocument) -> object: ...

    def load(self, document_key: str) -> NormalizedExtractedDocument: ...


class EngineeringDocumentReader(Protocol):
    """Load canonical engineering documents for read-only use cases."""

    def load(self, key: DocumentKey) -> EngineeringDocument: ...
