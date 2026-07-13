from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    Standard,
    StandardKey,
)


def test_repository_preserves_standard_subtype(
    tmp_path: Path,
) -> None:
    repository = FileSystemEngineeringDocumentRepository(
        workspace=tmp_path / ".atlas",
    )

    standard = Standard(
        key=StandardKey(value="EN50716"),
        title="EN 50716",
        name="EN 50716",
        document_type=DocumentType.STANDARD,
        year=2023,
        parent_key=StandardKey(value="IEC61508"),
    )

    repository.save(standard)

    loaded = repository.load(
        DocumentKey(value="EN50716"),
    )

    assert isinstance(loaded, Standard)
    assert loaded == standard
    assert loaded.parent_key == StandardKey(value="IEC61508")
