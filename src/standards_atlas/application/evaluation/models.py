"""Domain-neutral models for reproducible evaluation runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

JsonObject = Mapping[str, Any]


@dataclass(frozen=True)
class PromptDefinition:
    task: str
    version: str
    system_prompt: str
    user_template: str
    output_schema: JsonObject
    description: str = ""


@dataclass(frozen=True)
class EvaluationExample:
    id: str
    input: JsonObject
    expected: JsonObject
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationDataset:
    task: str
    version: str
    examples: tuple[EvaluationExample, ...]


@dataclass(frozen=True)
class ExampleMetrics:
    exact_match: bool
    precision: float
    recall: float
    f1: float
    confidence: float | None = None


@dataclass(frozen=True)
class EvaluationCaseResult:
    example_id: str
    output: JsonObject | None
    expected: JsonObject
    valid_json: bool
    schema_valid: bool
    metrics: ExampleMetrics
    model: str
    provider: str
    prompt_version: str
    duration_ms: int
    input_hash: str
    raw_response_hash: str
    error: str | None = None


@dataclass(frozen=True)
class AggregateMetrics:
    cases: int
    valid_json_rate: float
    schema_valid_rate: float
    exact_match_rate: float
    precision: float
    recall: float
    f1: float
    confidence_coverage: float
    mean_confidence: float | None
    min_confidence: float | None
    max_confidence: float | None
    mean_duration_ms: float


@dataclass(frozen=True)
class EvaluationRun:
    task: str
    prompt_version: str
    dataset_version: str
    model: str
    provider: str
    metrics: AggregateMetrics
    cases: tuple[EvaluationCaseResult, ...]
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class RegressionResult:
    passed: bool
    regressions: tuple[str, ...]


# Backwards-compatible terminology for existing semantic evaluation clients.
GoldenExample = EvaluationExample
GoldenDataset = EvaluationDataset
