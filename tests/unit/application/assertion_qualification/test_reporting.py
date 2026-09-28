from __future__ import annotations

from pathlib import Path

from standards_atlas.application.assertion_qualification import (
    AssertionQualificationEvaluator,
    load_assertion_review_audit,
    publish_assertion_review_pilot,
    qualification_report_sha256,
    render_assertion_qualification_summary,
)

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/assertion_qualification/synthetic-reviewed-complete.yaml"
)


def test_summary_is_deterministic_and_separates_metrics_from_diagnosis() -> None:
    audit = load_assertion_review_audit(FIXTURE)
    suite = publish_assertion_review_pilot(audit)
    report = AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)

    left = render_assertion_qualification_summary(report)
    right = render_assertion_qualification_summary(report)

    assert left == right
    assert qualification_report_sha256(report) in left
    assert "## Strict regression metrics" in left
    assert "## Work-product metrics" in left
    assert "## Evidence and diagnostic separation" in left
    assert "Retained proposal diagnostics" in left
    assert "Historical verifier rejections" in left
    assert "Unconfirmed diagnostic suggestions" in left
    assert "not a production-adoption decision" in left
    assert "current time" not in left.casefold()


def test_summary_contains_no_local_artifact_paths() -> None:
    audit = load_assertion_review_audit(FIXTURE)
    suite = publish_assertion_review_pilot(audit)
    report = AssertionQualificationEvaluator().evaluate(suite, review_audit=audit)

    summary = render_assertion_qualification_summary(report)

    assert str(FIXTURE) not in summary
    assert "/tmp/" not in summary
    assert "local/evaluation" not in summary
