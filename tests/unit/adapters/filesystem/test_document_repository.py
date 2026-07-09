from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


def test_file_system_repository_saves_and_loads_document(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")

    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Example Document",
        document_type=DocumentType.OTHER,
        year=2025,
    )

    repository.save(document)

    loaded = repository.load(DocumentKey(value="DOC"))

    assert loaded == document


def test_file_system_repository_reports_existing_document(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")

    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Example Document",
        document_type=DocumentType.OTHER,
    )

    assert repository.exists(DocumentKey(value="DOC")) is False

    repository.save(document)

    assert repository.exists(DocumentKey(value="DOC")) is True
