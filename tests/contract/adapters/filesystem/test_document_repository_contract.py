from pathlib import Path

import pytest

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument

pytestmark = pytest.mark.contract


def _document(key: str = "DOC") -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title="Repository contract document",
        document_type=DocumentType.OTHER,
        year=2026,
    )


def test_repository_roundtrip_preserves_the_canonical_document(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")
    document = _document()

    repository.save(document)

    assert repository.load(document.key) == document


def test_repository_save_replaces_the_same_document_identity(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")
    original = _document()
    replacement = original.model_copy(update={"title": "Updated title"})

    repository.save(original)
    repository.save(replacement)

    assert repository.load(original.key) == replacement


def test_repository_exists_reflects_persisted_state(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")
    document = _document()

    assert not repository.exists(document.key)
    repository.save(document)
    assert repository.exists(document.key)


def test_repository_load_of_unknown_identity_is_explicit(tmp_path: Path) -> None:
    repository = FileSystemEngineeringDocumentRepository(workspace=tmp_path / ".atlas")

    with pytest.raises(FileNotFoundError, match="UNKNOWN"):
        repository.load(DocumentKey(value="UNKNOWN"))
