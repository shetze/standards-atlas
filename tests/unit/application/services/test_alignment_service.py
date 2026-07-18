from datetime import UTC, datetime

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.adapters.reference_detection import ReferenceCandidateRepository
from standards_atlas.application.model import (
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedHeading,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceCandidateStatus,
    ReferenceDetectionMetadata,
    ReferenceDetectionStatistics,
    ReferenceMatchKind,
)
from standards_atlas.application.services import AlignmentService
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    Standard,
    StandardKey,
    StandardReference,
)


def test_service_loads_aligns_persists_and_reloads(tmp_path):
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
    ReferenceCandidateRepository(workspace).save(
        "SAMPLE",
        ReferenceCandidateDocument(
            source_id="SAMPLE",
            candidates=(
                ReferenceCandidate(
                    item_id="h1",
                    sequence_number=0,
                    raw_reference="1",
                    normalized_reference="1",
                    title_remainder="Scope",
                    match_kind=ReferenceMatchKind.EXACT,
                    status=ReferenceCandidateStatus.EXPECTED,
                    confidence=0.99,
                    expected_clause_ids=("SAMPLE-1",),
                ),
            ),
            metadata=ReferenceDetectionMetadata(
                detector_version="test",
                source_normalization_hash="n",
                expected_structure_hash="e",
                created_at=datetime.now(UTC),
                statistics=ReferenceDetectionStatistics(candidates=1),
            ),
        ),
    )

    service = AlignmentService(workspace)
    alignment = service.run("SAMPLE")

    assert alignment.clauses[0].clause_id == "SAMPLE-1"
    assert service.load("SAMPLE") == alignment


def test_service_orders_expanded_subclauses_by_physical_reference(tmp_path):
    workspace = tmp_path / ".atlas"
    clauses = tuple(
        Clause(
            id=ClauseId(value=f"SAMPLE-{reference}"),
            reference=StandardReference(standard="SAMPLE", clause=reference),
            clause_type=ClauseType.CLAUSE,
        )
        for reference in ("1", "2", "3", "1.1", "1.2")
    )
    FileSystemEngineeringDocumentRepository(workspace).save(
        Standard(
            key=StandardKey(value="SAMPLE"),
            title="Sample",
            name="Sample",
            clauses=clauses,
        )
    )
    items = tuple(
        NormalizedHeading(
            id=f"h-{reference}",
            sequence_number=index,
            source_item_ids=(f"h-{reference}",),
            text=reference,
        )
        for index, reference in enumerate(("1", "1.1", "1.2", "2", "3"))
    )
    NormalizationArtifactRepository(workspace).save(
        "SAMPLE",
        NormalizedExtractedDocument(
            source_id="SAMPLE",
            items=items,
            metadata=NormalizationMetadata(
                normalizer_version="test",
                source_extraction_hash="hash",
                created_at=datetime.now(UTC),
                options=NormalizationOptions(),
                statistics=NormalizationStatistics(input_items=5, output_items=5),
            ),
        ),
    )
    candidates = tuple(
        ReferenceCandidate(
            item_id=f"h-{reference}",
            sequence_number=index,
            raw_reference=reference,
            normalized_reference=reference,
            match_kind=ReferenceMatchKind.EXACT,
            status=ReferenceCandidateStatus.EXPECTED,
            confidence=0.99,
            expected_clause_ids=(f"SAMPLE-{reference}",),
        )
        for index, reference in enumerate(("1", "1.1", "1.2", "2", "3"))
    )
    ReferenceCandidateRepository(workspace).save(
        "SAMPLE",
        ReferenceCandidateDocument(
            source_id="SAMPLE",
            candidates=candidates,
            metadata=ReferenceDetectionMetadata(
                detector_version="test",
                source_normalization_hash="n",
                expected_structure_hash="e",
                created_at=datetime.now(UTC),
                statistics=ReferenceDetectionStatistics(candidates=5),
            ),
        ),
    )

    alignment = AlignmentService(workspace).run("SAMPLE")

    assert [item.expected_reference for item in alignment.clauses] == [
        "1", "1.1", "1.2", "2", "3"
    ]
    assert alignment.metadata.statistics.missing == 0
