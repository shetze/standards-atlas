"""Execution and comparison of semantic prompt/model evaluations."""

from __future__ import annotations

from collections.abc import Iterable

from standards_atlas.application.ports.llm_gateway import (
    LlmGateway,
    StructuredGenerationRequest,
)
from standards_atlas.application.semantic_evaluation.metrics import (
    calculate_metrics,
    empty_metrics,
)
from standards_atlas.application.semantic_evaluation.models import (
    AggregateMetrics,
    EvaluationCaseResult,
    EvaluationRun,
    GoldenDataset,
    PromptDefinition,
    RegressionResult,
)
from standards_atlas.application.semantic_evaluation.schema import validate_schema


class SemanticEvaluationRunner:
    def __init__(self, gateway: LlmGateway) -> None:
        self._gateway = gateway

    def run(
        self,
        prompt: PromptDefinition,
        dataset: GoldenDataset,
        *,
        model: str | None = None,
    ) -> EvaluationRun:
        cases = tuple(self._run_case(prompt, example, model) for example in dataset.examples)
        provider = cases[0].provider if cases else "unknown"
        resolved_model = cases[0].model if cases else (model or "unknown")
        return EvaluationRun(
            task=prompt.task,
            prompt_version=prompt.version,
            dataset_version=dataset.version,
            model=resolved_model,
            provider=provider,
            metrics=_aggregate(cases),
            cases=cases,
        )

    def benchmark(
        self,
        prompt: PromptDefinition,
        dataset: GoldenDataset,
        models: Iterable[str],
    ) -> tuple[EvaluationRun, ...]:
        """Compare models under an identical prompt and gold dataset."""
        return tuple(self.run(prompt, dataset, model=model) for model in models)

    def benchmark_prompts(
        self,
        prompts: Iterable[PromptDefinition],
        dataset: GoldenDataset,
        *,
        model: str | None = None,
    ) -> tuple[EvaluationRun, ...]:
        """Compare prompt versions under an identical model and gold dataset."""
        return tuple(self.run(prompt, dataset, model=model) for prompt in prompts)

    def _run_case(self, prompt, example, model):
        user_prompt = prompt.user_template.format(**example.input)
        request = StructuredGenerationRequest(
            task=prompt.task,
            system_prompt=prompt.system_prompt,
            user_prompt=user_prompt,
            output_schema=prompt.output_schema,
            prompt_version=prompt.version,
            model=model,
            temperature=0.0,
            seed=0,
            metadata={"example_id": example.id, "dataset_version": "golden"},
        )
        try:
            result = self._gateway.generate_structured(request)
            output = dict(result.value)
            schema_valid, schema_error = validate_schema(output, prompt.output_schema)
            metrics = (
                calculate_metrics(output, example.expected) if schema_valid else empty_metrics()
            )
            return EvaluationCaseResult(
                example.id,
                output,
                example.expected,
                True,
                schema_valid,
                metrics,
                result.model,
                result.provider,
                result.prompt_version,
                result.duration_ms,
                result.input_hash,
                result.raw_response_hash,
                schema_error,
            )
        except Exception as exc:
            return EvaluationCaseResult(
                example.id,
                None,
                example.expected,
                False,
                False,
                empty_metrics(),
                model or "unknown",
                "unknown",
                prompt.version,
                0,
                "",
                "",
                f"{type(exc).__name__}: {exc}",
            )


def compare_runs(
    baseline: EvaluationRun,
    candidate: EvaluationRun,
    *,
    tolerance: float = 0.0,
) -> RegressionResult:
    regressions = []
    for name in ("schema_valid_rate", "exact_match_rate", "precision", "recall", "f1"):
        before = getattr(baseline.metrics, name)
        after = getattr(candidate.metrics, name)
        if after + tolerance < before:
            regressions.append(f"{name} regressed from {before:.4f} to {after:.4f}")
    baseline_cases = {case.example_id: case for case in baseline.cases}
    for case in candidate.cases:
        previous = baseline_cases.get(case.example_id)
        if previous and previous.metrics.f1 > case.metrics.f1 + tolerance:
            regressions.append(
                f"case {case.example_id} f1 regressed "
                f"from {previous.metrics.f1:.4f} to {case.metrics.f1:.4f}"
            )
    return RegressionResult(passed=not regressions, regressions=tuple(regressions))


def _aggregate(cases: tuple[EvaluationCaseResult, ...]) -> AggregateMetrics:
    count = len(cases)
    if not count:
        return AggregateMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, None, None, 0.0)
    confidences = [case.metrics.confidence for case in cases if case.metrics.confidence is not None]
    return AggregateMetrics(
        cases=count,
        valid_json_rate=sum(case.valid_json for case in cases) / count,
        schema_valid_rate=sum(case.schema_valid for case in cases) / count,
        exact_match_rate=sum(case.metrics.exact_match for case in cases) / count,
        precision=sum(case.metrics.precision for case in cases) / count,
        recall=sum(case.metrics.recall for case in cases) / count,
        f1=sum(case.metrics.f1 for case in cases) / count,
        confidence_coverage=len(confidences) / count,
        mean_confidence=sum(confidences) / len(confidences) if confidences else None,
        min_confidence=min(confidences) if confidences else None,
        max_confidence=max(confidences) if confidences else None,
        mean_duration_ms=sum(case.duration_ms for case in cases) / count,
    )
