from types import SimpleNamespace

from standards_atlas.application.ontology import LlmRoleSemanticsClassifier, OntologyContext
from standards_atlas.application.ports.llm_gateway import LlmResponseError


class FakeGateway:
    def __init__(self, values):
        self.values = list(values)
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(value=value)


def test_presence_false_skips_relation_extraction() -> None:
    gateway = FakeGateway(
        [{"role_semantics_present": False, "confidence": 0.98, "rationale": "none"}]
    )
    classifier = LlmRoleSemanticsClassifier(gateway, model="test")

    result = classifier.classify(OntologyContext(content="This clause defines a concept."))

    assert result.present is False
    assert result.relations == ()
    assert [request.task for request in gateway.requests] == ["role-semantics-presence"]


def test_presence_true_without_complete_tuple_returns_no_relation() -> None:
    gateway = FakeGateway(
        [
            {"role_semantics_present": True, "confidence": 0.97, "rationale": "verification"},
            {"role_relations": []},
        ]
    )
    classifier = LlmRoleSemanticsClassifier(gateway)

    result = classifier.classify(OntologyContext(content="The analysis shall be verified."))

    assert result.present is True
    assert result.relations == ()
    assert [request.task for request in gateway.requests] == [
        "role-semantics-presence",
        "role-relation-extraction",
    ]


def test_complete_tuple_is_extracted_with_actor_field() -> None:
    gateway = FakeGateway(
        [
            {"role_semantics_present": True, "confidence": 0.99, "rationale": "explicit actor"},
            {
                "role_relations": [
                    {
                        "actor": "Verifier",
                        "relation_class": "performance",
                        "target": "analysis",
                    }
                ]
            },
        ]
    )
    classifier = LlmRoleSemanticsClassifier(gateway)

    result = classifier.classify(OntologyContext(content="The Verifier verifies the analysis."))

    assert result.present is True
    assert len(result.relations) == 1
    assert result.relations[0].actor == "Verifier"
    assert result.relations[0].relation_class == "performance"
    assert result.relations[0].target == "analysis"


def test_presence_retries_malformed_response_with_bounded_budget() -> None:
    gateway = FakeGateway(
        [
            LlmResponseError("truncated", finish_reason="length"),
            {"role_semantics_present": False, "confidence": 0.96},
        ]
    )
    classifier = LlmRoleSemanticsClassifier(gateway, model="test")

    result = classifier.classify(OntologyContext(content="This clause defines a concept."))

    assert result.present is False
    assert len(gateway.requests) == 2
    assert gateway.requests[0].max_tokens == 64
    assert gateway.requests[1].max_tokens == 128
    assert gateway.requests[0].output_schema["required"] == [
        "role_semantics_present",
        "confidence",
    ]


def test_presence_propagates_second_malformed_response_for_clause_level_handling() -> None:
    gateway = FakeGateway(
        [
            LlmResponseError("first"),
            LlmResponseError("second"),
        ]
    )
    classifier = LlmRoleSemanticsClassifier(gateway)

    try:
        classifier.classify(OntologyContext(content="The design shall be verified."))
    except LlmResponseError as error:
        assert str(error) == "second"
    else:
        raise AssertionError("expected LlmResponseError")

    assert len(gateway.requests) == 2
