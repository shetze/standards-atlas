from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
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

    standard = Standard(
        key=StandardKey(value="EN50716"),
        name="EN 50716",
        year=2023,
        clauses=(clause,),
    )

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
