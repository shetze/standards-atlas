import pytest
from pydantic import ValidationError

from standards_atlas.domain.model import (
    BoundingBox,
    Clause,
    ClauseId,
    ClauseType,
    CoordinateOrigin,
    FormulaBlock,
    ListBlock,
    ListItem,
    NoteBlock,
    PictureBlock,
    SourceEvidence,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def _clause(**changes: object) -> Clause:
    values = {
        "id": ClauseId(value="example-5.1"),
        "reference": StandardReference(
            standard="Example",
            year=2026,
            clause="5.1",
        ),
        "clause_type": ClauseType.REQUIREMENT,
    }
    values.update(changes)
    return Clause(**values)


def test_clause_preserves_ordered_heterogeneous_content() -> None:
    clause = _clause(
        content=(
            TextBlock(id="text-1", text="The supplier shall provide evidence."),
            ListBlock(
                id="list-1",
                ordered=True,
                items=(
                    ListItem(text="analysis"),
                    ListItem(text="test report"),
                ),
            ),
            TableBlock(
                id="table-1",
                caption="Required evidence",
                rows=(
                    TableRow(
                        cells=(
                            TableCell(text="Method", is_header=True),
                            TableCell(text="Result", is_header=True),
                        )
                    ),
                    TableRow(cells=(TableCell(text="Test"), TableCell(text="Pass"))),
                ),
            ),
            FormulaBlock(id="formula-1", expression="S = R / T", representation="latex"),
            PictureBlock(
                id="picture-1",
                caption="System context",
                image_path="documents/example/assets/context.png",
            ),
            NoteBlock(
                id="note-1",
                note_kind="NOTE",
                content=(TextBlock(id="note-text-1", text="Informative guidance."),),
            ),
        )
    )

    assert [block.type for block in clause.content] == [
        "text",
        "list",
        "table",
        "formula",
        "picture",
        "note",
    ]
    assert "The supplier shall provide evidence." in clause.plain_text
    assert "1. analysis" in clause.plain_text
    assert "Method | Result" in clause.plain_text
    assert "NOTE: Informative guidance." in clause.plain_text


def test_content_block_carries_adapter_neutral_source_evidence() -> None:
    evidence = SourceEvidence(
        source_id="EN50716-pdf",
        source_type="pdf",
        locator="#/texts/417",
        page_number=83,
        bounding_box=BoundingBox(
            left=10.0,
            top=20.0,
            right=200.0,
            bottom=60.0,
            coordinate_origin=CoordinateOrigin.TOP_LEFT,
        ),
        extraction_method="docling",
    )
    clause = _clause(
        content=(
            TextBlock(
                id="text-417",
                text="Extracted protected content.",
                source_evidence=(evidence,),
            ),
        )
    )

    location = clause.content[0].source_evidence[0]
    assert location.locator == "#/texts/417"
    assert location.page_number == 83
    assert location.bounding_box is not None
    assert location.bounding_box.right == 200.0


def test_clause_rejects_removed_legacy_text_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _clause(text="Legacy protected text.")


def test_clause_rejects_legacy_text_even_with_structured_content() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _clause(
            text="Legacy text must not replace content.",
            content=(TextBlock(id="canonical", text="Canonical content."),),
        )


def test_bounding_box_rejects_inverted_coordinates() -> None:
    with pytest.raises(ValidationError, match="right must be greater"):
        BoundingBox(left=20, top=10, right=10, bottom=30)
