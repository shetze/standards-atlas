from dataclasses import replace

from standards_atlas.application.semantic_evaluation import (
    EvaluationCaseResult,
    EvaluationReport,
    aggregate_metrics,
    compare_reports,
)


def _case(identifier: str, exact: bool):
    return EvaluationCaseResult(
        case_id=identifier,
        output={"value": exact},
        expected={"value": True},
        schema_valid=True,
        exact_match=exact,
        field_scores={"value": float(exact)},
        model="model",
        provider="fake",
        prompt_version="1",
        input_hash="input",
        raw_response_hash="response",
        duration_ms=5,
    )


def _report(cases):
    cases = tuple(cases)
    return EvaluationReport(
        task="task",
        prompt_id="prompt",
        prompt_version="1",
        corpus_id="corpus",
        corpus_version="1",
        requested_model="model",
        metrics=aggregate_metrics(cases),
        cases=cases,
    )


def test_compare_reports_identifies_case_and_metric_regressions():
    baseline = _report([_case("one", True), _case("two", True)])
    candidate = _report([_case("one", False), _case("two", True)])

    delta = compare_reports(baseline, candidate)

    assert delta.has_regression
    assert delta.regressed_case_ids == ("one",)
    assert delta.exact_match_delta == -0.5


def test_no_regression_when_candidate_improves():
    baseline_case = replace(_case("one", False), schema_valid=False)
    baseline = _report([baseline_case])
    candidate = _report([_case("one", True)])

    assert not compare_reports(baseline, candidate).has_regression
