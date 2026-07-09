from pathlib import Path

from standards_atlas.application.services import DocumentImportService
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
)


class FakeReader:

    def import_document(
        self,
        source: Path,
    ) -> EngineeringDocument:

        return EngineeringDocument(
            key=DocumentKey(value=source.name),
            title="Example",
            document_type=DocumentType.OTHER,
        )


def test_document_import_service_returns_document() -> None:

    service = DocumentImportService(FakeReader())

    document = service.import_document(Path("example"))

    assert document.title == "Example"
