import json
from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.cli.main import app
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)

runner = CliRunner()


def _document() -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test Standard",
        document_type=DocumentType.SPECIFICATION,
        clauses=(
            Clause(
                id=ClauseId(value="terms"),
                reference=StandardReference(
                    standard="TEST",
                    year=2026,
                    clause="3",
                ),
                clause_type=ClauseType.TERM,
                heading="Terms and definitions",
            ),
            Clause(
                id=ClauseId(value="risk"),
                reference=StandardReference(
                    standard="TEST",
                    year=2026,
                    clause="3.1",
                ),
                clause_type=ClauseType.TERM,
                heading="risk",
            ),
            Clause(
                id=ClauseId(value="risk-2"),
                reference=StandardReference(
                    standard="TEST",
                    year=2026,
                    clause="3.2",
                ),
                clause_type=ClauseType.TERM,
                heading="Risk",
            ),
        ),
    )


def test_subject_vocabulary_prints_analysis_from_persisted_documents(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas" / "data"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())

    result = runner.invoke(
        app,
        ["context", "subject-vocabulary", "--workspace", str(workspace)],
    )

    assert result.exit_code == 0, result.output
    assert "Term clauses              : 3" in result.output
    assert "Accepted term clauses     : 2" in result.output
    assert "Unique candidates         : 1" in result.output
    assert "Extraction coverage       : 100.0%" in result.output
    assert "risk" in result.output


def test_subject_vocabulary_can_write_complete_json(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas" / "data"
    output = tmp_path / "local" / "analysis" / "subject-vocabulary.json"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())

    result = runner.invoke(
        app,
        [
            "context",
            "subject-vocabulary",
            "--workspace",
            str(workspace),
            "--output",
            str(output),
            "--limit",
            "0",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["analysis"]["unique_candidates"] == 1
    assert payload["candidates"][0]["normalized_label"] == "risk"
    assert "Most frequent candidates" not in result.output
