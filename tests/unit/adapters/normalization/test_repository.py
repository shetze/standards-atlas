from datetime import UTC, datetime
from pathlib import Path

import pytest

from standards_atlas.adapters.normalization import (
    NormalizationArtifactRepository,
    NormalizationState,
)
from standards_atlas.application.model import (
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
)


def normalized(source_hash: str = "abc") -> NormalizedExtractedDocument:
    return NormalizedExtractedDocument(
        source_id="sample",
        metadata=NormalizationMetadata(
            normalizer_version="0.5.0",
            source_extraction_hash=source_hash,
            created_at=datetime.now(UTC),
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(),
        ),
    )


def test_repository_roundtrip_and_current_state(tmp_path: Path) -> None:
    repository = NormalizationArtifactRepository(tmp_path / ".atlas")
    repository.save("sample", normalized())
    assert repository.load("sample").source_id == "sample"
    assert (
        repository.state(
            "sample",
            source_extraction_hash="abc",
            options=NormalizationOptions(),
            normalizer_version="0.5.0",
        )
        is NormalizationState.CURRENT
    )


def test_repository_detects_stale_document(tmp_path: Path) -> None:
    repository = NormalizationArtifactRepository(tmp_path / ".atlas")
    repository.save("sample", normalized())
    assert (
        repository.state(
            "sample",
            source_extraction_hash="changed",
            options=NormalizationOptions(),
            normalizer_version="0.5.0",
        )
        is NormalizationState.STALE
    )


@pytest.mark.parametrize("key", ["", "..", "../public", "/tmp/public", "a/b"])
def test_repository_rejects_unsafe_document_keys(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        NormalizationArtifactRepository(tmp_path / ".atlas").document_path(key)


def test_repository_writes_deterministic_document_and_separate_run_metadata(
    tmp_path: Path,
) -> None:
    repository = NormalizationArtifactRepository(tmp_path / ".atlas")
    artifact = normalized()

    repository.save("sample", artifact)
    first_document = repository.document_path("sample").read_bytes()
    first_run = repository.load_run("sample")
    repository.save("sample", artifact)
    second_document = repository.document_path("sample").read_bytes()
    second_run = repository.load_run("sample")

    assert first_document == second_document
    assert b"created_at" not in first_document
    assert first_run.document_content_hash == second_run.document_content_hash
    assert repository.run_path("sample").is_file()


def test_repository_detects_tampered_document_payload(tmp_path: Path) -> None:
    repository = NormalizationArtifactRepository(tmp_path / ".atlas")
    repository.save("sample", normalized())
    path = repository.document_path("sample")
    path.write_text(path.read_text().replace('"source_id": "sample"', '"source_id": "other"'))

    assert (
        repository.state(
            "sample",
            source_extraction_hash="abc",
            options=NormalizationOptions(),
            normalizer_version="0.5.0",
        )
        is NormalizationState.INCOMPLETE
    )
