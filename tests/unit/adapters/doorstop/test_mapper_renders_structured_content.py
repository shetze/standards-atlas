from standards_atlas.adapters.doorstop.id_generator import DoorstopIdContext
from standards_atlas.adapters.doorstop.item_mapper import DoorstopItemMapper
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ListBlock,
    ListItem,
    StandardReference,
    TextBlock,
)


def test_mapper_renders_structured_clause_content_as_text() -> None:
    clause = Clause(
        id=ClauseId(value="example-5.1"),
        reference=StandardReference(standard="Example", year=2026, clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(
            TextBlock(id="text-1", text="The supplier shall provide evidence."),
            ListBlock(
                id="list-1",
                items=(ListItem(text="analysis"), ListItem(text="test report")),
            ),
        ),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
    )
    mapper = DoorstopItemMapper(
        prefix="EX",
        separator="-",
        id_context=DoorstopIdContext(digits=8),
    )

    item = mapper.map_document(document)[0]

    assert item.text == ("The supplier shall provide evidence.\n\n- analysis\n- test report")
