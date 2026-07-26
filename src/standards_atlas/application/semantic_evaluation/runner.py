"""Reusable semantic evaluation runner."""

from __future__ import annotations

from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest

from .metrics import aggregate_metrics, compare_fields
from .models import EvaluationCaseResult, EvaluationReport, GoldenCorpus, PromptDefinition
from .schema import SchemaValidationError, validate_json_schema


class SemanticEvaluationRunner:
    """Run identical prompt/corpus inputs against any configured LLM gateway."""

    def __init__(self, gateway: LlmGateway) -> None:
        self._gateway = gateway

    def run(
        self,
        prompt: PromptDefinition,
        corpus: GoldenCorpus,
        *,
        model: str,
        seed: int | None = 0,
        temperature: float = 0.0,
    ) -> EvaluationReport:
        if prompt.task != corpus.task:
            raise ValueError(
                f"prompt task {prompt.task!r} does not match corpus task {corpus.task!r}"
            )
        results = tuple(
            self._run_case(prompt, case, model, seed=seed, temperature=temperature)
            for case in corpus.cases
        )
        return EvaluationReport(
            task=prompt.task,
            prompt_id=prompt.identifier,
            prompt_version=prompt.version,
            corpus_id=corpus.identifier,
            corpus_version=corpus.version,
            requested_model=model,
            metrics=aggregate_metrics(results),
            cases=results,
        )

    def _run_case(self, prompt, case, model, *, seed, temperature):
        request = StructuredGenerationRequest(
            task=prompt.task,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.render(case.input),
            output_schema=prompt.output_schema,
            prompt_version=prompt.version,
            model=model,
            seed=seed,
            temperature=temperature,
            metadata={"prompt_id": prompt.identifier, "corpus_case": case.identifier},
        )
        try:
            generated = self._gateway.generate_structured(request)
            schema_valid = True
            error = None
            try:
                validate_json_schema(generated.value, prompt.output_schema)
            except SchemaValidationError as exception:
                schema_valid = False
                error = str(exception)
            field_scores = compare_fields(generated.value, case.expected) if schema_valid else {}
            usage = generated.usage
            return EvaluationCaseResult(
                case_id=case.identifier,
                output=generated.value,
                expected=case.expected,
                schema_valid=schema_valid,
                exact_match=schema_valid and dict(generated.value) == dict(case.expected),
                field_scores=field_scores,
                model=generated.model,
                provider=generated.provider,
                prompt_version=generated.prompt_version,
                input_hash=generated.input_hash,
                raw_response_hash=generated.raw_response_hash,
                duration_ms=generated.duration_ms,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                cached=generated.cached,
                error=error,
            )
        except Exception as exception:
            return EvaluationCaseResult(
                case_id=case.identifier,
                output=None,
                expected=case.expected,
                schema_valid=False,
                exact_match=False,
                field_scores={},
                model=model,
                provider="unknown",
                prompt_version=prompt.version,
                input_hash="",
                raw_response_hash="",
                duration_ms=0,
                error=f"{type(exception).__name__}: {exception}",
            )
