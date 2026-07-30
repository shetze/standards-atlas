"""Application service orchestrating extracted document normalization."""

from __future__ import annotations

from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedExtractedDocument,
)
from standards_atlas.application.normalization import DocumentNormalizer
from standards_atlas.application.ports import (
    ExtractedDocumentRepository,
    NormalizedDocumentRepository,
)


class DocumentNormalizationService:
    """Load, normalize, and persist an extracted document through ports."""

    def __init__(
        self,
        *,
        extracted_documents: ExtractedDocumentRepository,
        normalized_documents: NormalizedDocumentRepository,
        normalizer: DocumentNormalizer | None = None,
    ) -> None:
        self._extracted_documents = extracted_documents
        self._normalized_documents = normalized_documents
        self._normalizer = normalizer or DocumentNormalizer()

    def normalize(
        self,
        document_key: str,
        *,
        options: NormalizationOptions | None = None,
    ) -> NormalizedExtractedDocument:
        extracted = self._extracted_documents.load(document_key)
        result = self._normalizer.normalize(extracted, options)
        self._normalized_documents.save(document_key, result)
        return result

    def load(self, document_key: str) -> NormalizedExtractedDocument:
        return self._normalized_documents.load(document_key)
