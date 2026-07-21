from standards_atlas.adapters.doorstop.id_generator import DoorstopIdContext
from standards_atlas.adapters.doorstop.item_mapper import DoorstopItemMapper
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
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


def test_mapper_nests_part_clauses_below_part_root() -> None:
    root = Clause(
        id=ClauseId(value="part-root"),
        reference=StandardReference(standard="IEC 61508", clause="0"),
        clause_type=ClauseType.TOC,
        title="IEC 61508-1",
        volume="1",
    )
    scope = Clause(
        id=ClauseId(value="scope"),
        reference=StandardReference(standard="IEC 61508", clause="1"),
        clause_type=ClauseType.SCOPE,
        title="Scope",
        volume="1",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508"),
        title="IEC 61508",
        document_type=DocumentType.STANDARD,
        clauses=(root, scope),
    )
    mapper = DoorstopItemMapper(
        prefix="IEC61508",
        separator="-",
        id_context=DoorstopIdContext(digits=8),
    )

    root_item, scope_item = mapper.map_document(document)

    assert root_item.level == "1"
    assert root_item.header == "IEC 61508-1"
    assert scope_item.level == "1.1"


def test_mapper_gives_supplement_a_distinct_root_level() -> None:
    supplement = Clause(
        id=ClauseId(value="supplement-root"),
        reference=StandardReference(standard="IEC 61508", clause="0"),
        clause_type=ClauseType.TOC,
        title="IEC 61508-3-1",
        volume="3§1",
    )
    clause = Clause(
        id=ClauseId(value="supplement-scope"),
        reference=StandardReference(standard="IEC 61508", clause="1"),
        clause_type=ClauseType.SCOPE,
        volume="3§1",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508"),
        title="IEC 61508",
        document_type=DocumentType.STANDARD,
        clauses=(supplement, clause),
    )
    mapper = DoorstopItemMapper(
        prefix="IEC61508",
        separator="-",
        id_context=DoorstopIdContext(digits=12, part_shift=1),
    )

    root_item, scope_item = mapper.map_document(document)

    assert root_item.level == "401"
    assert scope_item.level == "401.1"


def test_mapper_qualifies_clause_identifiers_with_part() -> None:
    clause = Clause(
        id=ClauseId(value="part-clause"),
        reference=StandardReference(
            standard="IEC 61508",
            year=2010,
            clause="7.4.2",
        ),
        clause_type=ClauseType.REQUIREMENT,
        volume="3§1",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508"),
        title="IEC 61508",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )
    mapper = DoorstopItemMapper(
        prefix="IEC61508",
        separator="-",
        id_context=DoorstopIdContext(digits=12, part_shift=1),
    )

    item = mapper.map_document(document)[0]

    expected = "IEC 61508-3-1:2010 7.4.2"
    assert item.attributes["idx"] == expected
    assert item.attributes["atlas-reference"] == expected
    assert item.references[0].keyword == expected
