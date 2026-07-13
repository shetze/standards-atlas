from standards_atlas.adapters.atlasdata.toc_generator import generate_toc_records
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def test_generate_toc_records_from_document_clauses() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="Example",
                    year=2025,
                    clause="1",
                ),
                clause_type=ClauseType.TOC,
                title="Scope",
            ),
        ),
    )

    records = generate_toc_records(document)

    assert len(records) == 1
    assert records[0].kind == "TOC"
    assert records[0].reference == "Example:2025 1"
    assert records[0].content == "Scope"


def test_generate_toc_records_uses_clause_type_marker() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="Example",
                    year=2025,
                    clause="5.1.1",
                ),
                clause_type=ClauseType.REQUIREMENT,
            ),
        ),
    )

    records = generate_toc_records(document)

    assert records[0].type_marker == "r"
    assert records[0].content == "Requirement"


def test_generate_toc_records_preserves_existing_clause_title() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="Example",
                    year=2025,
                    clause="1",
                ),
                clause_type=ClauseType.SCOPE,
                title="Actual scope title",
            ),
        ),
    )

    records = generate_toc_records(document)

    assert records[0].type_marker == "s"
    assert records[0].content == "Actual scope title"
