from pathlib import Path

import yaml

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.semantic_qualification.references import (
    ClauseReferenceExtractionService,
    ReferenceResolutionStatus,
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


def _clause(clause_id: str, reference: str, text: str, title: str | None = None) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="IEC61508-3", clause=reference),
        clause_type=ClauseType.CLAUSE,
        title=title,
        text=text,
    )


def test_extracts_and_resolves_clause_range(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    document = EngineeringDocument(
        key=DocumentKey(value="IEC61508-3"),
        title="Software requirements",
        document_type=DocumentType.SPECIFICATION,
        clauses=(
            _clause("c1", "7.4.3.2.2", "First requirement", "First"),
            _clause("c2", "7.4.3.2.3", "Second requirement", "Second"),
            _clause("c3", "7.4.3.2.4", "Third requirement", "Third"),
            _clause("c4", "7.4.3.2.5", "Fourth requirement", "Fourth"),
            _clause(
                "c5",
                "7.4.3.2.6",
                "The test goals resulting from the requirements 7.4.3.2.2 to "
                "7.4.3.2.5 shall be addressed by adequate test methods.",
            ),
        ),
    )
    FileSystemEngineeringDocumentRepository(workspace).save(document)

    result = ClauseReferenceExtractionService().run(
        workspace=workspace,
        knowledge_domain="functional-safety",
        output_root=tmp_path / "references",
    )

    assert result.references == 1
    assert result.resolved == 1
    payload = yaml.safe_load(
        (tmp_path / "references/functional-safety/IEC61508-3/c5.yaml").read_text()
    )
    reference = payload["references"][0]
    assert reference["status"] == ReferenceResolutionStatus.RESOLVED
    assert [target["reference"] for target in reference["targets"]] == [
        "7.4.3.2.2",
        "7.4.3.2.3",
        "7.4.3.2.4",
        "7.4.3.2.5",
    ]


def test_preserves_unresolved_reference_as_diagnostic(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.SPECIFICATION,
        clauses=(_clause("c1", "8.1", "See clause 9.9 for details."),),
    )
    FileSystemEngineeringDocumentRepository(workspace).save(document)

    ClauseReferenceExtractionService().run(
        workspace=workspace,
        knowledge_domain="functional-safety",
        output_root=tmp_path / "references",
    )

    payload = yaml.safe_load((tmp_path / "references/functional-safety/DOC/c1.yaml").read_text())
    reference = payload["references"][0]
    assert reference["status"] == ReferenceResolutionStatus.UNRESOLVED
    assert reference["unresolved_references"] == ["9.9"]


def test_does_not_treat_arbitrary_decimal_as_reference(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Document",
        document_type=DocumentType.SPECIFICATION,
        clauses=(_clause("c1", "8.1", "The probability shall be below 0.01."),),
    )
    FileSystemEngineeringDocumentRepository(workspace).save(document)

    result = ClauseReferenceExtractionService().run(
        workspace=workspace,
        knowledge_domain="functional-safety",
        output_root=tmp_path / "references",
    )

    assert result.references == 0
