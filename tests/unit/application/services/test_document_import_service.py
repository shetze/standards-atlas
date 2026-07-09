from pathlib import Path

from standards_atlas.application.services import DocumentImportService
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
)


class FakeImporter:
    def import_document(self, source: Path) -> EngineeringDocument:
        return EngineeringDocument(
            key=DocumentKey(value=source.name),
            title="Example",
            document_type=DocumentType.OTHER,
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved_document: EngineeringDocument | None = None

    def save(self, document: EngineeringDocument) -> None:
        self.saved_document = document

    def load(self, key: DocumentKey) -> EngineeringDocument:
        raise NotImplementedError

    def exists(self, key: DocumentKey) -> bool:
        return False


def test_document_import_service_saves_imported_document() -> None:
    repository = FakeRepository()

    service = DocumentImportService(
        importer=FakeImporter(),
        repository=repository,
    )

    document = service.import_document(Path("example"))

    assert repository.saved_document == document
