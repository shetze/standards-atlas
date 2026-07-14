from datetime import UTC, datetime

import pytest

from standards_atlas.adapters.alignment import (
    AlignmentArtifactRepository,
    AlignmentArtifactState,
)
from standards_atlas.application.model import (
    AlignmentMetadata,
    AlignmentOptions,
    AlignmentResult,
    AlignmentStatistics,
)


def result():
    return AlignmentResult(
        source_id="sample",
        metadata=AlignmentMetadata(
            alignment_version="test",
            normalized_document_hash="n",
            candidate_document_hash="c",
            expected_structure_hash="s",
            created_at=datetime.now(UTC),
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(),
        ),
    )


def test_roundtrip_and_current_state(tmp_path):
    repository = AlignmentArtifactRepository(tmp_path / ".atlas")
    path = repository.save("SAMPLE", result())

    assert path == (tmp_path / ".atlas" / "alignments" / "SAMPLE" / "alignment.json").resolve()
    assert repository.load("SAMPLE").source_id == "sample"
    assert (
        repository.state(
            "SAMPLE",
            normalized_hash="n",
            candidate_hash="c",
            structure_hash="s",
            alignment_version="test",
        )
        is AlignmentArtifactState.CURRENT
    )


def test_stale_and_incomplete_states(tmp_path):
    repository = AlignmentArtifactRepository(tmp_path / ".atlas")
    repository.save("SAMPLE", result())
    assert (
        repository.state(
            "SAMPLE",
            normalized_hash="changed",
            candidate_hash="c",
            structure_hash="s",
            alignment_version="test",
        )
        is AlignmentArtifactState.STALE
    )
    repository.document_path("BROKEN").parent.mkdir(parents=True)
    repository.document_path("BROKEN").write_text("not-json", encoding="utf-8")
    assert (
        repository.state(
            "BROKEN",
            normalized_hash="n",
            candidate_hash="c",
            structure_hash="s",
            alignment_version="test",
        )
        is AlignmentArtifactState.INCOMPLETE
    )


@pytest.mark.parametrize("key", ["", ".", "..", "../public", "/tmp/public", "a/b", "a\\b"])
def test_rejects_path_components(tmp_path, key):
    with pytest.raises(ValueError):
        AlignmentArtifactRepository(tmp_path / ".atlas").document_path(key)
