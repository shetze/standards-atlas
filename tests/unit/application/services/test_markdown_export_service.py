from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
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
    document = document.model_copy(update={"clauses": (
        _clause("p1", "1", "1", "Part one"),
        _clause("p2", "2", "1", "Part two"),
    )})
    repository.save(document)

    result = MarkdownExportService(MarkdownExporter(), workspace).export(
        "IEC11889", tmp_path / "markdown"
    )

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

    result = MarkdownExportService(MarkdownExporter(), workspace).export(
        "EN50716", tmp_path / "markdown"
    )

    assert [path.name for path in result.generated_files] == ["EN50716.md"]


def _clause(identifier: str, volume: str | None, reference: str, text: str) -> Clause:
    return Clause(
        id=ClauseId(value=identifier),
        reference=StandardReference(standard="IEC 11889", year=2015, clause=reference),
        clause_type=ClauseType.CLAUSE,
        title="Scope",
        volume=volume,
        content=(TextBlock(id=f"{identifier}-text", text=text),),
    )
