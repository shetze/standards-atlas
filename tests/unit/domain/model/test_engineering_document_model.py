from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)


def test_create_generic_engineering_document_with_virtual_clause() -> None:
    clause = Clause(
        id=ClauseId(value="AT-ARCH-2.3.1"),
        reference=StandardReference(
            standard="AT System Architecture Specification",
            year=2024,
            clause="2.3.1",
        ),
        clause_type=ClauseType.CLAUSE,
        title="System Element ODS",
        content=(
            TextBlock(
                id="AT-ARCH-2.3.1-text",
                text=(
                    "The object detection system perceives the environment "
                    "in front of the train unit."
                ),
            ),
        ),
    )

    document = EngineeringDocument(
        key=DocumentKey(value="AT-SYSTEM-ARCHITECTURE-SPEC"),
        title="AT System Architecture Specification",
        document_type=DocumentType.SPECIFICATION,
        year=2024,
        version="2.0",
        clauses=(clause,),
    )

    assert document.title == "AT System Architecture Specification"
    assert document.document_type == DocumentType.SPECIFICATION
    assert document.clauses[0].title == "System Element ODS"


def test_engineering_document_is_json_serializable() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="AT-SAFETY-APPORTIONMENT"),
        title="AT System Safety Requirements Apportionment Report",
        document_type=DocumentType.REPORT,
        version="1.0",
    )

    data = document.model_dump(mode="json")

    assert data["key"]["value"] == "AT-SAFETY-APPORTIONMENT"
    assert data["document_type"] == "report"
