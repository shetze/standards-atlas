from standards_atlas.application.services.structured_knowledge_mapping_service import (
    StructuredKnowledgeMappingService,
)
from standards_atlas.application.services.table_retrieval_projection_service import (
    TableRetrievalProjectionService,
)
from standards_atlas.domain.model import (
    NormalizedTable,
    NormalizedTableCell,
    NormalizedTableColumn,
    NormalizedTableRow,
    NormalizedTableRowKind,
    RetrievalDocumentKind,
    RetrievalTokenizationProfile,
)


def _work_product_table() -> NormalizedTable:
    return NormalizedTable(
        id="normalized-table:test",
        document_key="DOMAIN",
        reference="Table 1",
        title="Work products",
        parent_clause_id="clause-1",
        parent_clause_reference="DOMAIN 1",
        table_block_id="table-1",
        width=2,
        height=2,
        header_row_count=1,
        columns=(
            NormalizedTableColumn(index=0, header_path=("Activity",), label="Activity"),
            NormalizedTableColumn(
                index=1,
                header_path=("Work product",),
                label="Work product",
            ),
        ),
        rows=(
            NormalizedTableRow(
                index=0,
                kind=NormalizedTableRowKind.HEADER,
                cells=(
                    NormalizedTableCell(
                        row_index=0,
                        column_index=0,
                        text="Activity",
                        is_header=True,
                    ),
                    NormalizedTableCell(
                        row_index=0,
                        column_index=1,
                        text="Work product",
                        is_header=True,
                    ),
                ),
            ),
            NormalizedTableRow(
                index=1,
                kind=NormalizedTableRowKind.DATA,
                cells=(
                    NormalizedTableCell(row_index=1, column_index=0, text="Review"),
                    NormalizedTableCell(
                        row_index=1,
                        column_index=1,
                        text="Review report",
                    ),
                ),
            ),
        ),
    )


def test_projects_table_row_concepts_and_relation_with_table_profile() -> None:
    knowledge = StructuredKnowledgeMappingService().map_table(_work_product_table())

    projection = TableRetrievalProjectionService().project_table(knowledge)

    kinds = [document.kind for document in projection.documents]
    assert kinds == [
        RetrievalDocumentKind.TABLE,
        RetrievalDocumentKind.ROW,
        RetrievalDocumentKind.CONCEPT,
        RetrievalDocumentKind.CONCEPT,
        RetrievalDocumentKind.RELATION,
    ]
    assert all(
        document.tokenization_profile is RetrievalTokenizationProfile.STRUCTURED_TABLE_V1
        for document in projection.documents
    )
    row = projection.documents[1]
    assert "Activity: Review" in row.text
    assert "Work product: Review report" in row.text
    relation = projection.documents[-1]
    assert "Review produces Review report" in relation.text


def test_projection_ids_and_text_are_deterministic() -> None:
    knowledge = StructuredKnowledgeMappingService().map_table(_work_product_table())
    service = TableRetrievalProjectionService()

    first = service.project_table(knowledge)
    second = service.project_table(knowledge)

    assert first == second
    assert len({document.id for document in first.documents}) == len(first.documents)
