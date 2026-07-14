from datetime import UTC, datetime

import pytest

from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.model import (
    ReferenceCandidateDocument,
    ReferenceDetectionMetadata,
    ReferenceDetectionStatistics,
)


def candidate_document():
    return ReferenceCandidateDocument(
        source_id="sample",
        metadata=ReferenceDetectionMetadata(
            detector_version="test",
            source_normalization_hash="n",
            expected_structure_hash="e",
            created_at=datetime.now(UTC),
            statistics=ReferenceDetectionStatistics(),
        ),
    )


def test_roundtrip_below_private_workspace(tmp_path):
    repository = ReferenceCandidateRepository(tmp_path / ".atlas")
    path = repository.save("SAMPLE", candidate_document())
    assert (
        path
        == (tmp_path / ".atlas" / "reference-candidates" / "SAMPLE" / "document.json").resolve()
    )
    assert repository.load("SAMPLE").source_id == "sample"


@pytest.mark.parametrize("key", ["", ".", "..", "../public", "/tmp/public", "a/b", "a\\b"])
def test_rejects_path_components(tmp_path, key):
    with pytest.raises(ValueError):
        ReferenceCandidateRepository(tmp_path / ".atlas").document_path(key)
