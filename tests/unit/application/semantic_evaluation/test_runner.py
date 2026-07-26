from standards_atlas.application.ports.llm_gateway import (
    StructuredGenerationResult,
    TokenUsage,
)
from standards_atlas.application.semantic_evaluation import (
    GoldenCorpus,
    GoldenCorpusCase,
    PromptDefinition,
    SemanticEvaluationRunner,
)


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        value = next(self.outputs)
        return StructuredGenerationResult(
            value=value,
            model=request.model or "default",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash="input-hash",
            raw_response_hash="response-hash",
            duration_ms=10,
            usage=TokenUsage(prompt_tokens=4, completion_tokens=2, total_tokens=6),
        )


def _prompt():
    return PromptDefinition(
        identifier="summary",
        version="1.0.0",
        task="summary",
        system_prompt="Return JSON.",
        user_template="Summarize {text}",
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    )


def _corpus():
    return GoldenCorpus(
        identifier="summary",
        version="1.0.0",
        task="summary",
        cases=(
            GoldenCorpusCase("one", {"text": "Clause one"}, {"summary": "One"}),
            GoldenCorpusCase("two", {"text": "Clause two"}, {"summary": "Two"}),
        ),
    )


def test_runner_calculates_metrics_and_preserves_provenance():
    gateway = FakeGateway([{"summary": "One"}, {"summary": "Different"}])

    report = SemanticEvaluationRunner(gateway).run(_prompt(), _corpus(), model="granite")

    assert report.metrics.case_count == 2
    assert report.metrics.json_schema_validity == 1.0
    assert report.metrics.exact_match_rate == 0.5
    assert report.metrics.field_accuracy == 0.5
    assert report.metrics.total_tokens == 12
    assert report.cases[0].provider == "fake"
    assert gateway.requests[0].model == "granite"
    assert gateway.requests[0].seed == 0


def test_runner_records_schema_failures_without_aborting_corpus():
    gateway = FakeGateway([{"summary": 42}, {"summary": "Two"}])

    report = SemanticEvaluationRunner(gateway).run(_prompt(), _corpus(), model="granite")

    assert report.metrics.successful_cases == 1
    assert report.metrics.json_schema_validity == 0.5
    assert report.cases[0].error == "$.summary must be a string"
