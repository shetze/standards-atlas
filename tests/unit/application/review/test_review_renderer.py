from standards_atlas.application.model import (
    AlignmentResult,
    NormalizedExtractedDocument,
    ReferenceCandidateDocument,
)
from standards_atlas.application.review import AlignmentReviewRenderer
from standards_atlas.domain.model import EngineeringDocument

ReviewDocuments = tuple[
    AlignmentResult,
    NormalizedExtractedDocument,
    ReferenceCandidateDocument,
    EngineeringDocument,
]


def test_review_contains_missing_clause_and_override_example(
    review_documents: ReviewDocuments,
) -> None:
    automatic, normalized, candidates, engineering = review_documents

    text = AlignmentReviewRenderer().render(
        automatic,
        normalized,
        candidates,
        engineering,
    )

    assert "# Alignment Review: DOC" in text
    assert "## missing: 1" in text
    assert "action: assign" in text


def test_review_uses_candidate_alternative_in_override_example(
    review_documents: ReviewDocuments,
) -> None:
    automatic, normalized, candidates, engineering = review_documents

    text = AlignmentReviewRenderer().render(
        automatic,
        normalized,
        candidates,
        engineering,
    )

    assert "candidate_item_id: i1" in text
    assert "candidate_item_id: normalized:#/texts/" not in text


def test_review_uses_normalized_text_prefix_without_candidate_alternative(
    review_documents: ReviewDocuments,
) -> None:
    automatic, normalized, candidates, engineering = review_documents
    candidates_without_alternatives = candidates.model_copy(update={"candidates": ()})

    text = AlignmentReviewRenderer().render(
        automatic,
        normalized,
        candidates_without_alternatives,
        engineering,
    )

    assert "candidate_item_id: normalized:#/texts/" in text
    assert "candidate_item_id: <item-id>" not in text
