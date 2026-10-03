from standards_atlas.adapters.evaluation.engineering_document_clause_provider import (
    EngineeringDocumentClauseProvider,
)
from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def _document_with(clause: Clause) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def test_marks_clause_as_table_dominant_from_structured_content() -> None:
    rows = tuple(
        TableRow(cells=(TableCell(text=f"Technique {index}"), TableCell(text="HR")))
        for index in range(30)
    )
    clause = Clause(
        id=ClauseId(value="DOC:A"),
        reference=StandardReference(standard="DOC", clause="A"),
        clause_type=ClauseType.CLAUSE,
        content=(
            TextBlock(id="intro", text="Selection guidance."),
            TableBlock(id="table", caption="Techniques", rows=rows),
        ),
    )

    descriptor = EngineeringDocumentClauseProvider._clause_descriptor(
        _document_with(clause), clause
    )

    assert descriptor.content_profile is ClauseContentProfile.TABLE_DOMINANT
    assert descriptor.table_block_count == 1
    assert descriptor.table_text_length >= 200
    assert descriptor.non_table_text_length == len("Selection guidance.")


def test_keeps_small_incidental_table_as_text_dominant() -> None:
    clause = Clause(
        id=ClauseId(value="DOC:1"),
        reference=StandardReference(standard="DOC", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(
            TextBlock(id="text", text="The supplier shall document the result." * 10),
            TableBlock(
                id="table",
                rows=(TableRow(cells=(TableCell(text="A"), TableCell(text="B"))),),
            ),
        ),
    )

    descriptor = EngineeringDocumentClauseProvider._clause_descriptor(
        _document_with(clause), clause
    )

    assert descriptor.content_profile is ClauseContentProfile.TEXT_DOMINANT


def test_exact_batch_clause_lookup_preserves_order_and_document_boundary(
    tmp_path, monkeypatch
) -> None:
    from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository

    def clause(clause_id: str) -> Clause:
        return Clause(
            id=ClauseId(value=clause_id),
            reference=StandardReference(standard="DOC", clause=clause_id.rsplit(":", 1)[-1]),
            clause_type=ClauseType.CLAUSE,
            content=(TextBlock(id=f"text-{clause_id}", text=f"Text {clause_id}"),),
        )

    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="DOC"),
            title="Document",
            document_type=DocumentType.OTHER,
            clauses=(clause("DOC:A"), clause("DOC:B"), clause("DOC:C")),
        )
    )
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="HIDDEN"),
            title="Hidden",
            document_type=DocumentType.OTHER,
            clauses=(clause("HIDDEN:X"),),
        )
    )
    provider = EngineeringDocumentClauseProvider(tmp_path)
    loads: list[str] = []
    original_load = provider._repository.load

    def counted_load(key):
        loads.append(key.value)
        return original_load(key)

    monkeypatch.setattr(provider._repository, "load", counted_load)
    monkeypatch.setattr(
        provider._repository,
        "list",
        lambda: (_ for _ in ()).throw(AssertionError("bounded lookup must not list the corpus")),
    )

    descriptors = provider.get_clauses(("DOC:C", "DOC:A"), document_keys=("DOC",))
    documents = provider.get_documents(("DOC",))

    assert [item.id for item in descriptors] == ["DOC:C", "DOC:A"]
    assert [item.key for item in documents] == ["DOC"]
    assert loads == ["DOC", "DOC"]
