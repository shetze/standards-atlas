from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from standards_atlas.application.assertion_qualification import (
    AssertionQualificationEvaluator,
    load_assertion_golden_suite,
    load_assertion_qualification_report,
    load_assertion_review_audit,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/assertion_qualification/synthetic-reviewed-complete.yaml"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), env.get("PYTHONPATH", ""))).rstrip(
        os.pathsep
    )
    for name in tuple(env):
        upper = name.upper()
        if any(token in upper for token in ("OPENAI", "RAMALAMA", "LLM_API", "ANTHROPIC")):
            env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-c", "from standards_atlas.cli import app; app()", *args],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _publish(review: Path, golden: Path) -> subprocess.CompletedProcess[str]:
    return _run_cli(
        "evaluation",
        "assertion-review-pilot-publish",
        "--review",
        str(review),
        "--output",
        str(golden),
    )


def _evaluate(
    review: Path, golden: Path, report: Path, summary: Path
) -> subprocess.CompletedProcess[str]:
    return _run_cli(
        "evaluation",
        "assertion-evaluate",
        "--golden",
        str(golden),
        "--review",
        str(review),
        "--output",
        str(report),
        "--summary-output",
        str(summary),
    )


def test_two_fresh_process_runs_have_identical_golden_report_and_summary(tmp_path: Path) -> None:
    original = FIXTURE.read_bytes()
    review = tmp_path / "review.yaml"
    review.write_bytes(original)

    outputs: list[tuple[Path, Path, Path]] = []
    for run in (1, 2):
        golden = tmp_path / f"golden-{run}.yaml"
        report = tmp_path / f"report-{run}.json"
        summary = tmp_path / f"summary-{run}.md"
        published = _publish(review, golden)
        assert published.returncode == 0, published.stdout + published.stderr
        evaluated = _evaluate(review, golden, report, summary)
        assert evaluated.returncode == 0, evaluated.stdout + evaluated.stderr
        assert "review_snapshot" in evaluated.stdout
        assert "Report SHA-256" in evaluated.stdout
        outputs.append((golden, report, summary))

    for index in range(3):
        assert outputs[0][index].read_bytes() == outputs[1][index].read_bytes()
    assert review.read_bytes() == original

    suite = load_assertion_golden_suite(outputs[0][0])
    stored = load_assertion_qualification_report(outputs[0][1])
    audit = load_assertion_review_audit(review)
    replayed = AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)
    assert replayed == stored


def test_fresh_process_rejects_changed_audit_and_stale_golden_schema(tmp_path: Path) -> None:
    review = tmp_path / "review.yaml"
    review.write_bytes(FIXTURE.read_bytes())
    golden = tmp_path / "golden.yaml"
    published = _publish(review, golden)
    assert published.returncode == 0, published.stdout + published.stderr

    reformatted = tmp_path / "review-reformatted.yaml"
    payload = yaml.safe_load(review.read_text(encoding="utf-8"))
    reformatted.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    mismatch_report = tmp_path / "audit-mismatch.json"
    mismatch_summary = tmp_path / "audit-mismatch.md"
    mismatch = _evaluate(reformatted, golden, mismatch_report, mismatch_summary)
    assert mismatch.returncode == 2
    assert "audit SHA-256" in mismatch.stdout + mismatch.stderr
    assert not mismatch_report.exists()
    assert not mismatch_summary.exists()

    stale_payload = yaml.safe_load(golden.read_text(encoding="utf-8"))
    stale_payload["schema_version"] = 0
    stale = tmp_path / "golden-stale.yaml"
    stale.write_text(yaml.safe_dump(stale_payload, sort_keys=False), encoding="utf-8")
    stale_report = tmp_path / "stale.json"
    stale_summary = tmp_path / "stale.md"
    result = _evaluate(review, stale, stale_report, stale_summary)
    assert result.returncode == 2
    assert "schema" in (result.stdout + result.stderr).casefold()
    assert not stale_report.exists()
    assert not stale_summary.exists()
