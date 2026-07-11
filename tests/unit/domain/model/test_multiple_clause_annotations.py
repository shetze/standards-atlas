from standards_atlas.domain.model.identifiers import (
    AnnotationId,
    ClauseId,
    DocumentKey,
    StandardKey,
    StandardReference,
)
from standards_atlas.domain.model.annotation import (
    AnnotationType,
    AnnotationVisibility,
    ClauseAnnotation,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)


def test_engineering_document_supports_multiple_clause_annotations() -> None:
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(
            standard="Example",
            year=2025,
            clause="1.1",
        ),
        clause_type=ClauseType.CLAUSE,
    )

    document = EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.OTHER,
        clauses=(clause,),
        annotations=(
            ClauseAnnotation(
                id=AnnotationId(value="annotation-title"),
                clause_id=clause.id,
                annotation_type=AnnotationType.TITLE,
                visibility=AnnotationVisibility.PUBLIC,
                content="Generated clause title",
            ),
            ClauseAnnotation(
                id=AnnotationId(value="annotation-summary"),
                clause_id=clause.id,
                annotation_type=AnnotationType.SUMMARY,
                visibility=AnnotationVisibility.LOCAL,
                content="Internal summary",
            ),
        ),
    )

    assert len(document.annotations_for_clause(clause.id)) == 2
