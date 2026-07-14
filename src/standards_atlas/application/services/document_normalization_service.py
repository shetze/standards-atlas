"""Application service orchestrating extracted document normalization."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.docling import DoclingArtifactRepository, DoclingJsonReader
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizedExtractedDocument,
)
from standards_atlas.application.normalization import DocumentNormalizer


class DocumentNormalizationService:
    """Load, normalize, and persist an extracted document."""

    def __init__(
        self,
        *,
        workspace: Path = Path(".atlas"),
        reader: DoclingJsonReader | None = None,
        normalizer: DocumentNormalizer | None = None,
    ) -> None:
        self._docling_repository = DoclingArtifactRepository(workspace)
        self._normalization_repository = NormalizationArtifactRepository(workspace)
        self._reader = reader or DoclingJsonReader()
        self._normalizer = normalizer or DocumentNormalizer()

    def normalize(
        self,
        document_key: str,
        *,
        options: NormalizationOptions | None = None,
    ) -> NormalizedExtractedDocument:
        extracted = self._reader.read(self._docling_repository.document_path(document_key))
        result = self._normalizer.normalize(extracted, options)
        self._normalization_repository.save(document_key, result)
        return result

    def load(self, document_key: str) -> NormalizedExtractedDocument:
        return self._normalization_repository.load(document_key)
