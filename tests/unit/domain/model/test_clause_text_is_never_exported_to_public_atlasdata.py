from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)
from standards_atlas.adapters.atlasdata.toc_generator import (
    generate_public_initialization_records,
)


def test_clause_text_is_never_exported_to_public_atlasdata() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(
            standard="Example",
            year=2025,
            clause="5.1",
        ),
        clause_type=ClauseType.REQUIREMENT,
        text="Protected source text that must not be published.",
    )

    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
    )

    records = generate_public_initialization_records(document)

    assert all(
        "Protected source text" not in record.content
        for record in records
    )
