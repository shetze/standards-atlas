from standards_atlas.application.analysis import resolve_internal_reference_relations
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    RelationScope,
    SemanticRelationKind,
    Standard,
    StandardKey,
    StandardReference,
    TextBlock,
)


def _clause(reference: str, text: str = "") -> Clause:
    return Clause(
        id=ClauseId(value=f"clause-{reference.replace('.', '-')}"),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=ClauseType.CLAUSE,
        title=f"Clause {reference}",
        content=(TextBlock(id=f"text-{reference}", text=text),) if text else (),
    )


def test_resolves_same_document_clause_references() -> None:
    source = _clause("5.1", "The procedure in 5.2 shall be applied.")
    target = _clause("5.2")
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(update={"clauses": (source, target)})

    relations = resolve_internal_reference_relations(document)[source.id.value]

    assert len(relations) == 1
    assert relations[0].kind is SemanticRelationKind.REFERENCES
    assert relations[0].scope is RelationScope.INTERNAL
    assert relations[0].target_reference == "5.2"
    assert relations[0].target_clause_id == target.id.value
    assert relations[0].display_text == "5.2"


def test_ignores_unresolved_and_self_references() -> None:
    source = _clause("5.1", "See 5.1 and clause 9.9.")
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(update={"clauses": (source,)})

    assert resolve_internal_reference_relations(document)[source.id.value] == ()


def test_resolves_range_endpoints_without_linking_non_literal_targets() -> None:
    source = _clause("5.1", "Requirements 5.2 to 5.4 apply.")
    clauses = (source, _clause("5.2"), _clause("5.3"), _clause("5.4"))
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(update={"clauses": clauses})

    relations = resolve_internal_reference_relations(document)[source.id.value]

    assert [relation.display_text for relation in relations] == ["5.2", "5.4"]
