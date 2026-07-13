from pathlib import Path

import pytest

from standards_atlas.adapters.docling import (
    DoclingArtifactRepository,
    ExtractionState,
    sha256_file,
)


def test_repository_places_native_artifacts_below_private_workspace(tmp_path: Path) -> None:
    repository = DoclingArtifactRepository(tmp_path / ".atlas")

    assert (
        repository.document_path("EN 50716")
        == (tmp_path / ".atlas" / "docling" / "EN_50716" / "document.json").resolve()
    )
    assert (
        repository.metadata_path("EN 50716")
        == (tmp_path / ".atlas" / "docling" / "EN_50716" / "conversion.json").resolve()
    )


@pytest.mark.parametrize("document_key", ["", ".", "..", "../public", "/tmp/public", "a/b"])
def test_repository_rejects_unsafe_document_keys(
    tmp_path: Path,
    document_key: str,
) -> None:
    repository = DoclingArtifactRepository(tmp_path / ".atlas")

    with pytest.raises(ValueError):
        repository.document_path(document_key)


def test_repository_roundtrips_conversion_metadata(tmp_path: Path) -> None:
    repository = DoclingArtifactRepository(tmp_path / ".atlas")
    metadata = {"schema_version": 1, "converter": "docling", "source_sha256": "abc"}

    path = repository.save_metadata("STD", metadata)

    assert path.exists()
    assert repository.load_metadata("STD") == metadata


def test_repository_detects_current_and_stale_extractions(tmp_path: Path) -> None:
    repository = DoclingArtifactRepository(tmp_path / ".atlas")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"first version")
    document = repository.document_path("STD")
    document.parent.mkdir(parents=True)
    document.write_text("{}", encoding="utf-8")
    repository.save_metadata("STD", {"source_sha256": sha256_file(source)})

    assert repository.extraction_state("STD", source) is ExtractionState.CURRENT
    assert repository.is_current("STD", source) is True

    source.write_bytes(b"second version")

    assert repository.extraction_state("STD", source) is ExtractionState.STALE
    assert repository.is_current("STD", source) is False


def test_repository_detects_incomplete_extraction(tmp_path: Path) -> None:
    repository = DoclingArtifactRepository(tmp_path / ".atlas")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"PDF")
    repository.document_path("STD").parent.mkdir(parents=True)
    repository.document_path("STD").write_text("{}", encoding="utf-8")

    assert repository.extraction_state("STD", source) is ExtractionState.INCOMPLETE


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"private standard content")

    assert sha256_file(source) == sha256_file(source)
    assert len(sha256_file(source)) == 64
