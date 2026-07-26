"""Provider-independent models for semantic LLM evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

JsonObject = Mapping[str, Any]


@dataclass(frozen=True)
class PromptDefinition:
    """Immutable, versioned prompt and its expected structured output."""

    identifier: str
    version: str
    task: str
    system_prompt: str
    user_template: str
    output_schema: JsonObject
    description: str = ""

    def render(self, variables: Mapping[str, str]) -> str:
        try:
            return self.user_template.format_map(dict(variables))
        except KeyError as error:
            raise ValueError(f"missing prompt variable: {error.args[0]}") from error


@dataclass(frozen=True)
class GoldenCorpusCase:
    """One reviewed input and expected result in a semantic golden corpus."""

    identifier: str
    input: Mapping[str, str]
    expected: JsonObject
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoldenCorpus:
    """Versioned collection of reviewed semantic examples."""

    identifier: str
    version: str
    task: str
    cases: tuple[GoldenCorpusCase, ...]


@dataclass(frozen=True)
class EvaluationCaseResult:
    """Result and provenance for one evaluated corpus case."""

    case_id: str
    output: JsonObject | None
    expected: JsonObject
    schema_valid: bool
    exact_match: bool
    field_scores: Mapping[str, float]
    model: str
    provider: str
    prompt_version: str
    input_hash: str
    raw_response_hash: str
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached: bool = False
    error: str | None = None


@dataclass(frozen=True)
class EvaluationMetrics:
    """Aggregated, reproducible metrics for an evaluation run."""

    case_count: int
    successful_cases: int
    json_schema_validity: float
    exact_match_rate: float
    field_accuracy: float
    mean_duration_ms: float
    total_tokens: int | None


@dataclass(frozen=True)
class EvaluationReport:
    """Persistable evidence produced by one prompt/model/corpus run."""

    task: str
    prompt_id: str
    prompt_version: str
    corpus_id: str
    corpus_version: str
    requested_model: str
    metrics: EvaluationMetrics
    cases: tuple[EvaluationCaseResult, ...]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass(frozen=True)
class RegressionDelta:
    """Metric differences between a baseline and candidate report."""

    exact_match_delta: float
    schema_validity_delta: float
    field_accuracy_delta: float
    regressed_case_ids: tuple[str, ...]

    @property
    def has_regression(self) -> bool:
        return bool(self.regressed_case_ids) or any(
            value < 0
            for value in (
                self.exact_match_delta,
                self.schema_validity_delta,
                self.field_accuracy_delta,
            )
        )
