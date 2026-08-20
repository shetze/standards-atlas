from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.services import StructuralTaxonomyService
from standards_atlas.cli.main import app
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


def test_route_semantics_persists_selected_contract_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas" / "data"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="TEST"),
            title="Test",
            document_type=DocumentType.OTHER,
            clauses=(
                Clause(
                    id=ClauseId(value="clause-1"),
                    reference=StandardReference(standard="TEST", clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    title="Scope",
                    content=(TextBlock(id="text-1", text="Requirements apply."),),
                ),
            ),
        )
    )
    StructuralTaxonomyService(repository).classify("TEST")

    result = CliRunner().invoke(
        app,
        [
            "document",
            "route-semantics",
            "TEST",
            "--manifest",
            "manifests/functional-safety-semantic-routing-v1.yaml",
            "--workspace",
            str(workspace),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "functional-safety-semantic-profile@1.0.0" in result.output
    assert "Clauses routed        : 1" in result.output
    assert (
        workspace
        / "routing"
        / "TEST"
        / "functional-safety-semantic-profile"
        / "1.0.0"
        / "routing.json"
    ).is_file()
