from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    SemanticRole,
    Standard,
    StandardKey,
    StandardReference,
)


def test_create_standard_with_clause() -> None:
    clause = Clause(
        id=ClauseId(value="EN50716-2023-5.1"),
        reference=StandardReference(
            standard="EN 50716",
            year=2023,
            clause="5.1",
        ),
        clause_type=ClauseType.CLAUSE,
        title="Software safety integrity",
    )

    standard = Standard.from_name(
        key=StandardKey(value="EN50716"),
        name="EN 50716",
        year=2023,
        parent_key=None,
    ).model_copy(update={"clauses": (clause,)})

    assert standard.name == "EN 50716"
    assert standard.clauses[0].reference.as_text() == "EN 50716:2023 5.1"


def test_clause_model_is_json_serializable() -> None:
    clause = Clause(
        id=ClauseId(value="EN50716-2023-5.1"),
        reference=StandardReference(
            standard="EN 50716",
            year=2023,
            clause="5.1",
        ),
        clause_type=ClauseType.REQUIREMENT,
    )

    data = clause.model_dump()

    assert data["id"]["value"] == "EN50716-2023-5.1"
    assert data["clause_type"] == "requirement"


def test_clause_can_have_semantic_roles() -> None:
    clause = Clause(
        id=ClauseId(value="ISO26262-8-2018-6.5"),
        reference=StandardReference(
            standard="ISO 26262-8",
            year=2018,
            clause="6.5",
        ),
        clause_type=ClauseType.CLAUSE,
        semantic_roles=(SemanticRole.WORK_PRODUCTS,),
        title="Work products",
    )

    assert clause.semantic_roles == (SemanticRole.WORK_PRODUCTS,)

    data = clause.model_dump(mode="json")

    assert data["semantic_roles"] == ["work_products"]
