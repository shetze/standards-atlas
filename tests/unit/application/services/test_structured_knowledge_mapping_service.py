from standards_atlas.application.services.structured_knowledge_mapping_service import (
    StructuredKnowledgeMappingService,
)
from standards_atlas.domain.model import (
    NormalizedTable,
    NormalizedTableCell,
    NormalizedTableColumn,
    NormalizedTableRow,
    NormalizedTableRowKind,
)


def test_maps_portable_matrix_from_normalized_header_paths() -> None:
    table = NormalizedTable(
        id="normalized-table:test",
        document_key="DOMAIN",
        reference="Table 1",
        parent_clause_id="clause-1",
        parent_clause_reference="DOMAIN 1",
        table_block_id="table-1",
        width=2,
        height=2,
        header_row_count=1,
        columns=(
            NormalizedTableColumn(
                index=0,
                header_path=("Process", "Activity"),
                label="Process / Activity",
            ),
            NormalizedTableColumn(
                index=1,
                header_path=("Output", "Work product"),
                label="Output / Work product",
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
                    NormalizedTableCell(row_index=1, column_index=1, text="Review report"),
                ),
            ),
        ),
    )

    mapped = StructuredKnowledgeMappingService().map_table(table)

    assert mapped.kind == "work_product_matrix"
    semantic = mapped.records[1].structured_knowledge
    assert semantic is not None
    assert semantic.relations[0].kind == "produces"
    assert semantic.concepts[0].source_header == "Process / Activity"
    assert semantic.concepts[1].source_header == "Output / Work product"


def test_unknown_normalized_table_stays_generic() -> None:
    table = NormalizedTable(
        id="normalized-table:generic",
        document_key="DOMAIN",
        reference="Table 2",
        parent_clause_id="clause-2",
        parent_clause_reference="DOMAIN 2",
        table_block_id="table-2",
        width=2,
        height=2,
        header_row_count=1,
        columns=(
            NormalizedTableColumn(index=0, header_path=("Name",), label="Name"),
            NormalizedTableColumn(index=1, header_path=("Comment",), label="Comment"),
        ),
        rows=(
            NormalizedTableRow(
                index=0,
                kind=NormalizedTableRowKind.HEADER,
                cells=(
                    NormalizedTableCell(row_index=0, column_index=0, text="Name", is_header=True),
                    NormalizedTableCell(
                        row_index=0, column_index=1, text="Comment", is_header=True
                    ),
                ),
            ),
            NormalizedTableRow(
                index=1,
                kind=NormalizedTableRowKind.DATA,
                cells=(
                    NormalizedTableCell(row_index=1, column_index=0, text="Alpha"),
                    NormalizedTableCell(row_index=1, column_index=1, text="Example"),
                ),
            ),
        ),
    )

    mapped = StructuredKnowledgeMappingService().map_table(table)

    assert mapped.kind == "generic"
    assert mapped.records[1].structured_knowledge is None


def test_structured_knowledge_rejects_unknown_relation_endpoint() -> None:
    from pydantic import ValidationError

    from standards_atlas.domain.model import (
        KnowledgeConcept,
        KnowledgeConceptKind,
        KnowledgeRelation,
        KnowledgeRelationKind,
        StructuredKnowledgeRecord,
    )

    try:
        StructuredKnowledgeRecord(
            concepts=(
                KnowledgeConcept(
                    id="concept:a",
                    kind=KnowledgeConceptKind.SUBJECT,
                    label="A",
                    source_column_index=0,
                ),
            ),
            relations=(
                KnowledgeRelation(
                    kind=KnowledgeRelationKind.TRACES_TO,
                    source_concept_id="concept:a",
                    target_concept_id="concept:missing",
                ),
            ),
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("unknown relation endpoint must be rejected")
