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


def test_mark_generated_upserts_same_path_with_latest_provenance() -> None:
    clause = _clause().mark_generated(
        GeneratedAttribute(
            path="baseline.structural_context",
            generator="old-generator",
            method=GenerationMethod.DETERMINISTIC,
        )
    )

    updated = clause.mark_generated(
        GeneratedAttribute(
            path="baseline.structural_context",
            generator="new-generator",
            method=GenerationMethod.DETERMINISTIC,
            evidence=("clause:c1",),
        )
    )

    assert len(updated.provenance.generated_attributes) == 1
    generated = updated.provenance.generated_attributes[0]
    assert generated.generator == "new-generator"
    assert generated.evidence == ("clause:c1",)


def test_confirm_authoritative_only_removes_confirmed_generated_path() -> None:
    clause = _clause().mark_generated(
        GeneratedAttribute(
            path="baseline.structural_context",
            generator="structural-taxonomy",
            method=GenerationMethod.DETERMINISTIC,
        ),
        GeneratedAttribute(
            path="enrichments.semantic.statement_functions",
            generator="semantic-profile-classification/2.4.0",
            method=GenerationMethod.LLM,
        ),
    )

    confirmed = clause.confirm_authoritative("baseline.structural_context")

    assert [item.path for item in confirmed.provenance.generated_attributes] == [
        "enrichments.semantic.statement_functions"
    ]
