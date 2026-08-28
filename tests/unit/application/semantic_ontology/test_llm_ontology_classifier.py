from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.ports.llm_gateway import (
    LlmResponseError,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_classification import (
    LlmSemanticClassifier,
    SemanticClassificationContext,
)
from standards_atlas.application.semantic_ontology import OntologyDefinition


class Gateway:
    def __init__(self, responses=None) -> None:
        self.requests = []
        self._responses = list(responses or [])

    @property
    def request(self):
        return self.requests[-1] if self.requests else None

    def generate_structured(self, request):
        self.requests.append(request)
        if self._responses:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return StructuredGenerationResult(
            value={"statement_functions": ["requirement"]},
            model="test",
            provider="test",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
        )


def _prompt() -> PromptDefinition:
    return PromptDefinition(
        task="semantic-profile-classification",
        version="structure-aware-v6",
        description="test",
        system_prompt="Qualified semantic classification rules.",
        user_template=(
            "Normalized clause content:\n{content}\n\nStructural context:\n{context_json}"
        ),
        output_schema={"type": "object"},
    )


def _classifier(gateway: Gateway) -> LlmSemanticClassifier:
    return LlmSemanticClassifier(gateway, prompt=_prompt(), task_version="2.4.0")


def _definition() -> OntologyDefinition:
    return OntologyDefinition(
        id="statement-functions",
        version="2.0.0",
        dimension="statement_functions",
        values=("requirement", "recommendation"),
    )


def test_classifier_supplies_structural_context_to_llm() -> None:
    gateway = Gateway()
    classifier = _classifier(gateway)

    result = classifier.classify(
        SemanticClassificationContext(
            content="The item shall be verified.",
            structural_context={"node_kind": "leaf", "sibling": {"is_last": True}},
            metadata={"title": "Verification"},
        ),
        {"statement_functions": _definition()},
    )

    assert result[0].values == ("requirement",)
    assert gateway.request is not None
    assert '"structural_context"' in gateway.request.user_prompt
    assert '"is_last": true' in gateway.request.user_prompt


def test_classifier_retries_truncated_structured_response_with_larger_budget() -> None:
    failure = LlmResponseError("truncated", finish_reason="length")
    success = StructuredGenerationResult(
        value={"statement_functions": ["requirement"]},
        model="test",
        provider="test",
        prompt_version="structure-aware-v6",
        input_hash="input",
        raw_response_hash="response",
        duration_ms=1,
    )
    gateway = Gateway([failure, success])
    classifier = _classifier(gateway)

    result = classifier.classify(
        SemanticClassificationContext(content="The item shall be verified."),
        {"statement_functions": _definition()},
    )

    assert result[0].values == ("requirement",)
    assert [request.max_tokens for request in gateway.requests] == [1024, 2048]
    assert "previous response was truncated" in gateway.requests[1].system_prompt
    assert gateway.requests[0].task == "semantic-profile-classification"
    assert gateway.requests[0].prompt_version == "structure-aware-v6"
    assert gateway.requests[0].metadata["task_version"] == "2.4.0"


def test_classifier_does_not_retry_non_length_response_error() -> None:
    failure = LlmResponseError("invalid json", finish_reason="stop")
    gateway = Gateway([failure])
    classifier = _classifier(gateway)

    try:
        classifier.classify(
            SemanticClassificationContext(content="The item shall be verified."),
            {"statement_functions": _definition()},
        )
    except LlmResponseError as error:
        assert error is failure
    else:
        raise AssertionError("expected LlmResponseError")

    assert len(gateway.requests) == 1
