from standards_atlas.application.model import ExtractedDocument, ExtractionMetadata
from standards_atlas.application.model.normalized_document import NormalizedExtractedDocument
from standards_atlas.application.services import DocumentNormalizationService


class ExtractedDocuments:
    def __init__(self, document: ExtractedDocument) -> None:
        self.document = document
        self.loaded: list[str] = []

    def load(self, document_key: str) -> ExtractedDocument:
        self.loaded.append(document_key)
        return self.document


class NormalizedDocuments:
    def __init__(self) -> None:
        self.saved: list[tuple[str, NormalizedExtractedDocument]] = []

    def save(self, document_key: str, document: NormalizedExtractedDocument) -> None:
        self.saved.append((document_key, document))

    def load(self, document_key: str) -> NormalizedExtractedDocument:
        for key, document in self.saved:
            if key == document_key:
                return document
        raise KeyError(document_key)


def test_normalization_service_uses_injected_repositories() -> None:
    source = ExtractedDocument(
        source_id="DOC",
        items=(),
        metadata=ExtractionMetadata(converter="test"),
    )
    extracted = ExtractedDocuments(source)
    normalized = NormalizedDocuments()
    service = DocumentNormalizationService(
        extracted_documents=extracted,
        normalized_documents=normalized,
    )

    result = service.normalize("DOC")

    assert extracted.loaded == ["DOC"]
    assert normalized.saved == [("DOC", result)]
    assert service.load("DOC") == result
