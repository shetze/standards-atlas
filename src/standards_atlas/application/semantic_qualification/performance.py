"""Measured request costs, kept separate from historical and orchestration time."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    LlmHealth,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class RequestTiming(BaseModel):
    """Costs of actual gateway calls, including retries and failed attempts.

    Provider inference durations exist only for returned, timed responses.
    An exception has measured wall time, NOT an inferred provider duration.
    Cache entries carry historical inference time, never fresh inference cost.
    """

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    request_count: int = Field(default=0, ge=0)
    failed_request_count: int = Field(default=0, ge=0)
    fresh_response_count: int = Field(default=0, ge=0)
    cached_response_count: int = Field(default=0, ge=0)
    fresh_measured_request_count: int = Field(default=0, ge=0)
    cached_measured_request_count: int = Field(default=0, ge=0)
    fresh_inference_duration_seconds: float | None = Field(default=None, ge=0)
    cached_historical_inference_duration_seconds: float | None = Field(default=None, ge=0)
    request_wall_seconds: float = Field(default=0.0, ge=0)
    failed_request_wall_seconds: float = Field(default=0.0, ge=0)

    def plus(self, other: RequestTiming) -> RequestTiming:
        """Combine disjoint executions, preserving unknown provider durations."""
        values = {}
        for field in type(self).model_fields:
            if field == "schema_version":
                continue
            left, right = getattr(self, field), getattr(other, field)
            values[field] = None if left is None and right is None else (left or 0) + (right or 0)
        return RequestTiming(**values)

    @property
    def measured_request_count(self) -> int:
        return self.fresh_measured_request_count + self.cached_measured_request_count

    @property
    def recorded_inference_duration_seconds(self) -> float | None:
        if not self.measured_request_count:
            return None
        return (self.fresh_inference_duration_seconds or 0) + (
            self.cached_historical_inference_duration_seconds or 0
        )


class MeasuredLlmGateway:
    """Observe the existing gateway without changing retry or generation policy."""

    def __init__(self, gateway: LlmGateway) -> None:
        self.gateway = gateway
        self.timing = RequestTiming()

    def health(self) -> LlmHealth:
        return self.gateway.health()

    def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResult:
        started = time.monotonic()
        try:
            result = self.gateway.generate_structured(request)
        except Exception:
            elapsed = time.monotonic() - started
            self.timing = self.timing.plus(
                RequestTiming(
                    request_count=1,
                    failed_request_count=1,
                    request_wall_seconds=elapsed,
                    failed_request_wall_seconds=elapsed,
                )
            )
            raise
        elapsed = time.monotonic() - started
        duration = measured_seconds(result.duration_ms)
        self.timing = self.timing.plus(
            RequestTiming(
                request_count=1,
                fresh_response_count=int(not result.cached),
                cached_response_count=int(result.cached),
                fresh_measured_request_count=int(not result.cached and duration is not None),
                cached_measured_request_count=int(result.cached and duration is not None),
                fresh_inference_duration_seconds=duration if not result.cached else None,
                cached_historical_inference_duration_seconds=duration if result.cached else None,
                request_wall_seconds=elapsed,
            )
        )
        return result


def measured_seconds(duration_ms: object) -> float | None:
    """Reject absent, negative and non-finite historical measurements."""
    if duration_ms is None or isinstance(duration_ms, bool):
        return None
    try:
        value = float(duration_ms) / 1000.0
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def stored_request_timing(path: Path) -> RequestTiming:
    return RequestTiming.model_validate(json.loads(path.read_text(encoding="utf-8")))


def observation_performance_fields(
    *,
    timing: RequestTiming | None,
    historical_count: int,
    historical_seconds: float | None,
    elapsed_seconds: float,
    recompute: bool,
) -> dict[str, object]:
    """Build explicitly denominated timing fields for a matrix observation."""
    if timing is not None and timing.fresh_measured_request_count:
        count = timing.fresh_measured_request_count
        seconds = timing.fresh_inference_duration_seconds
        source = "fresh"
    elif historical_count and historical_seconds is not None:
        count, seconds = historical_count, historical_seconds
        source = "recompute_historical" if recompute else "historical_mixed"
    else:
        count, seconds, source = 0, None, "not_measured"
    return {
        "mean_duration_seconds": seconds / count if count and seconds is not None else None,
        "inference_duration_seconds": seconds,
        "measured_request_count": count,
        "historical_measured_request_count": historical_count,
        "historical_inference_duration_seconds": historical_seconds,
        "elapsed_duration_seconds": elapsed_seconds,
        "performance_measurement_source": source,
        "request_timing": timing,
    }


def aggregate_performance(observations: list[object]) -> dict[str, object]:
    """Pool timed samples by request count; never average batch sums.

    Historical automatic observations without an explicit denominator are
    ambiguous and ineligible for latency thresholds. Legacy *declared* means
    remain readable, but are never silently mixed with weighted measurements.
    """
    measured = [
        item
        for item in observations
        if getattr(item, "measured_request_count", 0)
        and getattr(item, "inference_duration_seconds", None) is not None
        and item.performance_measurement_source != "not_measured"
    ]
    count = sum(item.measured_request_count for item in measured)
    seconds = sum(item.inference_duration_seconds for item in measured) if measured else None
    declared = [
        item.mean_duration_seconds
        for item in observations
        if item.performance_measurement_source == "legacy"
        and item.mean_duration_seconds is not None
    ]
    mean = (
        seconds / count
        if count and seconds is not None
        else (sum(declared) / len(declared) if declared else None)
    )
    sources = {item.performance_measurement_source for item in measured}
    source = (
        next(iter(sources))
        if len(sources) == 1
        else "mixed"
        if sources
        else ("legacy_declared_mean" if declared else "not_measured")
    )
    timing = None
    for item in observations:
        if item.request_timing is not None:
            timing = (timing or RequestTiming()).plus(item.request_timing)
    elapsed = [item.elapsed_duration_seconds for item in observations]
    historical = [item.historical_inference_duration_seconds for item in observations]
    historical_counts = [item.historical_measured_request_count for item in observations]
    return {
        "mean_duration_seconds": mean,
        "inference_duration_seconds": seconds,
        "measured_request_count": count if measured else None,
        "performance_measurement_source": source,
        "request_timing": timing,
        "timing_observation_count": len(measured),
        "request_timing_complete": all(item.request_timing is not None for item in observations),
        "elapsed_duration_seconds": (
            sum(elapsed) if all(value is not None for value in elapsed) else None
        ),
        "historical_inference_duration_seconds": (
            sum(historical) if all(value is not None for value in historical) else None
        ),
        "historical_measured_request_count": (
            sum(historical_counts)
            if all(value is not None for value in historical_counts)
            else None
        ),
    }
