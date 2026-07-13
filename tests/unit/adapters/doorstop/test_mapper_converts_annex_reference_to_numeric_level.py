from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)
from standards_atlas.adapters.doorstop.item_mapper import DoorstopItemMapper
from standards_atlas.adapters.doorstop.id_generator import DoorstopIdContext
from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopItemAttributes,
    DoorstopReference,
)

def test_mapper_converts_annex_reference_to_numeric_level() -> None:
    clause = Clause(
        id=ClauseId(value="annex-a"),
        reference=StandardReference(
            standard="EN 50716",
            year=2023,
            clause="A.1",
        ),
        clause_type=ClauseType.CLAUSE,
        title="Annex clause",
    )

    document = EngineeringDocument(
        key=DocumentKey(value="EN50716"),
        title="EN 50716",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )

    mapper = DoorstopItemMapper(
        prefix="EN50716",
        separator="-",
        id_context=DoorstopIdContext(digits=8),
    )

    item = mapper.map_document(document)[0]

    assert item.uid == "EN50716-10010000"
    assert item.level == "10.1"
