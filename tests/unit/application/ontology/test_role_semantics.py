from types import SimpleNamespace

from standards_atlas.application.ontology import LlmRoleSemanticsClassifier, OntologyContext


class FakeGateway:
    def __init__(self, values):
        self.values = list(values)
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        return SimpleNamespace(value=self.values.pop(0))


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
                        "predicate": "verify",
                        "target": "analysis",
                        "condition": None,
                        "evidence": "The Verifier verifies the analysis",
                        "confidence": 0.96,
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
    assert result.relations[0].predicate == "verify"
