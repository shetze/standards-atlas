from standards_atlas.adapters.atlasdata.toc_generator import (
    generate_public_text_records,
    generate_toc_records,
)
from standards_atlas.domain.model import (
    AnnotationId,
    AnnotationType,
    AnnotationVisibility,
    Clause,
    ClauseAnnotation,
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


def test_generate_toc_records_preserves_simple_volume_in_reference() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508"),
        title="IEC 61508",
        document_type=DocumentType.STANDARD,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="IEC 61508",
                    year=2005,
                    clause="1",
                ),
                clause_type=ClauseType.TOC,
                title="Scope",
                volume="0",
            ),
        ),
    )

    records = generate_toc_records(document)

    assert records[0].reference == "IEC 61508-0:2005 1"
    assert records[0].hash_value == "60dd0d2143028c31cfaa4f6724e2e85d"


def test_generate_toc_records_serializes_nested_volume_with_hyphens() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508-3-1"),
        title="IEC 61508-3-1",
        document_type=DocumentType.STANDARD,
        clauses=(
            Clause(
                id=ClauseId(value="clause-1"),
                reference=StandardReference(
                    standard="IEC 61508",
                    year=2010,
                    clause="1",
                ),
                clause_type=ClauseType.TOC,
                title="Scope",
                volume="3§1",
            ),
        ),
    )

    records = generate_toc_records(document)

    assert records[0].reference == "IEC 61508-3-1:2010 1"


def test_generate_public_text_records_preserves_volume_in_reference() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(
            standard="IEC 61508",
            year=2010,
            clause="7.4.4",
        ),
        clause_type=ClauseType.REQUIREMENT,
        volume="3§1",
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508-3-1"),
        title="IEC 61508-3-1",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
        annotations=(
            ClauseAnnotation(
                id=AnnotationId(value="annotation-1"),
                clause_id=clause.id,
                annotation_type=AnnotationType.COMMENT,
                visibility=AnnotationVisibility.PUBLIC,
                content="Public comment",
            ),
        ),
    )

    records = generate_public_text_records(document)

    assert records[0].reference == "IEC 61508-3-1:2010 7.4.4"
