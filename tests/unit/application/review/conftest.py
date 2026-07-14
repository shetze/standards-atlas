from datetime import UTC, datetime

import pytest

from standards_atlas.application.model import (
    AlignmentMetadata,
    AlignmentOptions,
    AlignmentResult,
    AlignmentStatistics,
    AlignmentStatus,
    ClauseAlignment,
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedText,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceCandidateStatus,
    ReferenceDetectionMetadata,
    ReferenceDetectionStatistics,
    ReferenceMatchKind,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


@pytest.fixture
def review_documents() -> tuple[
    AlignmentResult,
    NormalizedExtractedDocument,
    ReferenceCandidateDocument,
    EngineeringDocument,
]:
    now = datetime.now(UTC)
    engineering = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.STANDARD,
        clauses=(
            Clause(
                id=ClauseId(value="c1"),
                reference=StandardReference(standard="DOC", clause="1"),
                clause_type=ClauseType.CLAUSE,
                title="One",
            ),
            Clause(
                id=ClauseId(value="c2"),
                reference=StandardReference(standard="DOC", clause="2"),
                clause_type=ClauseType.CLAUSE,
                title="Two",
            ),
        ),
    )
    normalized = NormalizedExtractedDocument(
        source_id="DOC",
        items=(
            NormalizedText(
                id="i1",
                sequence_number=0,
                source_item_ids=("s1",),
                text="1 One",
            ),
            NormalizedText(
                id="i2",
                sequence_number=1,
                source_item_ids=("s2",),
                text="2 Two",
            ),
        ),
        metadata=NormalizationMetadata(
            normalizer_version="x",
            source_extraction_hash="x",
            created_at=now,
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(),
        ),
    )
    candidates = ReferenceCandidateDocument(
        source_id="DOC",
        candidates=(
            ReferenceCandidate(
                item_id="i1",
                sequence_number=0,
                raw_reference="1",
                normalized_reference="1",
                match_kind=ReferenceMatchKind.EXACT,
                status=ReferenceCandidateStatus.EXPECTED,
                confidence=0.9,
                expected_clause_ids=("c1",),
            ),
            ReferenceCandidate(
                item_id="i2",
                sequence_number=1,
                raw_reference="2",
                normalized_reference="2",
                match_kind=ReferenceMatchKind.EXACT,
                status=ReferenceCandidateStatus.EXPECTED,
                confidence=0.9,
                expected_clause_ids=("c2",),
            ),
        ),
        metadata=ReferenceDetectionMetadata(
            detector_version="x",
            source_normalization_hash="x",
            expected_structure_hash="x",
            created_at=now,
            statistics=ReferenceDetectionStatistics(),
        ),
    )
    automatic = AlignmentResult(
        source_id="DOC",
        clauses=(
            ClauseAlignment(
                clause_id="c1",
                expected_reference="1",
                status=AlignmentStatus.MISSING,
            ),
            ClauseAlignment(
                clause_id="c2",
                expected_reference="2",
                status=AlignmentStatus.MISSING,
            ),
        ),
        metadata=AlignmentMetadata(
            alignment_version="x",
            normalized_document_hash="x",
            candidate_document_hash="x",
            expected_structure_hash="x",
            created_at=now,
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(expected_clauses=2, missing=2),
        ),
    )
    return automatic, normalized, candidates, engineering
