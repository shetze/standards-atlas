from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentProvider,
)
from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.application.services import MarkdownExportService
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    Standard,
    StandardKey,
    StandardReference,
    TextBlock,
)


def test_exports_multi_part_standard_to_separate_files(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    document = Standard.from_name(key=StandardKey(value="IEC11889"), name="IEC 11889", year=2015)
    document = document.model_copy(
        update={
            "clauses": (
                _clause("p1", "1", "1", "Part one"),
                _clause("p2", "2", "1", "Part two"),
            )
        }
    )
    repository.save(document)

    result = MarkdownExportService(
        MarkdownExporter(), FileSystemPublicationDocumentProvider(repository)
    ).export("IEC11889", tmp_path / "markdown")

    assert [path.name for path in result.generated_files] == ["IEC11889-1.md", "IEC11889-2.md"]
    assert "Part one" in result.generated_files[0].read_text()
    assert "Part two" not in result.generated_files[0].read_text()
    assert result.clauses_exported == 2


def test_exports_single_part_document_to_one_file(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    document = Standard.from_name(key=StandardKey(value="EN50716"), name="EN 50716", year=2023)
    document = document.model_copy(update={"clauses": (_clause("c1", None, "1", "Scope"),)})
    repository.save(document)

    result = MarkdownExportService(
        MarkdownExporter(), FileSystemPublicationDocumentProvider(repository)
    ).export("EN50716", tmp_path / "markdown")

    assert [path.name for path in result.generated_files] == ["EN50716.md"]


def _clause(identifier: str, volume: str | None, reference: str, text: str) -> Clause:
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="IEC 11889", year=2015, clause=reference, part=volume),
        clause_type=ClauseType.CLAUSE,
        heading="Scope",
        content=(TextBlock(id=f"{identifier}-text", text=text),),
    )


def test_links_clause_in_another_exported_document(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    source = Standard.from_name(
        key=StandardKey(value="ISO26262-5"),
        name="ISO 26262-5",
        year=2018,
    ).model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="source"),
                    reference=StandardReference(standard="ISO 26262-5", year=2018, clause="7.1"),
                    clause_type=ClauseType.CLAUSE,
                    heading="Source",
                    content=(
                        TextBlock(
                            id="source-text",
                            text="See ISO 26262-6:2018, 7.4.5.",
                        ),
                    ),
                ),
            )
        }
    )
    target = Standard.from_name(
        key=StandardKey(value="ISO26262-6"),
        name="ISO 26262-6",
        year=2018,
    ).model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="target"),
                    reference=StandardReference(standard="ISO 26262-6", year=2018, clause="7.4.5"),
                    clause_type=ClauseType.CLAUSE,
                    heading="Target",
                    content=(TextBlock(id="target-text", text="Target."),),
                ),
            )
        }
    )
    repository.save(source)
    repository.save(target)

    result = MarkdownExportService(
        MarkdownExporter(), FileSystemPublicationDocumentProvider(repository)
    ).export(
        "ISO26262-5",
        tmp_path / "markdown" / "ISO26262-5",
    )

    rendered = result.generated_files[0].read_text(encoding="utf-8")
    assert ("[ISO 26262-6:2018, 7.4.5](../ISO26262-6/ISO26262-6.md#clause-7-4-5)") in rendered


def test_links_clause_in_another_part_file(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    document = Standard.from_name(
        key=StandardKey(value="ISO26262"),
        name="ISO 26262",
        year=2018,
    ).model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="source"),
                    reference=StandardReference(
                        standard="ISO 26262", year=2018, clause="7.1", part="5"
                    ),
                    clause_type=ClauseType.CLAUSE,
                    heading="Source",
                    content=(
                        TextBlock(
                            id="source-text",
                            text="See ISO 26262-6:2018, 7.4.5.",
                        ),
                    ),
                ),
                Clause(
                    id=ClauseId(value="target"),
                    reference=StandardReference(
                        standard="ISO 26262", year=2018, clause="7.4.5", part="6"
                    ),
                    clause_type=ClauseType.CLAUSE,
                    heading="Target",
                    content=(TextBlock(id="target-text", text="Target."),),
                ),
            )
        }
    )
    repository.save(document)

    result = MarkdownExportService(
        MarkdownExporter(), FileSystemPublicationDocumentProvider(repository)
    ).export(
        "ISO26262",
        tmp_path / "markdown" / "ISO26262",
    )

    rendered = result.generated_files[0].read_text(encoding="utf-8")
    assert ("[ISO 26262-6:2018, 7.4.5](ISO26262-6.md#clause-7-4-5)") in rendered
