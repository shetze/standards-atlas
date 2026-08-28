from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    GeneratedAttribute,
    GenerationMethod,
    SemanticClassification,
    StandardReference,
    StatementFunction,
)


def _clause() -> Clause:
    return Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="EXAMPLE", year=2026, clause="1"),
        clause_type=ClauseType.CLAUSE,
        heading="Scope",
    )


def test_clause_serializes_baseline_and_enrichment_as_distinct_blocks() -> None:
    clause = _clause().with_semantic_classification(
        SemanticClassification(statement_functions=(StatementFunction.REQUIREMENT,))
    )

    payload = clause.model_dump(mode="json")

    assert payload["baseline"]["heading"] == "Scope"
    assert payload["enrichments"]["semantic"]["statement_functions"] == ["requirement"]
    assert "semantic_classification" not in payload
    assert "heading" not in payload


def test_generated_attribute_can_be_confirmed_authoritative() -> None:
    clause = _clause().mark_generated(
        GeneratedAttribute(
            path="baseline.structural_context",
            generator="structural-taxonomy",
            method=GenerationMethod.DETERMINISTIC,
        )
    )
    assert clause.provenance.generated_attributes[0].path == "baseline.structural_context"

    confirmed = clause.confirm_authoritative("baseline.structural_context")

    assert confirmed.provenance.generated_attributes == ()
