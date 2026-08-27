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
from standards_atlas.cli.composition import build_reference_candidate_service
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

    service = build_reference_candidate_service(workspace)
    result = service.detect("SAMPLE")

    assert result.candidates[0].normalized_reference == "1"
    assert service.load("SAMPLE") == result


def test_service_derives_missing_part_view_from_master_document(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        Standard(
            key=StandardKey(value="ISO26262"),
            title="ISO 26262",
            name="ISO 26262",
            clauses=(
                Clause(
                    id=ClauseId(value="part-7"),
                    reference=StandardReference(standard="ISO 26262", clause="1", part="7"),
                    clause_type=ClauseType.CLAUSE,
                ),
                Clause(
                    id=ClauseId(value="part-8"),
                    reference=StandardReference(standard="ISO 26262", clause="1", part="8"),
                    clause_type=ClauseType.CLAUSE,
                ),
            ),
        )
    )
    NormalizationArtifactRepository(workspace).save(
        "ISO26262-8",
        NormalizedExtractedDocument(
            source_id="ISO26262-8",
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

    result = build_reference_candidate_service(workspace).detect("ISO26262-8")

    derived = repository.load(StandardKey(value="ISO26262-8"))
    assert derived.parent_key.value == "ISO26262"
    assert [clause.id.value for clause in derived.clauses] == ["part-8"]
    assert result.candidates[0].expected_clause_ids == ("part-8",)
