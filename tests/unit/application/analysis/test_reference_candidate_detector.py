from datetime import UTC, datetime

from standards_atlas.application.analysis import ReferenceCandidateDetector
from standards_atlas.application.model import (
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedHeading,
    NormalizedText,
    ReferenceCandidateStatus,
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
            statistics=NormalizationStatistics(input_items=len(items), output_items=len(items)),
        ),
    )


def engineering(*references):
    return EngineeringDocument(
        key=DocumentKey(value="SAMPLE"),
        title="Sample",
        document_type=DocumentType.STANDARD,
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"SAMPLE-{ref}"),
                reference=StandardReference(standard="SAMPLE", clause=ref),
                clause_type=ClauseType.CLAUSE,
            )
            for ref in references
        ),
    )


def heading(identifier, sequence, text):
    return NormalizedHeading(
        id=identifier,
        sequence_number=sequence,
        source_item_ids=(identifier,),
        text=text,
    )


def test_detects_exact_numeric_heading_against_expected_structure():
    result = ReferenceCandidateDetector().detect(
        normalized(heading("h1", 0, "6.4.2 Software requirements")),
        engineering("6.4.2"),
    )
    candidate = result.candidates[0]
    assert candidate.normalized_reference == "6.4.2"
    assert candidate.title_remainder == "Software requirements"
    assert candidate.status is ReferenceCandidateStatus.EXPECTED
    assert candidate.match_kind is ReferenceMatchKind.EXACT


def test_normalizes_spacing_and_trailing_dot():
    result = ReferenceCandidateDetector().detect(
        normalized(heading("h1", 0, "6 . 4 . 2. Software requirements")),
        engineering("6.4.2"),
    )
    assert result.candidates[0].normalized_reference == "6.4.2"
    assert result.candidates[0].match_kind is ReferenceMatchKind.NORMALIZED


def test_detects_annex_and_annex_subclause():
    result = ReferenceCandidateDetector().detect(
        normalized(
            heading("a", 0, "Annex A Informative material"),
            heading("a1", 1, "A.1 Example"),
        ),
        engineering("A", "A.1"),
    )
    assert [candidate.normalized_reference for candidate in result.candidates] == ["A", "A.1"]
    assert all(candidate.match_kind is ReferenceMatchKind.ANNEX for candidate in result.candidates)


def test_reports_unexpected_reference_without_dropping_it():
    result = ReferenceCandidateDetector().detect(
        normalized(heading("h", 0, "9.9 Unknown")),
        engineering("1"),
    )
    assert result.candidates[0].status is ReferenceCandidateStatus.UNEXPECTED
    assert result.issues[0].code == "UNEXPECTED_REFERENCE"


def test_does_not_treat_arbitrary_number_in_text_as_clause_reference():
    text = NormalizedText(
        id="t",
        sequence_number=0,
        source_item_ids=("t",),
        text="The value 6.4.2 is referenced here.",
    )
    result = ReferenceCandidateDetector().detect(normalized(text), engineering("6.4.2"))
    assert result.candidates == ()


def test_accepts_inline_reference_only_at_text_start_with_title():
    text = NormalizedText(id="t", sequence_number=0, source_item_ids=("t",), text="2 Scope")
    result = ReferenceCandidateDetector().detect(normalized(text), engineering("2"))
    assert result.candidates[0].status is ReferenceCandidateStatus.EXPECTED
    assert result.candidates[0].confidence < 0.9


def test_pure_reference_text_item_creates_candidate() -> None:
    reference = NormalizedText(
        id="ref",
        sequence_number=0,
        source_item_ids=("ref",),
        text="3.1.15",
    )
    result = ReferenceCandidateDetector().detect(normalized(reference), engineering("3.1.15"))
    candidate = result.candidates[0]
    assert candidate.status is ReferenceCandidateStatus.EXPECTED
    assert candidate.title_remainder is None
    assert candidate.remainder_kind.value == "unknown"


def test_pure_reference_followed_by_term_preserves_following_label() -> None:
    reference = NormalizedText(
        id="ref",
        sequence_number=0,
        source_item_ids=("ref",),
        text="3.1.15",
    )
    term = NormalizedText(
        id="term",
        sequence_number=1,
        source_item_ids=("term",),
        text="availability",
    )
    result = ReferenceCandidateDetector().detect(
        normalized(reference, term),
        engineering("3.1.15"),
    )
    candidate = result.candidates[0]
    assert candidate.following_label_item_id == "term"
    assert candidate.following_label == "availability"


def test_inline_text_remainder_is_classified_as_content() -> None:
    text = NormalizedText(
        id="scope",
        sequence_number=0,
        source_item_ids=("scope",),
        text="1.1 This document specifies the process and technical requirements.",
    )
    result = ReferenceCandidateDetector().detect(normalized(text), engineering("1.1"))
    candidate = result.candidates[0]
    assert candidate.title_remainder.startswith("This document specifies")
    assert candidate.remainder_kind.value == "content"


def test_heading_remainder_is_classified_as_title() -> None:
    result = ReferenceCandidateDetector().detect(
        normalized(heading("h", 0, "6.4.2 Software requirements")),
        engineering("6.4.2"),
    )
    assert result.candidates[0].remainder_kind.value == "title"


def test_following_clause_reference_is_not_used_as_term_label() -> None:
    first = NormalizedText(
        id="first",
        sequence_number=0,
        source_item_ids=("first",),
        text="3.1.15",
    )
    second = NormalizedText(
        id="second",
        sequence_number=1,
        source_item_ids=("second",),
        text="3.1.16 next term",
    )
    result = ReferenceCandidateDetector().detect(
        normalized(first, second),
        engineering("3.1.15", "3.1.16"),
    )
    assert result.candidates[0].following_label is None
