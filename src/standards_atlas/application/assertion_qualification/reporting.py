"""Deterministic, human-readable summaries for assertion qualification reports."""

from __future__ import annotations

from collections import Counter

from standards_atlas.application.assertion_qualification.models import (
    AccuracyMetrics,
    AssertionDiagnosticStatus,
    AssertionQualificationCaseReport,
    AssertionQualificationReport,
    CountMetrics,
    RatioMetric,
    ReviewSnapshotProvenance,
)
from standards_atlas.application.assertion_qualification.policy import (
    qualification_report_sha256,
)


def render_assertion_qualification_summary(report: AssertionQualificationReport) -> str:
    """Render a stable Markdown note without timestamps, paths, or invented judgements.

    The note deliberately separates measured strict differences, retained technical
    proposal diagnostics, historical verifier rejections, and diagnostic findings that
    still require human review. It is therefore suitable for reproducibility comparisons
    and for the private AP01 v8 baseline once the byte-bound audit is available.
    """

    aggregate = report.aggregate
    lines = [
        "# Assertion qualification baseline",
        "",
        "## Bound evaluation",
        "",
        f"- Evaluation contract: `{report.evaluation_contract}`",
        f"- Candidate mode: `{report.candidate_mode}`",
        f"- Source binding: `{report.source_binding}`",
        (
            "- Golden suite: "
            f"`{report.golden_suite_id}@{report.golden_suite_version}` "
            f"(`{report.golden_suite_hash}`)"
        ),
        (
            "- Audit: "
            f"`{report.audit.review_id}@{report.audit.review_version}` "
            f"(`{report.audit.audit_sha256}`)"
        ),
        f"- Deterministic report SHA-256: `{qualification_report_sha256(report)}`",
        (
            "- Coverage: "
            f"{aggregate.candidate_clauses}/{aggregate.clauses} candidate clauses, "
            f"{aggregate.documents} distinct documents"
        ),
        "- Ontology resources:",
    ]
    lines.extend(
        f"  - `{item.reference}`: `{item.resource_sha256}`" for item in report.ontology_resources
    )
    lines.extend(
        [
            "",
            "## Strict regression metrics",
            "",
            "| Metric | Value | Support |",
            "|---|---:|---:|",
            _count_metric_row("Entity label precision", aggregate.entities, "precision"),
            _count_metric_row("Entity label recall", aggregate.entities, "recall"),
            _count_metric_row("Entity label F1", aggregate.entities, "f1"),
            _count_metric_row("Typed entity precision", aggregate.typed_entities, "precision"),
            _count_metric_row("Typed entity recall", aggregate.typed_entities, "recall"),
            _accuracy_metric_row("Entity class accuracy", aggregate.entity_class_accuracy),
            _count_metric_row("Assertion precision", aggregate.assertions, "precision"),
            _count_metric_row("Assertion recall", aggregate.assertions, "recall"),
            _count_metric_row("Assertion F1", aggregate.assertions, "f1"),
            _accuracy_metric_row("Predicate accuracy", aggregate.predicate_accuracy),
            _accuracy_metric_row("Normative force accuracy", aggregate.normative_force_accuracy),
            _accuracy_metric_row("Evidence span exact match", aggregate.evidence_span_exact_match),
            _accuracy_metric_row("Exact assertion accuracy", aggregate.exact_assertion_accuracy),
            (
                "| Clause-level exact match | "
                f"{_ratio_text(aggregate.clause_exact_match.accuracy)} | "
                f"{aggregate.clause_exact_match.matched}/{aggregate.clause_exact_match.cases} |"
            ),
            "",
            "Extraction counts are kept separate from attribute accuracies:",
            "",
            "| Object | Expected | Predicted | TP | FP | FN |",
            "|---|---:|---:|---:|---:|---:|",
            _count_support_row("Entities", aggregate.entities),
            _count_support_row("Typed entities", aggregate.typed_entities),
            _count_support_row("Assertions", aggregate.assertions),
            "",
            "## Work-product metrics",
            "",
            "| Metric | Value | Support |",
            "|---|---:|---:|",
            _ratio_row("Work-product precision", aggregate.work_product_precision),
            _ratio_row("Work-product recall", aggregate.work_product_recall),
            _accuracy_metric_row(
                "Work-product class accuracy", aggregate.work_product_class_accuracy
            ),
            _ratio_row(
                "Required work-product relation recall",
                aggregate.required_work_product_relation_recall,
            ),
            "",
            "## Evidence and diagnostic separation",
            "",
            (
                "- Technical evidence integrity: "
                f"{_ratio_text(aggregate.evidence_integrity.validity)}; "
                f"valid={aggregate.evidence_integrity.valid}, "
                f"invalid={aggregate.evidence_integrity.invalid}, "
                f"unavailable={aggregate.evidence_integrity.unavailable}, "
                f"conflicting={aggregate.evidence_integrity.conflicting}."
            ),
            (
                "- Semantic evidence judgement: "
                f"`{aggregate.semantic_evidence.status}`; AP01 does not infer semantic "
                "support from technical hash/span validity."
            ),
        ]
    )

    source_comparisons = Counter(
        case.source_comparison.status.value
        for case in report.cases
        if case.source_comparison.status.value != "not_evaluated"
    )
    if source_comparisons:
        lines.append(
            "- Native candidate-source comparability (reporting only): "
            + ", ".join(f"{status}={count}" for status, count in sorted(source_comparisons.items()))
            + "; this does not change strict matching."
        )

    rejected = _historical_rejections(report)
    violations = sum(case.proposal_violations for case in report.cases)
    failures = sum(case.proposal_failures for case in report.cases)
    status_counts = Counter(
        finding.status.value for case in report.cases for finding in case.diagnostic_findings
    )
    needs_review_codes = Counter(
        code.value
        for case in report.cases
        for finding in case.diagnostic_findings
        if finding.status is AssertionDiagnosticStatus.NEEDS_REVIEW
        for code in finding.codes
    )
    lines.extend(
        [
            (
                "- Retained proposal diagnostics: "
                f"{violations} violation record(s), {failures} failure record(s)."
            ),
            (
                "- Historical verifier rejections declared by review snapshots: "
                f"{len(rejected)} candidate reference(s)."
            ),
            (
                "- Diagnostic findings: "
                f"rule_based={status_counts['rule_based']}, "
                f"needs_review={status_counts['needs_review']}, "
                f"human_confirmed={status_counts['human_confirmed']}."
            ),
        ]
    )
    if needs_review_codes:
        lines.append(
            "- Unconfirmed diagnostic suggestions: "
            + ", ".join(f"`{code}`={count}" for code, count in sorted(needs_review_codes.items()))
            + "."
        )
    else:
        lines.append("- Unconfirmed diagnostic suggestions: none in this report.")

    mismatches = [case for case in report.cases if case.clause_exact_match.value is not True]
    lines.extend(["", "## Case-level differences", ""])
    if not mismatches:
        lines.append(
            "All candidate-present cases exactly match the fields annotated in the golden suite."
        )
    else:
        for case in mismatches:
            lines.extend(_case_difference_lines(case))

    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This report is a deterministic regression comparison, not a production-adoption "
            "decision. Review-snapshot provenance does not reconstruct unavailable historical "
            "model or rendered-input provenance, and `needs_review` diagnostics are not human "
            "confirmed. Poor metric values are regression results rather than test failures.",
            "",
        ]
    )
    return "\n".join(lines)


def _count_metric_row(label: str, metric: CountMetrics, field: str) -> str:
    ratio = getattr(metric, field)
    return f"| {label} | {_ratio_text(ratio)} | {ratio.numerator}/{ratio.denominator} |"


def _accuracy_metric_row(label: str, metric: AccuracyMetrics) -> str:
    return (
        f"| {label} | {_ratio_text(metric.accuracy)} | "
        f"{metric.correct}/{metric.evaluated}; aligned "
        f"{metric.alignment_coverage.numerator}/{metric.alignment_coverage.denominator} |"
    )


def _ratio_row(label: str, metric: RatioMetric) -> str:
    return f"| {label} | {_ratio_text(metric)} | {metric.numerator}/{metric.denominator} |"


def _ratio_text(metric: RatioMetric) -> str:
    if metric.value is None:
        return f"n/a (`{metric.status.value}`)"
    return f"{metric.value:.4f} (`{metric.status.value}`)"


def _count_support_row(label: str, metric: CountMetrics) -> str:
    return (
        f"| {label} | {metric.expected} | {metric.predicted} | {metric.true_positive} | "
        f"{metric.false_positive} | {metric.false_negative} |"
    )


def _historical_rejections(report: AssertionQualificationReport) -> tuple[tuple[str, str], ...]:
    rejected: list[tuple[str, str]] = []
    for case in report.cases:
        provenance = case.provenance
        if not isinstance(provenance, ReviewSnapshotProvenance):
            continue
        rejected.extend(
            (f"{case.source_document_key}:{case.clause_id.value}", candidate_id)
            for candidate_id, disposition in provenance.verifier_dispositions.items()
            if disposition == "rejected"
        )
    return tuple(sorted(rejected))


def _case_difference_lines(case: AssertionQualificationCaseReport) -> list[str]:
    exact = (
        "missing candidate"
        if case.clause_exact_match.value is None
        else "exact"
        if case.clause_exact_match.value
        else "different"
    )
    lines = [
        f"### `{case.source_document_key}` / `{case.clause_id.value}` — {case.reference}",
        "",
        f"- Clause comparison: {exact} (`{case.clause_exact_match.status.value}`).",
        (
            "- Entity differences: "
            f"FP={list(case.entity_false_positive_ids)!r}; "
            f"FN={list(case.entity_false_negative_ids)!r}."
        ),
        (
            "- Assertion differences: "
            f"FP={list(case.assertion_false_positive_ids)!r}; "
            f"FN={list(case.assertion_false_negative_ids)!r}."
        ),
    ]
    if case.violation_details:
        lines.append(f"- Retained proposal violations: {list(case.violation_details)!r}.")
    if case.failure_details:
        lines.append(f"- Retained proposal failures: {list(case.failure_details)!r}.")
    provenance = case.provenance
    if isinstance(provenance, ReviewSnapshotProvenance):
        rejected = sorted(
            candidate_id
            for candidate_id, disposition in provenance.verifier_dispositions.items()
            if disposition == "rejected"
        )
        if rejected:
            lines.append(f"- Historical verifier-rejected candidate references: {rejected!r}.")
    for finding in case.diagnostic_findings:
        codes = ", ".join(f"`{code.value}`" for code in finding.codes)
        lines.append(
            f"- Finding ({finding.status.value}, {finding.origin.value}; {codes}): "
            f"{finding.observed_difference}"
        )
    lines.append("")
    return lines
