from datetime import UTC, datetime

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.application.model import (
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedHeading,
)
from standards_atlas.application.services import ReferenceCandidateService
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    Standard,
    StandardKey,
    StandardReference,
)


def test_service_loads_inputs_detects_and_persists_candidates(tmp_path):
    workspace = tmp_path / ".atlas"
    FileSystemEngineeringDocumentRepository(workspace).save(
        Standard(
            key=StandardKey(value="SAMPLE"),
            title="Sample",
            name="Sample",
            clauses=(
                Clause(
                    id=ClauseId(value="SAMPLE-1"),
                    reference=StandardReference(standard="SAMPLE", clause="1"),
                    clause_type=ClauseType.CLAUSE,
                ),
            ),
        )
    )
    NormalizationArtifactRepository(workspace).save(
        "SAMPLE",
        NormalizedExtractedDocument(
            source_id="SAMPLE",
            items=(
                NormalizedHeading(
                    id="h1",
                    sequence_number=0,
                    source_item_ids=("h1",),
                    text="1 Scope",
                ),
            ),
            metadata=NormalizationMetadata(
                normalizer_version="test",
                source_extraction_hash="hash",
                created_at=datetime.now(UTC),
                options=NormalizationOptions(),
                statistics=NormalizationStatistics(input_items=1, output_items=1),
            ),
        ),
    )

    service = ReferenceCandidateService(workspace)
    result = service.detect("SAMPLE")

    assert result.candidates[0].normalized_reference == "1"
    assert service.load("SAMPLE") == result
