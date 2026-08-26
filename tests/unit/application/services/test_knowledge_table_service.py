from standards_atlas.application.services.knowledge_table_service import (
    KnowledgeTableProjectionService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    NoteBlock,
    SourceEvidence,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
)


def _document() -> EngineeringDocument:
    evidence = SourceEvidence(
        source_id="source.pdf",
        source_type="pdf",
        locator="/private/source.pdf",
        page_number=7,
    )
    table = TableBlock(
        id="table-a1",
        caption="Table A.1 — Selection of techniques",
        source_evidence=(evidence,),
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Technique", is_header=True),
                    TableCell(text="SIL 1", is_header=True),
                )
            ),
            TableRow(cells=(TableCell(text="Formal methods"), TableCell(text="R"))),
        ),
    )
    clause = Clause(
        id=ClauseId(value="iec61508-3-a"),
        reference=StandardReference(standard="IEC61508-3", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(NoteBlock(id="note", note_kind="NOTE", content=(table,)),),
    )
    return EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="IEC 61508-3",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_projects_nested_tables_and_lossless_records_with_stable_ids() -> None:
    service = KnowledgeTableProjectionService()

    first = service.project_document(_document())
    second = service.project_document(_document())

    assert first == second
    assert len(first) == 1
    table = first[0]
    assert table.reference == "Table A.1"
    assert table.table_block_id == "table-a1"
    assert table.header_rows == (("Technique", "SIL 1"),)
    assert table.records[1].plain_text == "Formal methods | R"
    assert table.records[1].source.row_index == 1
    assert table.records[1].source.source_evidence[0].page_number == 7
    assert table.records[1].id.value == f"{table.id.value}:row:2"


def test_interprets_iec61508_technique_recommendation_matrix() -> None:
    evidence = SourceEvidence(
        source_id="source.pdf",
        source_type="pdf",
        locator="/private/source.pdf",
        page_number=8,
    )
    table = TableBlock(
        id="table-a2",
        caption="Table A.2 — Software architecture design (see 7.4.3)",
        source_evidence=(evidence,),
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Ref", is_header=True),
                    TableCell(text="Technique/measure", is_header=True),
                    TableCell(text="See IEC 61508-7", is_header=True),
                    TableCell(text="SIL 1", is_header=True),
                    TableCell(text="SIL 2", is_header=True),
                    TableCell(text="SIL 3", is_header=True),
                    TableCell(text="SIL 4", is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="1b"),
                    TableCell(text="Formal methods"),
                    TableCell(text="B.2.2, C.2.4"),
                    TableCell(text="—"),
                    TableCell(text="R"),
                    TableCell(text="R"),
                    TableCell(text="HR"),
                )
            ),
        ),
    )
    clause = Clause(
        id=ClauseId(value="iec61508-3-a"),
        reference=StandardReference(standard="IEC61508-3", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="IEC 61508-3",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )

    projected = KnowledgeTableProjectionService().project_document(document)[0]

    assert projected.kind == "technique_recommendation_matrix"
    assert projected.context_references == ("IEC61508-3:7.4.3",)
    semantic = projected.records[1].technique_recommendation
    assert semantic is not None
    assert semantic.local_identifier == "1b"
    assert semantic.alternative_group == "1"
    assert semantic.technique == "Formal methods"
    assert semantic.description_references == ("IEC61508-7:B.2.2", "IEC61508-7:C.2.4")
    assert [item.level.value for item in semantic.recommendations] == [
        "neutral",
        "recommended",
        "recommended",
        "highly_recommended",
    ]


def test_does_not_interpret_similar_table_from_another_document() -> None:
    document = _document().model_copy(update={"key": DocumentKey(value="OTHER")})

    table = KnowledgeTableProjectionService().project_document(document)[0]

    assert table.kind == "generic"
    assert all(record.technique_recommendation is None for record in table.records)


def _matrix_document(headers: tuple[str, str], values: tuple[str, str]) -> EngineeringDocument:
    table = TableBlock(
        id="portable-matrix",
        caption="Structured knowledge matrix",
        rows=(
            TableRow(cells=tuple(TableCell(text=value, is_header=True) for value in headers)),
            TableRow(cells=tuple(TableCell(text=value) for value in values)),
        ),
    )
    clause = Clause(
        id=ClauseId(value="matrix-clause"),
        reference=StandardReference(standard="DOMAIN", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    return EngineeringDocument(
        key=DocumentKey(value="DOMAIN"),
        title="Domain document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_projects_work_product_matrix_into_portable_ontology() -> None:
    table = KnowledgeTableProjectionService().project_document(
        _matrix_document(("Activity", "Work product"), ("Review", "Review report"))
    )[0]

    assert table.kind == "work_product_matrix"
    semantic = table.records[1].structured_knowledge
    assert semantic is not None
    assert [(concept.kind.value, concept.label) for concept in semantic.concepts] == [
        ("activity", "Review"),
        ("work_product", "Review report"),
    ]
    assert semantic.relations[0].kind == "produces"


def test_projects_responsibility_matrix_with_source_columns() -> None:
    table = KnowledgeTableProjectionService().project_document(
        _matrix_document(("Responsible role", "Task"), ("Safety manager", "Approve plan"))
    )[0]

    assert table.kind == "responsibility_matrix"
    semantic = table.records[1].structured_knowledge
    assert semantic is not None
    assert semantic.concepts[0].source_column_index == 0
    assert semantic.concepts[0].source_header == "Responsible role"
    assert semantic.relations[0].kind == "responsible_for"


def test_projects_traceability_matrix() -> None:
    table = KnowledgeTableProjectionService().project_document(
        _matrix_document(("Source requirement", "Target test"), ("REQ-1", "TEST-7"))
    )[0]

    assert table.kind == "traceability_matrix"
    semantic = table.records[1].structured_knowledge
    assert semantic is not None
    assert semantic.relations[0].kind == "traces_to"


def test_keeps_unknown_table_generic_without_invented_relations() -> None:
    table = KnowledgeTableProjectionService().project_document(
        _matrix_document(("Name", "Comment"), ("Alpha", "Example"))
    )[0]

    assert table.kind == "generic"
    assert table.records[1].structured_knowledge is None


def test_iec61508_recommendation_row_exposes_structured_knowledge() -> None:
    evidence = SourceEvidence(
        source_id="source.pdf",
        source_type="pdf",
        locator="/private/source.pdf",
        page_number=8,
    )
    table = TableBlock(
        id="table-a3",
        caption="Table A.3 — Techniques and measures (see 7.4.4)",
        source_evidence=(evidence,),
        rows=(
            TableRow(
                cells=(
                    TableCell(text="Technique/measure", is_header=True),
                    TableCell(text="SIL 1", is_header=True),
                    TableCell(text="SIL 2", is_header=True),
                )
            ),
            TableRow(
                cells=(
                    TableCell(text="Defensive programming"),
                    TableCell(text="R"),
                    TableCell(text="HR"),
                )
            ),
        ),
    )
    clause = Clause(
        id=ClauseId(value="iec61508-3-a3"),
        reference=StandardReference(standard="IEC61508-3", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(table,),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="IEC 61508-3",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )

    projected = KnowledgeTableProjectionService().project_document(document)[0]
    semantic = projected.records[1].structured_knowledge

    assert projected.normalized_table_id is not None
    assert projected.mapping_version == "1.0.0"
    assert semantic is not None
    assert [(item.kind.value, item.label) for item in semantic.concepts] == [
        ("technique_or_measure", "Defensive programming"),
        ("integrity_level", "SIL 1"),
        ("integrity_level", "SIL 2"),
    ]
    assert [(item.kind.value, item.qualifier) for item in semantic.relations] == [
        ("recommended_for", "recommended"),
        ("recommended_for", "highly_recommended"),
    ]
