from datetime import UTC, datetime

from standards_atlas.application.alignment import AlignmentEngine
from standards_atlas.application.alignment.alignment_engine import _ExpectedClause
from standards_atlas.application.alignment.matching import candidate_index
from standards_atlas.application.alignment.recovery import recover_low_confidence_candidates
from standards_atlas.application.model import (
    AlignmentStatus,
    CandidateRemainderKind,
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedHeading,
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


def normalized(*items):
    return NormalizedExtractedDocument(
        source_id="sample",
        items=items,
        metadata=NormalizationMetadata(
            normalizer_version="test",
            source_extraction_hash="hash",
            created_at=datetime.now(UTC),
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(
                input_items=len(items),
                output_items=len(items),
            ),
        ),
    )


def engineering(*references):
    return EngineeringDocument(
        key=DocumentKey(value="SAMPLE"),
        title="Sample",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"SAMPLE-{reference}"),
                reference=StandardReference(
                    standard="SAMPLE",
                    clause=reference,
                ),
                clause_type=ClauseType.CLAUSE,
                title=f"Title {reference}",
            )
            for reference in references
        ),
    )


def candidates(*values):
    return ReferenceCandidateDocument(
        source_id="sample",
        candidates=values,
        metadata=ReferenceDetectionMetadata(
            detector_version="test",
            source_normalization_hash="n",
            expected_structure_hash="e",
            created_at=datetime.now(UTC),
            statistics=ReferenceDetectionStatistics(candidates=len(values)),
        ),
    )


def candidate(reference, sequence, *, confidence=0.9, kind=ReferenceMatchKind.EXACT):
    return ReferenceCandidate(
        item_id=f"h-{sequence}",
        sequence_number=sequence,
        raw_reference=reference,
        normalized_reference=reference,
        title_remainder=f"Title {reference}",
        match_kind=kind,
        status=ReferenceCandidateStatus.EXPECTED,
        confidence=confidence,
        expected_clause_ids=(f"SAMPLE-{reference}",),
    )


def heading(sequence, text):
    return NormalizedHeading(
        id=f"h-{sequence}",
        sequence_number=sequence,
        source_item_ids=(f"h-{sequence}",),
        text=text,
    )


def text(sequence, value):
    return NormalizedText(
        id=f"t-{sequence}",
        sequence_number=sequence,
        source_item_ids=(f"t-{sequence}",),
        text=value,
    )


def test_exact_candidates_align_and_form_ranges():
    result = AlignmentEngine().align(
        normalized(
            heading(0, "1 Scope"),
            text(1, "Scope text"),
            heading(2, "2 Requirements"),
            text(3, "Requirement text"),
        ),
        candidates(candidate("1", 0), candidate("2", 2)),
        engineering("1", "2"),
    )

    assert [clause.status for clause in result.clauses] == [
        AlignmentStatus.EXACT,
        AlignmentStatus.EXACT,
    ]
    assert result.clauses[0].source_item_ids == ("h-0", "t-1")
    assert result.clauses[1].source_item_ids == ("h-2", "t-3")


def test_duplicate_candidate_prefers_higher_confidence():
    result = AlignmentEngine().align(
        normalized(heading(0, "1 Duplicate"), heading(2, "1 Scope")),
        candidates(
            candidate("1", 0, confidence=0.6),
            candidate("1", 2, confidence=0.98),
        ),
        engineering("1"),
    )

    assert result.clauses[0].candidate_item_id == "h-2"
    assert result.clauses[0].alternative_item_ids == ("h-0",)
    assert any(issue.code == "DUPLICATE_REFERENCE" for issue in result.issues)


def test_out_of_order_candidate_is_reported_and_missing():
    result = AlignmentEngine().align(
        normalized(heading(0, "2 Two"), heading(1, "1 One")),
        candidates(candidate("2", 0), candidate("1", 1)),
        engineering("1", "2"),
    )

    assert result.clauses[1].status is AlignmentStatus.MISSING
    assert any(issue.code == "OUT_OF_ORDER_REFERENCE" for issue in result.issues)


def test_single_missing_clause_is_inferred_between_neighbours():
    result = AlignmentEngine().align(
        normalized(
            heading(0, "1 One"),
            text(1, "Intermediate content"),
            heading(2, "3 Three"),
        ),
        candidates(candidate("1", 0), candidate("3", 2)),
        engineering("1", "2", "3"),
    )

    assert result.clauses[1].status is AlignmentStatus.SEQUENCE_INFERRED
    assert result.clauses[1].start_sequence_number == 1
    assert any(issue.code == "INFERRED_REFERENCE" for issue in result.issues)


def test_front_matter_is_preserved_as_unassigned():
    result = AlignmentEngine().align(
        normalized(text(0, "Foreword"), heading(1, "1 Scope")),
        candidates(candidate("1", 1)),
        engineering("1"),
    )

    assert result.unassigned_ranges[0].kind == "front_matter"
    assert result.unassigned_ranges[0].source_item_ids == ("t-0",)


def test_alignment_is_deterministic_except_timestamp():
    args = (
        normalized(heading(0, "1 Scope")),
        candidates(candidate("1", 0)),
        engineering("1"),
    )
    first = AlignmentEngine().align(*args).model_dump()
    second = AlignmentEngine().align(*args).model_dump()
    first["metadata"].pop("created_at")
    second["metadata"].pop("created_at")
    assert first == second


def test_inline_content_candidate_does_not_trigger_title_mismatch() -> None:
    normalized_document = normalized(
        NormalizedText(
            id="inline",
            sequence_number=0,
            source_item_ids=("inline",),
            text="1.1 This document specifies the process.",
        )
    )
    engineering_document = engineering("1.1")
    candidate_document = candidates(
        ReferenceCandidate(
            item_id="inline",
            sequence_number=0,
            raw_reference="1.1",
            normalized_reference="1.1",
            title_remainder="This document specifies the process.",
            remainder_kind=CandidateRemainderKind.CONTENT,
            match_kind=ReferenceMatchKind.EXACT,
            status=ReferenceCandidateStatus.EXPECTED,
            confidence=0.78,
            expected_clause_ids=("SAMPLE-1.1",),
        )
    )
    result = AlignmentEngine().align(
        normalized_document,
        candidate_document,
        engineering_document,
    )
    alignment = result.clauses[0]
    assert alignment.observed_title is None
    assert alignment.observed_remainder == "This document specifies the process."
    assert alignment.remainder_kind is CandidateRemainderKind.CONTENT
    assert all(issue.code != "TITLE_MISMATCH" for issue in result.issues)


def test_missing_clause_recovers_bounded_lower_confidence_candidate() -> None:
    result = AlignmentEngine().align(
        normalized(
            heading(0, "1 One"),
            text(1, "2 Normative clause content without heading"),
            heading(2, "3 Three"),
        ),
        candidates(
            candidate("1", 0),
            candidate("2", 1, confidence=0.78),
            candidate("3", 2),
        ),
        engineering("1", "2", "3"),
    )

    # Simulate a primary-pass miss caused by an earlier selection decision by
    # exercising recovery directly with the middle candidate omitted initially.
    expected = tuple(
        _ExpectedClause(clause=clause, index=index)
        for index, clause in enumerate(engineering("1", "2", "3").clauses)
    )
    initial = [
        result.clauses[0],
        result.clauses[1].model_copy(
            update={
                "candidate_item_id": None,
                "status": AlignmentStatus.MISSING,
                "match_kind": None,
                "confidence": None,
                "start_sequence_number": None,
                "end_sequence_number": None,
                "source_item_ids": (),
            }
        ),
        result.clauses[2],
    ]
    candidate_document = candidates(candidate("2", 1, confidence=0.78))
    issues = []
    recovered = recover_low_confidence_candidates(
        initial,
        expected,
        candidate_index(candidate_document),
        {},
        normalized(
            heading(0, "1 One"),
            text(1, "2 Normative clause content without heading"),
            heading(2, "3 Three"),
        ),
        __import__(
            "standards_atlas.application.model.alignment",
            fromlist=["AlignmentOptions"],
        ).AlignmentOptions(),
        issues,
    )

    assert recovered[1].status is AlignmentStatus.LOW_CONFIDENCE
    assert recovered[1].start_sequence_number == 1
    assert any(issue.code == "LOW_CONFIDENCE_REFERENCE" for issue in issues)


def test_recovers_unique_reference_from_normalized_text_when_candidate_is_missing():
    result = AlignmentEngine().align(
        normalized(
            heading(0, "D.58 Heading"),
            text(1, "D.59 Clause text"),
            heading(2, "D.60 Heading"),
        ),
        candidates(
            candidate("D.58", 0),
            candidate("D.60", 2),
        ),
        engineering("D.58", "D.59", "D.60"),
    )

    recovered = next(item for item in result.clauses if item.expected_reference == "D.59")
    assert recovered.status is AlignmentStatus.LOW_CONFIDENCE
    assert recovered.candidate_item_id == "t-1"
    assert result.metadata.statistics.missing == 0


def test_derived_standard_ignores_legacy_clause_zero_anchor():
    from standards_atlas.domain.model import Standard, StandardKey

    document = Standard(
        key=StandardKey(value="SAMPLE-8"),
        title="Sample Part 8",
        name="Sample Part 8",
        parent_key=StandardKey(value="SAMPLE"),
        clauses=engineering("0", "1", "2").clauses,
    )

    result = AlignmentEngine().align(
        normalized(heading(0, "1 Scope"), heading(1, "2 Requirements")),
        candidates(candidate("1", 0), candidate("2", 1)),
        document,
    )

    assert [clause.expected_reference for clause in result.clauses] == ["1", "2"]
    assert result.metadata.statistics.expected_clauses == 2
    assert result.metadata.statistics.missing == 0
