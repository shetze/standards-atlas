from pathlib import Path

from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentProvider,
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


def _document(key: str, part: str) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=f"Test Part {part}",
        document_type=DocumentType.OTHER,
        year=2026,
        version="1.0",
        source="fixture",
        clauses=(
            Clause(
                id=ClauseId(value=f"{key}-root"),
                reference=StandardReference(standard="TEST", part=part, clause="0"),
                clause_type=ClauseType.TOC,
                heading=f"Part {part}",
            ),
            Clause(
                id=ClauseId(value=f"{key}-1"),
                reference=StandardReference(standard="TEST", part=part, clause="1"),
                clause_type=ClauseType.CLAUSE,
                heading="Scope",
            ),
        ),
    )


def test_provider_projects_physical_document_without_persistence(tmp_path: Path) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document("PART-1", "1"))
    provider = FileSystemPublicationDocumentProvider(documents)

    publication = provider.load("PART-1")

    assert publication.key.value == "PART-1"
    assert publication.part_keys == ("PART-1",)
    assert publication.year == 2026
    assert publication.version == "1.0"
    assert publication.source == "fixture"
    assert [clause.reference.clause for clause in publication.clauses] == ["0", "1"]


def test_provider_composes_family_on_demand_without_family_document(tmp_path: Path) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document("PART-1", "1"))
    documents.save(_document("PART-2", "2"))
    provider = FileSystemPublicationDocumentProvider(documents)

    publication = provider.load(
        "FAMILY",
        part_keys=("PART-1", "PART-2"),
        family_title="Test Family",
    )

    assert publication.key.value == "FAMILY"
    assert publication.title == "Test Family"
    assert publication.part_keys == ("PART-1", "PART-2")
    assert publication.year == 2026
    assert publication.version == "1.0"
    assert publication.source == "fixture"
    assert [clause.reference.part for clause in publication.clauses] == ["1", "1", "2", "2"]
    assert not documents.exists(DocumentKey(value="FAMILY"))
    assert not (tmp_path / "work" / "composed-documents").exists()
