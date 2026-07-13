from pathlib import Path

from typer.testing import CliRunner
from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.cli import app
from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
)


runner = CliRunner()


def test_document_export_doorstop_reports_missing_document(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / ".atlas"

    result = runner.invoke(
        app,
        [
            "document",
            "export",
            "doorstop",
            "MISSING",
            "--workspace",
            str(workspace),
        ],
    )

    assert result.exit_code == 1
    assert "No persisted document found" in result.output


def test_document_export_doorstop_exports_persisted_document(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / ".atlas"

    repository = FileSystemEngineeringDocumentRepository(
        workspace=workspace,
    )

    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="EXAMPLE"),
            title="Example Document",
            document_type=DocumentType.OTHER,
        )
    )

    target = tmp_path / "doorstop-export"

    result = runner.invoke(
        app,
        [
            "document",
            "export",
            "doorstop",
            "EXAMPLE",
            "--workspace",
            str(workspace),
            "--target",
            str(target),
            "--no-validate",
        ],
    )

    assert result.exit_code == 0
    assert "Exported document" in result.output
    assert target.exists()
    assert (target / ".doorstop.yml").exists()
