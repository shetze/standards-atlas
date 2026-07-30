from pathlib import Path

from typer.testing import CliRunner

from standards_atlas.application.qualification import GoldenCaseResult, GoldenCorpusReport
from standards_atlas.cli.main import app


def test_golden_corpus_cli_writes_reports(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "corpus.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    output = tmp_path / "reports"
    qualification = GoldenCorpusReport(
        corpus_version="1.0.0",
        passed=True,
        cases=(
            GoldenCaseResult(
                case_id="sample",
                passed=True,
                input_sha256="a" * 64,
                normalized_sha256="b" * 64,
            ),
        ),
    )
    monkeypatch.setattr(
        "standards_atlas.cli.commands.evaluation.GoldenCorpusQualifier.run",
        lambda self, root: qualification,
    )

    result = CliRunner().invoke(
        app,
        [
            "qualification",
            "golden-corpus",
            "--corpus",
            str(corpus),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Qualification status    : passed" in result.output
    assert len(tuple(output.glob("*/report.json"))) == 1
    assert len(tuple(output.glob("*/report.md"))) == 1


def test_golden_corpus_cli_returns_nonzero_after_writing_failed_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "corpus.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    output = tmp_path / "reports"
    qualification = GoldenCorpusReport(
        corpus_version="1.0.0",
        passed=False,
        cases=(
            GoldenCaseResult(
                case_id="sample",
                passed=False,
                input_sha256="a" * 64,
                failures=("regression",),
            ),
        ),
    )
    monkeypatch.setattr(
        "standards_atlas.cli.commands.evaluation.GoldenCorpusQualifier.run",
        lambda self, root: qualification,
    )

    result = CliRunner().invoke(
        app,
        [
            "qualification",
            "golden-corpus",
            "--corpus",
            str(corpus),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "Qualification status    : failed" in result.output
    assert len(tuple(output.glob("*/report.json"))) == 1
