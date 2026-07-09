from standards_atlas.application.services import DocumentTransformationService
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


class RenameDocumentTransformation:
    def __init__(self, title: str) -> None:
        self._title = title

    def transform(self, document: EngineeringDocument) -> EngineeringDocument:
        return document.model_copy(update={"title": self._title})


def test_document_transformation_service_applies_transformations_in_order() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Original",
        document_type=DocumentType.OTHER,
    )

    service = DocumentTransformationService(
        transformations=[
            RenameDocumentTransformation("First"),
            RenameDocumentTransformation("Second"),
        ]
    )

    transformed = service.transform(document)

    assert transformed.title == "Second"
