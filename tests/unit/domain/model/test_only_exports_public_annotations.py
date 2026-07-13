from standards_atlas.adapters.atlasdata.toc_generator import (
    generate_public_text_records,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseType,
    DocumentType,
    EngineeringDocument,
)
from standards_atlas.domain.model.annotation import (
    AnnotationType,
    AnnotationVisibility,
    ClauseAnnotation,
)
from standards_atlas.domain.model.identifiers import (
    AnnotationId,
    ClauseId,
    DocumentKey,
    StandardReference,
)


def test_generate_public_text_records_only_exports_public_annotations() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(
            standard="Example",
            year=2025,
            clause="5.1",
        ),
        clause_type=ClauseType.REQUIREMENT,
        text="Copyright-protected standard text",
    )

    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
        annotations=(
            ClauseAnnotation(
                id=AnnotationId(value="public-summary"),
                clause_id=clause.id,
                annotation_type=AnnotationType.SUMMARY,
                visibility=AnnotationVisibility.PUBLIC,
                content="Publicly authored summary.",
            ),
            ClauseAnnotation(
                id=AnnotationId(value="local-comment"),
                clause_id=clause.id,
                annotation_type=AnnotationType.COMMENT,
                visibility=AnnotationVisibility.LOCAL,
                content="Internal comment.",
            ),
            ClauseAnnotation(
                id=AnnotationId(value="private-note"),
                clause_id=clause.id,
                annotation_type=AnnotationType.NOTE,
                visibility=AnnotationVisibility.PRIVATE,
                content="Private note.",
            ),
        ),
    )

    records = generate_public_text_records(document)

    assert len(records) == 1
    assert records[0].kind == "PublicTXT"
    assert records[0].content == "Publicly authored summary."

    rendered = "\n".join(record.content for record in records)

    assert "Copyright-protected standard text" not in rendered
    assert "Internal comment" not in rendered
    assert "Private note" not in rendered
