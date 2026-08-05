"""Markdown rendering for annotation qualification reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from standards_atlas.shared.markdown import markdown_row

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.qualification import (
        AgreementMetrics,
        AnnotationQualificationReport,
    )


def render_annotation_qualification_markdown(
    report: AnnotationQualificationReport,
) -> str:
    """Render one annotation qualification report as Markdown."""

    def agreement_line(name: str, metric: AgreementMetrics) -> str:
        values = (
            name,
            f"{metric.evaluated}/{metric.eligible}",
            f"{metric.exact_match_rate:.3f}",
            f"{metric.primary_function_accuracy:.3f}",
            f"{metric.micro_f1:.3f}",
            f"{metric.macro_f1:.3f}",
        )
        return markdown_row(values)

    brier = report.calibration.brier_score
    calibration_error = report.calibration.expected_calibration_error
    lines = [
        f"# Annotation qualification: {report.corpus_id}",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "## Coverage",
        "",
        f"- Corpus clauses: {report.coverage.corpus_clauses}",
        f"- Predictions: {report.coverage.predictions}",
        f"- Published gold: {report.coverage.published_gold}",
        f"- Local reviewed gold: {report.coverage.local_reviewed_gold}",
        f"- Local proposals: {report.coverage.local_proposals}",
        f"- Structure labels: {report.coverage.structure_labels}",
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
        "## Agreement",
        "",
        "| Evidence | Evaluated | Exact | Primary accuracy | Micro-F1 | Macro-F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        agreement_line("Gold", report.gold_agreement),
        agreement_line("Silver", report.silver_agreement),
        agreement_line("Structure", report.structure_agreement),
        "",
        "## Calibration",
        "",
        f"- Confidence coverage: {report.calibration.coverage:.3f}",
        f"- Brier score: {brier if brier is not None else 'n/a'}",
        "- Expected calibration error: "
        f"{calibration_error if calibration_error is not None else 'n/a'}",
        "",
        "## Primary-role confusion",
        "",
        "| Expected | Predicted | Count |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {entry.expected} | {entry.predicted} | {entry.count} |"
        for entry in report.primary_function_confusion
    )
    lines.extend(
        [
            "",
            "## Slice results",
            "",
            "| Dimension | Value | Cases | Gold F1 | Silver F1 | Structure F1 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.slices:
        values = (
            item.dimension,
            item.value,
            str(item.cases),
            f"{item.gold.micro_f1:.3f}",
            f"{item.silver.micro_f1:.3f}",
            f"{item.structure.micro_f1:.3f}",
        )
        lines.append("| " + " | ".join(values) + " |")
    if report.diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        lines.extend(f"- {item}" for item in report.diagnostics)
    return "\n".join(lines) + "\n"
