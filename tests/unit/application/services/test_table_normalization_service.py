from standards_atlas.application.services.table_normalization_service import (
    TableNormalizationService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentTable,
    DocumentTableId,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
)


def _document(table: TableBlock) -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="clause-a"),
        reference=StandardReference(standard="IEC61508-3", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    structural = DocumentTable(
        id=DocumentTableId(value="table:a1"),
        reference="A.1",
        title="Techniques and measures",
        parent_clause_id=clause.id,
        parent_clause_reference="A",
        sequence_index=0,
        table_block_id=table.id,
    )
    return EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="IEC 61508-3",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
        tables=(structural,),
    )


def test_reconstructs_merged_header_grid_and_column_paths() -> None:
    table = TableBlock(
        id="table-a1",
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Technique", row_span=2, is_header=True),
                    TableCell(text="Recommendation", column_span=2, is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="SIL 1", is_header=True),
                    TableCell(text="SIL 2", is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="Static analysis"),
                    TableCell(text="R"),
                    TableCell(text="HR"),
                )
            ),
        ),
    )

    normalized = TableNormalizationService().normalize_document(_document(table))[0]

    assert normalized.width == 3
    assert normalized.height == 3
    assert normalized.header_row_count == 2
    assert normalized.columns[0].header_path == ("Technique",)
    assert normalized.columns[1].header_path == ("Recommendation", "SIL 1")
    assert normalized.columns[2].header_path == ("Recommendation", "SIL 2")
    assert normalized.rows[2].kind == "data"
    assert normalized.rows[0].cells[1].column_span == 2


def test_extracts_units_footnotes_and_reference_tokens_without_semantics() -> None:
    table = TableBlock(
        id="timing",
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Parameter", is_header=True),
                    TableCell(text="Time [ms]", is_header=True),
                )
            ),
            TableRow(cells=(TableCell(text="Delay"), TableCell(text="10; see Clause 7.4.2"))),
            TableRow(cells=(TableCell(text="NOTE: See Table A.2", column_span=2),)),
        ),
    )

    normalized = TableNormalizationService().normalize_document(_document(table))[0]

    assert normalized.columns[1].unit == "ms"
    assert normalized.rows[2].kind == "footnote"
    assert normalized.footnotes[0].marker == "NOTE"
    assert normalized.footnotes[0].text == "See Table A.2"
    assert {(item.kind, item.text) for item in normalized.references} == {
        ("clause", "Clause 7.4.2"),
        ("table", "Table A.2"),
    }


def test_carries_spanning_row_headers_into_row_header_path() -> None:
    table = TableBlock(
        id="rows",
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Group", is_header=True),
                    TableCell(text="Item", is_header=True),
                    TableCell(text="Value", is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="A", row_span=2, is_header=True),
                    TableCell(text="one", is_header=True),
                    TableCell(text="1"),
                )
            ),
            TableRow(cells=(TableCell(text="two", is_header=True), TableCell(text="2"))),
        ),
    )

    normalized = TableNormalizationService().normalize_document(_document(table))[0]

    assert normalized.rows[1].header_path == ("A", "one")
    assert normalized.rows[2].header_path == ("A", "two")
