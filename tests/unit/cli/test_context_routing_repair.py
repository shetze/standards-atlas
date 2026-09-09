"""Canonical repair is a dry-run by default and never starts an LLM server."""

import json
from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.cli import app
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    ContextRouting,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    ReferenceRouting,
    ReferenceTarget,
    StandardReference,
    TextBlock,
)


def make_document():
    evidence = "See Annex G for this synthetic example."
    source = Clause(
        id=ClauseId(value="source"),
        reference=StandardReference(standard="TEST", part="3", year=2026, clause="7.1.2.4"),
        clause_type=ClauseType.CLAUSE,
        baseline={"content": (TextBlock(id="text", text=evidence),)},
        enrichments={
            "context_routing": ContextRouting(
                references=(
                    ReferenceRouting(
                        source_clause_id="source",
                        target=ReferenceTarget(
                            document_key="TEST-3",
                            clause_id="source",
                            reference="TEST-3:2026 7.1.2.4",
                        ),
                        role="provides_exception",
                        evidence=(evidence,),
                    ),
                )
            )
        },
    )
    target = Clause(
        id=ClauseId(value="annex"),
        reference=StandardReference(standard="TEST", part="3", year=2026, clause="G"),
        clause_type=ClauseType.CLAUSE,
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST-3"),
        title="Synthetic repair fixture",
        document_type=DocumentType.OTHER,
        clauses=(source, target),
    )


def test_cli_dry_run_write_backup_and_repeated_write_are_safe(tmp_path, monkeypatch):
    from standards_atlas.cli.commands.document_commands import management

    def no_llm(*args, **kwargs):
        raise AssertionError("repair must never start an LLM")

    monkeypatch.setattr(management, "managed_llm_server", no_llm)
    workspace = tmp_path / ".atlas/data"
    repo = FileSystemEngineeringDocumentRepository(workspace)
    doc = make_document()
    repo.save(doc)
    path = workspace / "documents/TEST-3.json"
    before = path.read_bytes()
    report = tmp_path / "report.json"
    args = [
        "document",
        "repair-context-routing",
        "TEST-3",
        "--workspace",
        str(workspace),
        "--report",
        str(report),
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_text())
    assert payload["routing_clauses_changed"] == 1
    assert payload["written"] is False
    assert payload["backup"] is None
    assert path.read_bytes() == before
    assert not tuple(path.parent.glob("*.bak"))

    result = runner.invoke(app, [*args, "--write"])
    assert result.exit_code == 0, result.output
    payload = json.loads(report.read_text())
    assert payload["written"] is True
    assert Path(payload["backup"]).read_bytes() == before
    assert repo.load(doc.key).clauses[0].context_routing.references[0].target.clause_id == "annex"
    assert len(repo.list()) == 1  # Backups are not mistaken for document JSONs.
    after = path.read_bytes()
    result = runner.invoke(app, [*args, "--write"])
    assert result.exit_code == 0, result.output
    assert path.read_bytes() == after
    assert json.loads(report.read_text())["clauses_changed"] == 0
    assert len(tuple(path.parent.glob("*.bak"))) == 1


def test_report_cannot_overwrite_any_canonical_document(tmp_path):
    repo = FileSystemEngineeringDocumentRepository(tmp_path)
    doc = make_document()
    repo.save(doc)
    path = tmp_path / "documents/TEST-3.json"
    before = path.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "document",
            "repair-context-routing",
            "TEST-3",
            "--workspace",
            str(tmp_path),
            "--report",
            str(path),
            "--write",
        ],
    )
    assert result.exit_code == 2
    assert path.read_bytes() == before


def test_missing_document_exits_with_actionable_error(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "document",
            "repair-context-routing",
            "missing",
            "--workspace",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "No persisted document" in result.output
