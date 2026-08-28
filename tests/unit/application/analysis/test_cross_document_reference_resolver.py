from standards_atlas.application.analysis import (
    resolve_cross_document_reference_relations,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    RelationScope,
    Standard,
    StandardKey,
    StandardReference,
    TextBlock,
)


def test_resolves_explicit_reference_to_available_document() -> None:
    source = _document(
        "ISO26262-5",
        "ISO 26262-5",
        (_clause("source", "ISO 26262-5", "7.1", "See ISO 26262-6:2018, 7.4.5."),),
    )
    target = _document(
        "ISO26262-6",
        "ISO 26262-6",
        (_clause("target", "ISO 26262-6", "7.4.5", "Target."),),
    )

    resolved = resolve_cross_document_reference_relations(source, (source, target))

    relation = resolved.clauses[0].reference_relations[0]
    assert relation.scope is RelationScope.EXTERNAL
    assert relation.target_document_key == "ISO26262-6"
    assert relation.target_clause_id == "target"
    assert relation.target_reference == "7.4.5"
    assert relation.display_text == "ISO 26262-6:2018, 7.4.5"


def test_does_not_resolve_ambiguous_target_reference() -> None:
    source = _document(
        "SOURCE",
        "Source",
        (_clause("source", "SOURCE", "1.1", "See TARGET, 7.4.5."),),
    )
    target = _document(
        "TARGET",
        "Target",
        (
            _clause("first", "TARGET", "7.4.5", "First."),
            _clause("second", "TARGET", "7.4.5", "Second."),
        ),
    )

    resolved = resolve_cross_document_reference_relations(source, (source, target))

    assert resolved.clauses[0].reference_relations == ()


def _document(key: str, name: str, clauses: tuple[Clause, ...]) -> Standard:
    document = Standard.from_name(key=StandardKey(value=key), name=name, year=2018)
    return document.model_copy(update={"clauses": clauses})


def _clause(identifier: str, standard: str, reference: str, text: str) -> Clause:
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard=standard, year=2018, clause=reference),
        clause_type=ClauseType.CLAUSE,
        heading="Clause",
        content=(TextBlock(id=f"{identifier}-text", text=text),),
    )


def test_part_qualified_alias_selects_matching_part_in_family_document() -> None:
    source = _document(
        "SOURCE",
        "Source",
        (_clause("source", "SOURCE", "1.1", "See IEC 61508-3:2010, 7.4.5."),),
    )
    target_p2 = Clause(
        id=ClauseId(value="p2"),
        reference=StandardReference(standard="IEC 61508", part="2", year=2010, clause="7.4.5"),
        clause_type=ClauseType.CLAUSE,
        heading="Part 2",
    )
    target_p3 = Clause(
        id=ClauseId(value="p3"),
        reference=StandardReference(standard="IEC 61508", part="3", year=2010, clause="7.4.5"),
        clause_type=ClauseType.CLAUSE,
        heading="Part 3",
    )
    family = _document("IEC61508", "IEC 61508", (target_p2, target_p3))

    resolved = resolve_cross_document_reference_relations(source, (source, family))

    relation = resolved.clauses[0].reference_relations[0]
    assert relation.target_clause_id == "p3"
