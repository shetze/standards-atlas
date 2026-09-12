from __future__ import annotations

import json
from pathlib import Path

import pytest

from standards_atlas.application.ports.llm_gateway import (
    LlmResponseError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.batch import (
    ProposalBatchExecutor,
    ProposalItemOutcome,
)
from standards_atlas.application.semantic_qualification.performance import (
    MeasuredLlmGateway,
    RequestTiming,
    aggregate_performance,
    measured_seconds,
    observation_performance_fields,
)
from standards_atlas.application.semantic_qualification.proposals import (
    historical_inference_duration,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
)
from standards_atlas.application.semantic_qualification.retry import generate_with_retry


def observation(**values) -> MatrixObservation:
    return MatrixObservation(
        prompt_id="prompt",
        model_id="model",
        repetition=1,
        qualification_report=Path("not-used.json"),
        **values,
    )


@pytest.mark.parametrize("value", [None, -1, float("inf"), float("nan"), "invalid", True])
def test_bad_historical_durations_are_unknown(value: object) -> None:
    assert measured_seconds(value) is None


def test_valid_zero_duration_is_not_unknown() -> None:
    assert measured_seconds(0) == 0.0


def test_batch_failure_retains_measured_response_cost() -> None:
    timing = RequestTiming(
        request_count=1,
        fresh_response_count=1,
        fresh_measured_request_count=1,
        fresh_inference_duration_seconds=2.0,
    )
    result = ProposalBatchExecutor().execute(
        [1],
        lambda *_: ProposalItemOutcome(
            False,
            "schema failed",
            fresh_predictions=1,
            fresh_inference_duration_seconds=2.0,
            request_timing=timing,
        ),
    )
    assert result.generated == 0
    assert result.failed == 1
    assert result.fresh_predictions == 1
    assert result.fresh_inference_duration_seconds == 2.0
    assert result.request_timing == timing


def test_gateway_measures_retries_but_does_not_invent_failed_provider_time(monkeypatch) -> None:
    ticks = iter([0.0, 4.0, 4.0, 6.0])
    monkeypatch.setattr(
        "standards_atlas.application.semantic_qualification.performance.time.monotonic",
        lambda: next(ticks),
    )

    class Gateway:
        def __init__(self):
            self.calls = 0

        def generate_structured(self, request):
            self.calls += 1
            if self.calls == 1:
                raise LlmResponseError("truncated", finish_reason="length")
            return StructuredGenerationResult({}, "model", "fake", "v1", "i", "r", 2000)

    gateway = MeasuredLlmGateway(Gateway())
    request = StructuredGenerationRequest("task", "system", "user", {}, "v1", max_tokens=32)
    generate_with_retry(
        gateway,
        request,
        attempts=1,
        backoff_seconds=0,
        retry_timeouts=False,
        truncation_retry_max_tokens=64,
    )
    assert gateway.timing.request_count == 2
    assert gateway.timing.failed_request_count == 1
    assert gateway.timing.failed_request_wall_seconds == 4.0
    assert gateway.timing.request_wall_seconds == 6.0
    assert gateway.timing.fresh_inference_duration_seconds == 2.0
    assert gateway.timing.fresh_measured_request_count == 1


def test_cache_duration_is_historical_not_fresh() -> None:
    class Gateway:
        def generate_structured(self, request):
            return StructuredGenerationResult(
                {}, "model", "fake", "v1", "i", "r", 5000, cached=True
            )

    gateway = MeasuredLlmGateway(Gateway())
    gateway.generate_structured(StructuredGenerationRequest("task", "s", "u", {}, "v1"))
    assert gateway.timing.fresh_inference_duration_seconds is None
    assert gateway.timing.cached_historical_inference_duration_seconds == 5.0
    assert gateway.timing.cached_measured_request_count == 1


def test_mean_is_per_measured_request_not_per_batch_or_wall_time() -> None:
    fields = observation_performance_fields(
        timing=RequestTiming(
            request_count=100,
            fresh_response_count=100,
            fresh_measured_request_count=100,
            fresh_inference_duration_seconds=500,
        ),
        historical_count=100,
        historical_seconds=500,
        elapsed_seconds=700,
        recompute=False,
    )
    assert fields["mean_duration_seconds"] == 5
    assert fields["inference_duration_seconds"] == 500
    assert fields["elapsed_duration_seconds"] == 700


def test_mixed_fresh_and_reused_durations_have_separate_denominators() -> None:
    fields = observation_performance_fields(
        timing=RequestTiming(
            request_count=3,
            fresh_response_count=2,
            cached_response_count=1,
            fresh_measured_request_count=2,
            fresh_inference_duration_seconds=4,
        ),
        historical_count=100,
        historical_seconds=900,
        elapsed_seconds=20,
        recompute=False,
    )
    assert fields["mean_duration_seconds"] == 2
    assert fields["measured_request_count"] == 2
    assert fields["historical_measured_request_count"] == 100


def test_weighted_request_mean_across_unequal_batches() -> None:
    result = aggregate_performance(
        [
            observation(
                measured_request_count=1,
                inference_duration_seconds=10,
                performance_measurement_source="fresh",
            ),
            observation(
                measured_request_count=9,
                inference_duration_seconds=18,
                performance_measurement_source="fresh",
            ),
        ]
    )
    assert result["mean_duration_seconds"] == 2.8
    assert result["inference_duration_seconds"] == 28
    assert result["measured_request_count"] == 10
    assert result["elapsed_duration_seconds"] is None
    assert result["request_timing_complete"] is False


@pytest.mark.parametrize("source", ["fresh", "recompute_historical", "historical_mixed"])
def test_legacy_automatic_batch_sum_is_ineligible_without_denominator(source: str) -> None:
    result = aggregate_performance(
        [observation(mean_duration_seconds=5873, performance_measurement_source=source)]
    )
    assert result["mean_duration_seconds"] is None
    assert result["performance_measurement_source"] == "not_measured"


def test_resume_uses_recorded_inference_without_claiming_fresh_work(tmp_path: Path) -> None:
    case = tmp_path / "one"
    case.mkdir()
    timing = RequestTiming(
        request_count=2,
        fresh_response_count=2,
        fresh_measured_request_count=2,
        fresh_inference_duration_seconds=3,
    )
    (case / "request-timing.json").write_text(timing.model_dump_json())
    count, seconds = historical_inference_duration(tmp_path, ["one", "missing"])
    fields = observation_performance_fields(
        timing=RequestTiming(),
        historical_count=count,
        historical_seconds=seconds,
        elapsed_seconds=0.02,
        recompute=True,
    )
    assert fields["mean_duration_seconds"] == 1.5
    assert fields["request_timing"].request_count == 0
    assert fields["performance_measurement_source"] == "recompute_historical"


def test_old_adaptive_interview_is_not_mistaken_for_single_request_total(tmp_path: Path) -> None:
    case = tmp_path / "one"
    case.mkdir()
    (case / "response.json").write_text(json.dumps({"duration_ms": 1000}))
    (case / "interview.json").write_text("{}")
    assert historical_inference_duration(tmp_path, ["one"]) == (0, None)


def test_new_failed_execution_does_not_reuse_old_response_duration(tmp_path: Path) -> None:
    case = tmp_path / "one"
    case.mkdir()
    (case / "response.json").write_text(json.dumps({"duration_ms": 999999}))
    (case / "request-timing.json").write_text(
        RequestTiming(request_count=1, failed_request_count=1).model_dump_json()
    )
    assert historical_inference_duration(tmp_path, ["one"]) == (0, None)
