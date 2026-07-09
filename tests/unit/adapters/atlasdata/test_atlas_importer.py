from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.application.ports import EngineeringDocumentImporter
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


def test_atlas_data_importer_implements_document_importer_protocol() -> None:
    importer: EngineeringDocumentImporter = AtlasDataImporter()

    assert importer is not None


def test_atlas_data_importer_imports_engineering_document() -> None:
    importer = AtlasDataImporter()

    document = importer.import_document(Path("data/EN50716"))

    assert isinstance(document, EngineeringDocument)
    assert document.title
    assert len(document.clauses) > 0


def test_atlas_data_importer_delegates_to_pipeline() -> None:
    class FakePipeline:
        def import_file(self, source: Path) -> EngineeringDocument:
            return EngineeringDocument(
                key=DocumentKey(value=source.name),
                title="Fake Document",
                document_type=DocumentType.OTHER,
            )

    importer = AtlasDataImporter(pipeline=FakePipeline())

    document = importer.import_document(Path("fake"))

    assert document.title == "Fake Document"
    assert document.key.value == "fake"
