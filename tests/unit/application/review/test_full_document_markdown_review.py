from standards_atlas.application.model import (
    AlignmentResult,
    AlignmentStatus,
    ClauseAlignment,
    MarkdownReviewChangeKind,
)
from standards_atlas.application.review import (
    FullDocumentReviewDiffer,
    FullDocumentReviewParser,
    FullDocumentReviewRenderer,
    MarkdownReviewOverrideBuilder,
)


def _aligned(automatic: AlignmentResult) -> AlignmentResult:
    return automatic.model_copy(
        update={
            "clauses": (
                ClauseAlignment(
                    clause_id="c1",
                    expected_reference="1",
                    candidate_item_id="i1",
                    status=AlignmentStatus.EXACT,
                    start_sequence_number=0,
                    end_sequence_number=0,
                    source_item_ids=("i1",),
                    observed_title="One",
                ),
                automatic.clauses[1],
            )
        }
    )


def test_full_review_renders_single_hash_and_item_anchors(review_documents) -> None:
    automatic, normalized, _, _ = review_documents

    text = FullDocumentReviewRenderer().render(normalized, _aligned(automatic))

    assert "<!-- atlas:item=i1 -->" in text
    assert "# 1 One\n" in text
    assert "# 1 One -" not in text
    assert "## 1 One" not in text
    assert "<!-- atlas:item=i2 -->\n2 Two" in text


def test_added_marker_preserves_inline_content(review_documents) -> None:
    _, normalized, _, _ = review_documents
    parser = FullDocumentReviewParser()
    differ = FullDocumentReviewDiffer()
    generated_text = FullDocumentReviewRenderer().render(
        normalized,
        review_documents[0],
    )
    edited_text = generated_text.replace("2 Two", "# 2 - Two")

    diff = differ.diff(parser.parse(generated_text), parser.parse(edited_text))

    assert [change.kind for change in diff.changes] == [MarkdownReviewChangeKind.ADD_ALIGNMENT]
    assert not diff.content_changes


def test_removing_hashes_deactivates_alignment_without_content_change(
    review_documents,
) -> None:
    automatic, normalized, _, _ = review_documents
    parser = FullDocumentReviewParser()
    differ = FullDocumentReviewDiffer()
    generated_text = FullDocumentReviewRenderer().render(normalized, _aligned(automatic))
    edited_text = generated_text.replace("# 1 One", "1 One -")

    diff = differ.diff(parser.parse(generated_text), parser.parse(edited_text))

    assert [change.kind for change in diff.changes] == [MarkdownReviewChangeKind.REMOVE_ALIGNMENT]
    assert not diff.content_changes


def test_multiple_hashes_are_recorded_as_explicit_level_change(review_documents) -> None:
    automatic, normalized, _, _ = review_documents
    parser = FullDocumentReviewParser()
    differ = FullDocumentReviewDiffer()
    generated_text = FullDocumentReviewRenderer().render(normalized, _aligned(automatic))
    edited_text = generated_text.replace("# 1 One", "### 1 One")

    diff = differ.diff(parser.parse(generated_text), parser.parse(edited_text))

    assert diff.changes[0].kind is MarkdownReviewChangeKind.CHANGE_LEVEL
    assert diff.changes[0].level == 3


def test_override_builder_translates_added_marker(review_documents) -> None:
    automatic, normalized, _, engineering = review_documents
    parser = FullDocumentReviewParser()
    differ = FullDocumentReviewDiffer()
    generated_text = FullDocumentReviewRenderer().render(normalized, automatic)
    edited_text = generated_text.replace("1 One", "# 1 - One")
    diff = differ.diff(parser.parse(generated_text), parser.parse(edited_text))

    overrides = MarkdownReviewOverrideBuilder().build(diff, engineering, automatic)

    assert overrides.overrides[0].action.value == "assign"
    assert overrides.overrides[0].clause_id == "c1"
    assert overrides.overrides[0].candidate_item_id == "i1"


def test_content_modification_is_reported(review_documents) -> None:
    automatic, normalized, _, _ = review_documents
    parser = FullDocumentReviewParser()
    differ = FullDocumentReviewDiffer()
    generated_text = FullDocumentReviewRenderer().render(normalized, automatic)
    edited_text = generated_text.replace("2 Two", "2 Changed")

    diff = differ.diff(parser.parse(generated_text), parser.parse(edited_text))

    assert diff.content_changes[0].item_id == "i2"


def test_low_confidence_alignment_is_marked_with_comment(review_documents) -> None:
    automatic, normalized, _, _ = review_documents
    low_confidence = automatic.model_copy(
        update={
            "clauses": (
                ClauseAlignment(
                    clause_id="c1",
                    expected_reference="1",
                    candidate_item_id="i1",
                    status=AlignmentStatus.LOW_CONFIDENCE,
                    confidence=0.78,
                    start_sequence_number=0,
                    end_sequence_number=0,
                    source_item_ids=("i1",),
                    observed_remainder="One",
                    remainder_kind="content",
                ),
                automatic.clauses[1],
            )
        }
    )

    text = FullDocumentReviewRenderer().render(normalized, low_confidence)

    assert "<!-- atlas:alignment-confidence=low reference=1 confidence=0.78 -->" in text
    assert "# 1 -\n\nOne" in text


def test_exact_alignment_without_heading_has_no_dash_and_content_on_next_line(
    review_documents,
) -> None:
    automatic, normalized, _, _ = review_documents
    exact_without_heading = automatic.model_copy(
        update={
            "clauses": (
                ClauseAlignment(
                    clause_id="c1",
                    expected_reference="1",
                    candidate_item_id="i1",
                    status=AlignmentStatus.EXACT,
                    start_sequence_number=0,
                    end_sequence_number=0,
                    source_item_ids=("i1",),
                    observed_remainder="One",
                    remainder_kind="content",
                ),
                automatic.clauses[1],
            )
        }
    )

    text = FullDocumentReviewRenderer().render(normalized, exact_without_heading)

    assert "# 1\n\nOne" in text
    assert "# 1 -" not in text


def test_sequence_inferred_alignment_uses_dash_before_line_break(
    review_documents,
) -> None:
    automatic, normalized, _, _ = review_documents
    inferred = automatic.model_copy(
        update={
            "clauses": (
                ClauseAlignment(
                    clause_id="c1",
                    expected_reference="1",
                    candidate_item_id="i1",
                    status=AlignmentStatus.SEQUENCE_INFERRED,
                    start_sequence_number=0,
                    end_sequence_number=0,
                    source_item_ids=("i1",),
                    observed_remainder="One",
                    remainder_kind="content",
                ),
                automatic.clauses[1],
            )
        }
    )

    text = FullDocumentReviewRenderer().render(normalized, inferred)

    assert "# 1 -\n\nOne" in text


def test_parser_accepts_new_heading_format_without_dash() -> None:
    parsed = FullDocumentReviewParser().parse(
        "<!-- atlas:item=i1 -->\n# 1 Heading\n\nClause content\n"
    )

    block = parsed.blocks[0]
    assert block.heading is not None
    assert block.heading.reference == "1"
    assert block.heading.heading == "Heading"
    assert block.body == "Clause content"
