from standards_atlas.application.model import (
    AlignmentOverrideDocument,
    AlignmentResult,
    AssignOverride,
    NormalizedExtractedDocument,
    ReferenceCandidateDocument,
)
from standards_atlas.application.review import AlignmentOverrideEngine
from standards_atlas.domain.model import EngineeringDocument

ReviewDocuments = tuple[
    AlignmentResult,
    NormalizedExtractedDocument,
    ReferenceCandidateDocument,
    EngineeringDocument,
]


def test_assign_override_creates_manual_alignment(
    review_documents: ReviewDocuments,
) -> None:
    automatic, normalized, candidates, engineering = review_documents
    overrides = AlignmentOverrideDocument(
        document_key="DOC",
        overrides=(
            AssignOverride(
                clause_id="c1",
                candidate_item_id="i1",
            ),
        ),
    )

    result = AlignmentOverrideEngine().apply(
        overrides,
        automatic,
        normalized,
        candidates,
        engineering,
    )

    assert result.clauses[0].status.value == "manual"
    assert result.clauses[0].candidate_item_id == "i1"
    assert result.clauses[0].source_item_ids == ("i1", "i2")


def test_validation_rejects_unknown_candidate(
    review_documents: ReviewDocuments,
) -> None:
    automatic, normalized, candidates, engineering = review_documents
    overrides = AlignmentOverrideDocument(
        document_key="DOC",
        overrides=(
            AssignOverride(
                clause_id="c1",
                candidate_item_id="missing",
            ),
        ),
    )

    result = AlignmentOverrideEngine().validate(
        overrides,
        automatic,
        normalized,
        candidates,
        engineering,
    )

    assert not result.valid
    assert result.issues[0].code == "UNKNOWN_CANDIDATE"
