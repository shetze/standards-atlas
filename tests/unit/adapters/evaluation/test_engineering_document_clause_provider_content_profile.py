from standards_atlas.adapters.evaluation.engineering_document_clause_provider import (
    EngineeringDocumentClauseProvider,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def _document_with(clause: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_marks_clause_as_table_dominant_from_structured_content() -> None:
    rows = tuple(
        TableRow(cells=(TableCell(text=f"Technique {index}"), TableCell(text="HR")))
        for index in range(30)
    )
    clause = Clause(
        id=ClauseId(value="DOC:A"),
        reference=StandardReference(standard="DOC", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(
            TextBlock(id="intro", text="Selection guidance."),
            TableBlock(id="table", caption="Techniques", rows=rows),
        ),
    )

    descriptor = EngineeringDocumentClauseProvider._clause_descriptor(
        _document_with(clause), clause
    )

    assert descriptor.content_profile is ClauseContentProfile.TABLE_DOMINANT
    assert descriptor.table_block_count == 1
    assert descriptor.table_text_length >= 200
    assert descriptor.non_table_text_length == len("Selection guidance.")


def test_keeps_small_incidental_table_as_text_dominant() -> None:
    clause = Clause(
        id=ClauseId(value="DOC:1"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(
            TextBlock(id="text", text="The supplier shall document the result." * 10),
            TableBlock(
                id="table",
                rows=(TableRow(cells=(TableCell(text="A"), TableCell(text="B"))),),
            ),
        ),
    )

    descriptor = EngineeringDocumentClauseProvider._clause_descriptor(
        _document_with(clause), clause
    )

    assert descriptor.content_profile is ClauseContentProfile.TEXT_DOMINANT
