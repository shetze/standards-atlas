import json
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas.application.qualification import (
    GoldenCaseResult,
    GoldenCorpusReport,
    QualificationRunReporter,
)


def _report(*, passed: bool = True) -> GoldenCorpusReport:
    return GoldenCorpusReport(
        corpus_version="1.2.3",
        passed=passed,
        cases=(
            GoldenCaseResult(
                case_id="simple",
                passed=passed,
                input_sha256="a" * 64,
                normalized_sha256="b" * 64 if passed else None,
                failures=() if passed else ("expected value differs",),
            ),
        ),
    )


def test_reporter_writes_auditable_json_and_markdown(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "corpus.json").write_text('{"version":"1.2.3"}\n', encoding="utf-8")

    report_json, report_md = QualificationRunReporter().write(
        _report(),
        corpus_root=corpus,
        project_root=tmp_path,
        now=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["corpus_version"] == "1.2.3"
    assert payload["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert len(payload["corpus_sha256"]) == 64
    assert "qualification report" in report_md.read_text(encoding="utf-8")


def test_reporter_records_failures_without_suppressing_evidence(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "input.json").write_text("{}\n", encoding="utf-8")

    report_json, report_md = QualificationRunReporter().write(
        _report(passed=False),
        corpus_root=corpus,
        project_root=tmp_path,
        output_root=tmp_path / "reports",
        now=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["summary"]["failed"] == 1
    assert "expected value differs" in report_md.read_text(encoding="utf-8")


def test_corpus_hash_is_independent_of_file_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "a").write_text("A", encoding="utf-8")
    (first / "b").write_text("B", encoding="utf-8")
    (second / "b").write_text("B", encoding="utf-8")
    (second / "a").write_text("A", encoding="utf-8")

    reporter = QualificationRunReporter()

    assert reporter._directory_hash(first) == reporter._directory_hash(second)
