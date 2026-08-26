from pathlib import Path

from standards_atlas.adapters.filesystem import (
    FileSystemComposedDocumentViewRepository,
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentReader,
)
from standards_atlas.application.model import ComposedDocumentView
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


def _document(key: str) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.OTHER,
    )


def test_publication_reader_prefers_work_view_without_canonical_family_file(
    tmp_path: Path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path / "data")
    documents.save(_document("PART-1"))
    views = FileSystemComposedDocumentViewRepository(tmp_path / "work")
    views.save(
        ComposedDocumentView(
            family_key="FAMILY",
            part_keys=("PART-1",),
            document=_document("FAMILY"),
        )
    )

    reader = FileSystemPublicationDocumentReader(documents, views)

    assert reader.load(DocumentKey(value="FAMILY")).key.value == "FAMILY"
    assert [document.key.value for document in reader.list()] == ["PART-1"]
    assert not documents.exists(DocumentKey(value="FAMILY"))
