from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.adapters.filesystem.normalized_table_repository import (
    FileSystemNormalizedTableRepository,
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
)


def test_exposes_reproducible_normalized_tables_from_documents(tmp_path) -> None:
    table = TableBlock(
        id="table-1",
        rows=(TableRow(cells=(TableCell(text="Name", is_header=True),)),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="c1"),
                reference=StandardReference(standard="DOC", clause="1"),
                clause_type=ClauseType.CLAUSE,
                content=(table,),
            ),
        ),
    )
    FileSystemEngineeringDocumentRepository(tmp_path).save(document)

    repository = FileSystemNormalizedTableRepository(tmp_path)
    tables = repository.list_tables(("DOC",))

    assert len(tables) == 1
    assert repository.get_table(tables[0].id) == tables[0]
