"""Aggregation of repeated semantic qualification observations."""

from __future__ import annotations

from statistics import fmean, pstdev
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from standards_atlas.application.semantic_qualification.qualification import (
        AnnotationQualificationReport,
    )
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CandidateQualification,
        MatrixObservation,
        ModelCandidate,
        ReasoningMode,
        RegressionThresholds,
    )


def aggregate_candidate(
    prompt_id: str,
    model: ModelCandidate,
    reasoning_mode: ReasoningMode,
    entries: list[tuple[MatrixObservation, AnnotationQualificationReport]],
    expected_repetitions: int,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    """Aggregate repeated reports for one model/prompt/reasoning candidate."""
    if reasoning_mode.id not in model.supported_reasoning_modes:
        return empty_candidate(
            prompt_id, model, reasoning_mode, expected_repetitions, status="unsupported"
        )
    if not entries:
        return empty_candidate(
            prompt_id, model, reasoning_mode, expected_repetitions, status="not_executed"
        )

    regressions: list[str] = []
    complete = len(entries) == expected_repetitions
    if not complete:
        regressions.append(
            f"completed repetitions {len(entries)} != expected {expected_repetitions}"
        )

    gold_available = any(report.gold_agreement.eligible > 0 for _, report in entries)
    gold_entries = [report for _, report in entries if report.gold_agreement.eligible > 0]
    f1_values = [report.gold_agreement.micro_f1 for report in gold_entries]
    coverage_values = [report.gold_agreement.coverage for report in gold_entries]
    silver_values = [report.silver_agreement.micro_f1 for _, report in entries]
    structure_values = [report.structure_agreement.micro_f1 for _, report in entries]
    success_values = [report.reliability.prediction_success_rate for _, report in entries]
    json_values = [report.reliability.json_validity_rate for _, report in entries]
    truncation_values = [report.reliability.truncation_rate for _, report in entries]
    durations = [
        item.mean_duration_seconds
        for item, _ in entries
        if item.mean_duration_seconds is not None
        and item.performance_measurement_source != "not_measured"
    ]
    memory = [item.peak_memory_gb for item, _ in entries if item.peak_memory_gb is not None]
    measurement_sources = {item.performance_measurement_source for item, _ in entries}
    fresh_prediction_counts = [item.fresh_prediction_count for item, _ in entries]
    fresh_prediction_count = (
        None
        if any(value is None for value in fresh_prediction_counts)
        else sum(value or 0 for value in fresh_prediction_counts)
    )
    cached_prediction_count = sum(item.cached_prediction_count for item, _ in entries)
    reused_prediction_count = sum(item.reused_prediction_count for item, _ in entries)

    mean_f1 = fmean(f1_values) if f1_values else None
    minimum_f1 = min(f1_values) if f1_values else None
    stddev = pstdev(f1_values) if len(f1_values) > 1 else (0.0 if f1_values else None)
    mean_coverage = fmean(coverage_values) if coverage_values else None
    mean_duration = fmean(durations) if durations else None
    peak_memory = max(memory) if memory else model.declared_memory_gb
    if len(measurement_sources) == 1:
        performance_measurement_source = next(iter(measurement_sources))
    else:
        performance_measurement_source = "mixed"

    if gold_available:
        assert mean_f1 is not None
        assert mean_coverage is not None
        assert stddev is not None
        if mean_f1 < thresholds.min_gold_f1:
            regressions.append(f"mean Gold F1 {mean_f1:.4f} < {thresholds.min_gold_f1:.4f}")
        if mean_coverage < thresholds.min_gold_coverage:
            regressions.append(
                f"mean Gold coverage {mean_coverage:.4f} < {thresholds.min_gold_coverage:.4f}"
            )
        if stddev > thresholds.max_gold_f1_stddev:
            regressions.append(f"Gold F1 stddev {stddev:.4f} > {thresholds.max_gold_f1_stddev:.4f}")

    mean_success = fmean(success_values) if success_values else 0.0
    mean_json = fmean(json_values) if json_values else 0.0
    mean_truncation = fmean(truncation_values) if truncation_values else 0.0
    if mean_success < thresholds.min_prediction_success_rate:
        regressions.append(
            f"prediction success rate {mean_success:.4f} < "
            f"{thresholds.min_prediction_success_rate:.4f}"
        )
    if mean_json < thresholds.min_json_validity_rate:
        regressions.append(
            f"JSON validity rate {mean_json:.4f} < {thresholds.min_json_validity_rate:.4f}"
        )
    if mean_truncation > thresholds.max_truncation_rate:
        regressions.append(
            f"truncation rate {mean_truncation:.4f} > {thresholds.max_truncation_rate:.4f}"
        )
    if thresholds.max_mean_duration_seconds is not None and mean_duration is None:
        regressions.append("fresh inference performance not measured")
    if (
        thresholds.max_mean_duration_seconds is not None
        and mean_duration is not None
        and mean_duration > thresholds.max_mean_duration_seconds
    ):
        regressions.append(
            f"mean duration {mean_duration:.3f}s > {thresholds.max_mean_duration_seconds:.3f}s"
        )
    if (
        thresholds.max_peak_memory_gb is not None
        and peak_memory is not None
        and peak_memory > thresholds.max_peak_memory_gb
    ):
        regressions.append(
            f"peak memory {peak_memory:.3f}GB > {thresholds.max_peak_memory_gb:.3f}GB"
        )

    failure_categories: dict[str, int] = {}
    messages: dict[str, int] = {}
    for _, report in entries:
        for item in report.reliability.failure_categories:
            failure_categories[item.category] = (
                failure_categories.get(item.category, 0) + item.count
            )
        for item in report.reliability.top_failure_messages:
            messages[item.message] = messages.get(item.message, 0) + item.count

    status = "passed" if complete and not regressions else "failed" if complete else "incomplete"
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CandidateQualification,
    )

    return CandidateQualification(
        prompt_id=prompt_id,
        model_id=model.id,
        provider=model.provider,
        reasoning_mode_id=reasoning_mode.id,
        reasoning_optional=reasoning_mode.optional,
        expected_repetitions=expected_repetitions,
        completed_repetitions=len(entries),
        status=status,
        qualification_eligible=complete,
        mean_gold_f1=mean_f1,
        min_gold_f1=minimum_f1,
        gold_f1_stddev=stddev,
        mean_gold_coverage=mean_coverage,
        mean_silver_f1=fmean(silver_values) if silver_values else 0.0,
        mean_structure_f1=fmean(structure_values) if structure_values else 0.0,
        mean_prediction_success_rate=mean_success,
        mean_json_validity_rate=mean_json,
        mean_truncation_rate=mean_truncation,
        mean_duration_seconds=mean_duration,
        performance_measurement_source=performance_measurement_source,
        fresh_prediction_count=fresh_prediction_count,
        cached_prediction_count=cached_prediction_count,
        reused_prediction_count=reused_prediction_count,
        peak_memory_gb=peak_memory,
        passed=status == "passed",
        regressions=tuple(regressions),
        failure_categories=failure_categories,
        top_failure_messages=tuple(
            message for message, _ in sorted(messages.items(), key=lambda item: -item[1])[:10]
        ),
    )


def empty_candidate(
    prompt_id: str,
    model: ModelCandidate,
    reasoning_mode: ReasoningMode,
    expected_repetitions: int,
    *,
    status: str,
) -> CandidateQualification:
    """Create an unrankable candidate for unsupported or missing runs."""
    from standards_atlas.application.semantic_qualification.qualification_matrix import (
        CandidateQualification,
    )

    return CandidateQualification(
        prompt_id=prompt_id,
        model_id=model.id,
        provider=model.provider,
        reasoning_mode_id=reasoning_mode.id,
        reasoning_optional=reasoning_mode.optional,
        expected_repetitions=expected_repetitions,
        completed_repetitions=0,
        status=status,
        qualification_eligible=False,
        mean_gold_f1=None,
        min_gold_f1=None,
        gold_f1_stddev=None,
        mean_gold_coverage=None,
        mean_silver_f1=0.0,
        mean_structure_f1=0.0,
        mean_prediction_success_rate=0.0,
        mean_json_validity_rate=0.0,
        mean_truncation_rate=0.0,
        performance_measurement_source="not_measured",
        fresh_prediction_count=0,
        cached_prediction_count=0,
        reused_prediction_count=0,
        peak_memory_gb=model.declared_memory_gb,
        passed=False,
    )
