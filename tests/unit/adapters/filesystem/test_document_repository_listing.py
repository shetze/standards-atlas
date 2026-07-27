from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


def test_lists_documents_by_original_key(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="zeta:2024"),
            title="Zeta",
            document_type=DocumentType.OTHER,
        )
    )
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="alpha/value"),
            title="Alpha",
            document_type=DocumentType.OTHER,
        )
    )

    assert [document.key.value for document in repository.list()] == [
        "alpha/value",
        "zeta:2024",
    ]
