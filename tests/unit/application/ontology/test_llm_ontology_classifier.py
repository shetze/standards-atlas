from standards_atlas.application.ontology import (
    LlmOntologyClassifier,
    OntologyContext,
    OntologyDefinition,
)
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult


class Gateway:
    def __init__(self) -> None:
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value={"statement_functions": ["requirement"]},
            model="test",
            provider="test",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
        )


def test_classifier_supplies_structural_context_to_llm() -> None:
    gateway = Gateway()
    classifier = LlmOntologyClassifier(gateway)
    definition = OntologyDefinition(
        id="statement-functions",
        version="2.0.0",
        dimension="statement_functions",
        values=("requirement", "recommendation"),
    )

    result = classifier.classify(
        OntologyContext(
            content="The item shall be verified.",
            structural_context={"node_kind": "leaf", "sibling": {"is_last": True}},
            metadata={"title": "Verification"},
        ),
        {"statement_functions": definition},
    )

    assert result[0].values == ("requirement",)
    assert gateway.request is not None
    assert '"structural_context"' in gateway.request.user_prompt
    assert '"is_last": true' in gateway.request.user_prompt
