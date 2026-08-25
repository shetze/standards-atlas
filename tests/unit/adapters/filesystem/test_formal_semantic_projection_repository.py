from __future__ import annotations

from standards_atlas.adapters.filesystem.formal_semantic_projection_repository import (
    FileSystemFormalSemanticProjectionRepository,
)
from standards_atlas.domain.model import FormalSemanticProjection


def test_projection_repository_round_trips_versioned_payload(tmp_path) -> None:
    repository = FileSystemFormalSemanticProjectionRepository(tmp_path)
    projection = FormalSemanticProjection(
        source_document_key="ISO/EXAMPLE:2026",
        projection_version="1.0.0",
        ontology_versions=("standards-atlas-core@1.1.0",),
    )

    repository.save(projection)

    assert repository.load("ISO/EXAMPLE:2026") == projection
    assert repository.load("missing") is None
