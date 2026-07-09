from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataReader
from standards_atlas.application.ports import EngineeringDocumentReader


def test_atlas_data_reader_implements_document_reader_protocol() -> None:
    reader: EngineeringDocumentReader = AtlasDataReader()

    assert reader is not None


def test_atlas_data_reader_reads_engineering_document() -> None:
    reader = AtlasDataReader()

    document = reader.import_document(Path("data/EN50716"))

    assert document.title
    assert len(document.clauses) > 0

def test_atlas_data_reader_delegates_to_importer() -> None:
    class FakeImporter:
        def import_file(self, source: Path):
            from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument

            return EngineeringDocument(
                key=DocumentKey(value=source.name),
                title="Fake Document",
                document_type=DocumentType.OTHER,
            )

    reader = AtlasDataReader(importer=FakeImporter())

    document = reader.import_document(Path("fake"))

    assert document.title == "Fake Document"
