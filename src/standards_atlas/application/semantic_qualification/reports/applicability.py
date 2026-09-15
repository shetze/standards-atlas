"""Markdown rendering for applicability qualification reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.applicability_qualification import (
        ApplicabilityQualificationReport,
    )


def render_applicability_qualification_markdown(
    report: ApplicabilityQualificationReport,
) -> str:
    """Render one applicability-presence qualification report as Markdown."""
    metric = report.gold_agreement
    brier = report.calibration.brier_score
    calibration_error = report.calibration.expected_calibration_error
    lines = [
        "# Applicability Qualification",
        "",
        f"- Corpus: `{report.corpus_id}`",
        f"- Prediction source: `{report.prediction_source}`",
        f"- Corpus clauses: {report.coverage.corpus_clauses}",
        f"- Predictions: {report.coverage.predictions}",
        f"- Published gold: {report.coverage.published_gold}",
        f"- Local reviewed gold: {report.coverage.local_reviewed_gold}",
        f"- Local proposals: {report.coverage.local_proposals}",
        f"- Missing predictions: {report.coverage.missing_predictions}",
        "",
        "## Reliability",
        "",
        f"- Attempted clauses: {report.reliability.attempted_clauses}",
        f"- Successful predictions: {report.reliability.successful_predictions}",
        f"- Failed responses: {report.reliability.failed_responses}",
        f"- Truncated responses: {report.reliability.truncated_responses}",
        f"- Invalid JSON responses: {report.reliability.invalid_json_responses}",
        f"- Timeout responses: {report.reliability.timeout_responses}",
        f"- Prediction success rate: {report.reliability.prediction_success_rate:.3f}",
        f"- JSON validity rate: {report.reliability.json_validity_rate:.3f}",
        f"- Truncation rate: {report.reliability.truncation_rate:.3f}",
        "",
        "## Gold agreement",
        "",
        f"- Evaluated: {metric.evaluated}/{metric.eligible} ({metric.coverage:.3f})",
        f"- Accuracy: {metric.accuracy:.3f}",
        f"- Precision: {metric.precision:.3f}",
        f"- Recall: {metric.recall:.3f}",
        f"- Specificity: {metric.specificity:.3f}",
        f"- F1: {metric.f1:.3f}",
        f"- TP/FP/TN/FN: {metric.true_positive}/{metric.false_positive}/"
        f"{metric.true_negative}/{metric.false_negative}",
        "",
        "## Calibration",
        "",
        f"- Confidence coverage: {report.calibration.coverage:.3f}",
        f"- Brier score: {brier if brier is not None else 'n/a'}",
        "- Expected calibration error: "
        f"{calibration_error if calibration_error is not None else 'n/a'}",
        "",
        "## Slice results",
        "",
        "| Dimension | Value | Cases | Coverage | F1 | Accuracy |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in report.slices:
        lines.append(
            f"| {item.dimension} | {item.value} | {item.cases} | "
            f"{item.gold.coverage:.3f} | {item.gold.f1:.3f} | {item.gold.accuracy:.3f} |"
        )
    if report.diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        lines.extend(f"- {item}" for item in report.diagnostics)
    return "\n".join(lines) + "\n"
