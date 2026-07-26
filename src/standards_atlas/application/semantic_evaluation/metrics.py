"""Task-neutral comparison and aggregation functions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import EvaluationCaseResult, EvaluationMetrics, EvaluationReport, RegressionDelta


def compare_fields(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, float]:
    return {key: float(actual.get(key) == value) for key, value in expected.items()}


def aggregate_metrics(cases: tuple[EvaluationCaseResult, ...]) -> EvaluationMetrics:
    count = len(cases)
    if count == 0:
        return EvaluationMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0)
    field_values = [score for case in cases for score in case.field_scores.values()]
    token_values = [case.total_tokens for case in cases if case.total_tokens is not None]
    return EvaluationMetrics(
        case_count=count,
        successful_cases=sum(case.error is None for case in cases),
        json_schema_validity=sum(case.schema_valid for case in cases) / count,
        exact_match_rate=sum(case.exact_match for case in cases) / count,
        field_accuracy=sum(field_values) / len(field_values) if field_values else 0.0,
        mean_duration_ms=sum(case.duration_ms for case in cases) / count,
        total_tokens=sum(token_values) if token_values else None,
    )


def compare_reports(baseline: EvaluationReport, candidate: EvaluationReport) -> RegressionDelta:
    baseline_cases = {case.case_id: case for case in baseline.cases}
    regressed = tuple(
        case.case_id
        for case in candidate.cases
        if case.case_id in baseline_cases
        and baseline_cases[case.case_id].exact_match
        and not case.exact_match
    )
    return RegressionDelta(
        exact_match_delta=candidate.metrics.exact_match_rate - baseline.metrics.exact_match_rate,
        schema_validity_delta=(
            candidate.metrics.json_schema_validity - baseline.metrics.json_schema_validity
        ),
        field_accuracy_delta=candidate.metrics.field_accuracy - baseline.metrics.field_accuracy,
        regressed_case_ids=regressed,
    )
