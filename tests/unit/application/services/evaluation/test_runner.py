from standards_atlas.application.ports.llm_gateway import (
    StructuredGenerationResult,
    TokenUsage,
)
from standards_atlas.application.services.evaluation.models import (
    GoldenDataset,
    GoldenExample,
    PromptDefinition,
)
from standards_atlas.application.services.evaluation.runner import (
    SemanticEvaluationRunner,
    compare_runs,
)


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def generate_structured(self, request):
        return StructuredGenerationResult(
            value=next(self.outputs),
            model=request.model or "granite",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=10,
            usage=TokenUsage(total_tokens=20),
        )


def prompt() -> PromptDefinition:
    return PromptDefinition(
        task="classification",
        version="1.0.0",
        system_prompt="system",
        user_template="{text}",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["labels", "confidence"],
            "properties": {
                "labels": {"type": "array"},
                "confidence": {"type": "number"},
            },
        },
    )


def dataset() -> GoldenDataset:
    return GoldenDataset(
        task="classification",
        version="1.0.0",
        examples=(
            GoldenExample("one", {"text": "shall"}, {"labels": ["requirement"], "confidence": 1.0}),
            GoldenExample("two", {"text": "note"}, {"labels": ["note"], "confidence": 1.0}),
        ),
    )


def test_runs_gold_dataset_and_aggregates_metrics() -> None:
    runner = SemanticEvaluationRunner(
        FakeGateway(
            [
                {"labels": ["requirement"], "confidence": 1.0},
                {"labels": ["note"], "confidence": 0.8},
            ]
        )
    )
    run = runner.run(prompt(), dataset(), model="model-a")
    assert run.model == "model-a"
    assert run.metrics.schema_valid_rate == 1.0
    assert run.metrics.precision == 1.0
    assert run.metrics.recall == 1.0
    assert run.metrics.mean_confidence == 0.9


def test_benchmarks_multiple_models() -> None:
    runner = SemanticEvaluationRunner(
        FakeGateway(
            [
                {"labels": ["requirement"], "confidence": 1.0},
                {"labels": ["note"], "confidence": 1.0},
                {"labels": ["requirement"], "confidence": 1.0},
                {"labels": ["wrong"], "confidence": 0.4},
            ]
        )
    )
    runs = runner.benchmark(prompt(), dataset(), ["model-a", "model-b"])
    assert [run.model for run in runs] == ["model-a", "model-b"]
    assert runs[0].metrics.f1 > runs[1].metrics.f1


def test_detects_metric_and_case_regressions() -> None:
    baseline = SemanticEvaluationRunner(
        FakeGateway(
            [
                {"labels": ["requirement"], "confidence": 1.0},
                {"labels": ["note"], "confidence": 1.0},
            ]
        )
    ).run(prompt(), dataset())
    candidate = SemanticEvaluationRunner(
        FakeGateway(
            [
                {"labels": ["requirement"], "confidence": 1.0},
                {"labels": ["wrong"], "confidence": 1.0},
            ]
        )
    ).run(prompt(), dataset())
    result = compare_runs(baseline, candidate)
    assert not result.passed
    assert any("recall regressed" in item for item in result.regressions)
    assert any("case two" in item for item in result.regressions)
