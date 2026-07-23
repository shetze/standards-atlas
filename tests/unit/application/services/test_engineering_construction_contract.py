import hashlib
import json
from datetime import UTC, datetime

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
    NormalizedHeading,
    NormalizedText,
    UnassignedRange,
)
from standards_atlas.application.services import EngineeringConstructionContractValidator


def test_accepts_complete_non_overlapping_partition():
    normalized = _normalized()
    alignment = _alignment(normalized)

    result = EngineeringConstructionContractValidator().validate(
        normalized, alignment, alignment, reviewed_alignment_used=False
    )

    assert result.valid is True
    assert result.coverage.active_items == 4
    assert result.coverage.assigned_items == 4
    assert result.coverage.unassigned_items == 0


def test_rejects_overlapping_clause_ranges():
    normalized = _normalized()
    alignment = _alignment(normalized, second_start=1)

    result = EngineeringConstructionContractValidator().validate(
        normalized, alignment, alignment, reviewed_alignment_used=False
    )

    assert result.valid is False
    assert {item.code for item in result.diagnostics} >= {
        "overlapping_clause_ranges",
        "items_assigned_multiple_times",
    }


def test_requires_unassigned_items_to_be_classified():
    normalized = _normalized()
    alignment = _alignment(normalized, first_end=0, second_start=3)

    result = EngineeringConstructionContractValidator().validate(
        normalized, alignment, alignment, reviewed_alignment_used=False
    )

    assert result.valid is False
    assert result.coverage.unassigned_items == 2
    assert "unaccounted_normalized_items" in {item.code for item in result.diagnostics}


def test_accepts_explicit_between_clause_range():
    normalized = _normalized()
    alignment = _alignment(normalized, first_end=0, second_start=3).model_copy(
        update={
            "unassigned_ranges": (
                UnassignedRange(
                    kind="between_clauses",
                    start_sequence_number=1,
                    end_sequence_number=2,
                    source_item_ids=("p1", "p2"),
                ),
            )
        }
    )

    result = EngineeringConstructionContractValidator().validate(
        normalized, alignment, alignment, reviewed_alignment_used=False
    )

    assert result.valid is True
    assert result.coverage.between_clause_items == 2


def test_rejects_following_label_outside_clause_range():
    normalized = _normalized()
    clauses = list(_alignment(normalized).clauses)
    clauses[0] = clauses[0].model_copy(update={"following_label_item_id": "h2"})
    alignment = _alignment(normalized).model_copy(update={"clauses": tuple(clauses)})

    result = EngineeringConstructionContractValidator().validate(
        normalized, alignment, alignment, reviewed_alignment_used=False
    )

    assert result.valid is False
    assert "following_label_outside_range" in {item.code for item in result.diagnostics}


def test_rejects_review_without_valid_integrity_manifest():
    normalized = _normalized()
    alignment = _alignment(normalized)

    result = EngineeringConstructionContractValidator().validate(
        normalized,
        alignment,
        alignment,
        reviewed_alignment_used=True,
        reviewed_integrity_valid=False,
        reviewed_integrity_message="changed",
    )

    assert result.valid is False
    assert result.reviewed_alignment_unchanged is False
    assert "reviewed_alignment_stale" in {item.code for item in result.diagnostics}


def _normalized():
    items = (
        NormalizedHeading(id="h1", sequence_number=0, source_item_ids=("h1",), text="1"),
        NormalizedText(id="p1", sequence_number=1, source_item_ids=("p1",), text="A"),
        NormalizedText(id="p2", sequence_number=2, source_item_ids=("p2",), text="B"),
        NormalizedHeading(id="h2", sequence_number=3, source_item_ids=("h2",), text="2"),
    )
    return NormalizedExtractedDocument(
        source_id="SAMPLE",
        items=items,
        metadata=NormalizationMetadata(
            normalizer_version="test",
            source_extraction_hash="source",
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(input_items=4, output_items=4),
        ),
    )


def _alignment(
    normalized: NormalizedExtractedDocument,
    *,
    first_end: int = 1,
    second_start: int = 2,
) -> AlignmentResult:
    clauses = (
        ClauseAlignment(
            clause_id="SAMPLE-1",
            expected_reference="1",
            candidate_item_id="h1",
            status=AlignmentStatus.EXACT,
            start_sequence_number=0,
            end_sequence_number=first_end,
        ),
        ClauseAlignment(
            clause_id="SAMPLE-2",
            expected_reference="2",
            candidate_item_id="h2",
            status=AlignmentStatus.EXACT,
            start_sequence_number=second_start,
            end_sequence_number=3,
        ),
    )
    return AlignmentResult(
        source_id="SAMPLE",
        clauses=clauses,
        metadata=AlignmentMetadata(
            alignment_version="test",
            normalized_document_hash=_model_hash(normalized),
            candidate_document_hash="candidate",
            expected_structure_hash="structure",
            created_at=datetime.now(UTC),
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(expected_clauses=2, exact_matches=2),
        ),
    )


def _model_hash(model) -> str:
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
