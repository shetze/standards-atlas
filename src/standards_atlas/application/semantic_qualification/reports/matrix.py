"""Markdown rendering for model/prompt qualification matrices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from standards_atlas.shared.formatting import (
    format_decimal,
    format_gigabytes,
    format_seconds,
)

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CandidateQualification,
        ModelCandidate,
        QualificationMatrixReport,
    )


def _candidate_key(candidate: CandidateQualification) -> str:
    return f"{candidate.prompt_id} / {candidate.model_id} / {candidate.reasoning_mode_id}"


def render_qualification_matrix_markdown(
    report: QualificationMatrixReport,
    models: dict[str, ModelCandidate],
) -> str:
    """Render one model/prompt qualification matrix as Markdown."""
    lines = [
        f"# Model/prompt qualification matrix: {report.matrix_id}",
        "",
        f"- Corpus: `{report.corpus_id}`",
        f"- Overall result: **{'PASS' if report.passed else 'FAIL'}**",
        f"- Pareto front: {', '.join(report.pareto_front) or 'none'}",
        "",
        "## Ranking",
        "",
        (
            "| Rank | Prompt | Model | Reasoning | Gold F1 | Stddev | "
            "Coverage | Mean / measured request | Perf source | Fresh/Cache/Reuse | Memory "
            "| Result |"
        ),
        ("| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |"),
    ]
    by_key = {_candidate_key(item): item for item in report.candidates}
    for rank, key in enumerate(report.ranking, start=1):
        item = by_key[key]
        model = models[item.model_id]
        duration = format_seconds(item.mean_duration_seconds)
        memory = format_gigabytes(item.peak_memory_gb)
        marker = item.status.upper()
        fresh = "?" if item.fresh_prediction_count is None else str(item.fresh_prediction_count)
        execution_mix = f"{fresh}/{item.cached_prediction_count}/{item.reused_prediction_count}"
        if item.pareto_optimal:
            marker += " · Pareto"
        lines.append(
            f"| {rank} | `{item.prompt_id}` | `{model.id}` | "
            f"`{item.reasoning_mode_id}` | {format_decimal(item.mean_gold_f1)} | "
            f"{format_decimal(item.gold_f1_stddev)} | "
            f"{format_decimal(item.mean_gold_coverage)} | "
            f"{duration} | `{item.performance_measurement_source}` | {execution_mix} | "
            f"{memory} | {marker} |"
        )
    excluded = [item for item in report.candidates if not item.qualification_eligible]
    if excluded:
        lines.extend(
            [
                "",
                "## Not ranked",
                "",
                "| Prompt | Model | Reasoning | Status | Runs |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for item in excluded:
            lines.append(
                f"| `{item.prompt_id}` | `{item.model_id}` | "
                f"`{item.reasoning_mode_id}` | {item.status} | "
                f"{item.completed_repetitions}/{item.expected_repetitions} |"
            )

    lines.extend(
        [
            "",
            "## Measured request costs",
            "",
            "Means use measured-request denominators, not batch counts. Historical/cache durations "
            "are reference measurements, not fresh work. Gateway wall time includes failed "
            "attempts; unknown provider time for those failures is not estimated. Observation wall "
            "time excludes model startup; stage wall time is reported in cascade provenance.",
            "",
            "| Model | Prompt | Reasoning | Timed requests | Inference sum | Fresh inference | "
            "Gateway calls / failed | Gateway wall | Observation wall |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for item in report.candidates:
        timing = item.request_timing
        measured = (
            "n/a" if item.measured_request_count is None else str(item.measured_request_count)
        )
        calls = "n/a" if timing is None else f"{timing.request_count}/{timing.failed_request_count}"
        lines.append(
            f"| `{item.model_id}` | `{item.prompt_id}` | `{item.reasoning_mode_id}` | {measured} | "
            f"{format_seconds(item.inference_duration_seconds)} | "
            f"{format_seconds(timing.fresh_inference_duration_seconds if timing else None)} | "
            f"{calls} | {format_seconds(timing.request_wall_seconds if timing else None)} | "
            f"{format_seconds(item.elapsed_duration_seconds)} |"
        )
    lines.extend(["", "## Regression diagnostics", ""])
    failures = [item for item in report.candidates if item.regressions]
    if not failures:
        lines.append("No threshold violations were detected.")
    for item in failures:
        lines.append(f"### {item.prompt_id} / {item.model_id} / {item.reasoning_mode_id}")
        lines.extend(f"- {message}" for message in item.regressions)
        lines.append("")
    failures_with_categories = [item for item in report.candidates if item.failure_categories]
    if failures_with_categories:
        lines.extend(["## Failure diagnostics", ""])
        for item in failures_with_categories:
            lines.append(f"### {item.prompt_id} / {item.model_id} / {item.reasoning_mode_id}")
            lines.extend(
                f"- `{category}`: {count}"
                for category, count in sorted(item.failure_categories.items())
            )
            if item.top_failure_messages:
                lines.append("- Frequent messages:")
                lines.extend(f"  - {message}" for message in item.top_failure_messages)
            lines.append("")

    if report.diagnostics:
        lines.extend(["## Matrix diagnostics", ""])
        lines.extend(f"- {message}" for message in report.diagnostics)
    return "\n".join(lines).rstrip() + "\n"
