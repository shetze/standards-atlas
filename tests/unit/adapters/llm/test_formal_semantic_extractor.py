from standards_atlas.adapters.llm.formal_semantic_extractor import OntologyGuidedLlmExtractor
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import Clause, ClauseId, ClauseType, StandardReference


class _Gateway:
    def __init__(self) -> None:
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value={
                "entities": [
                    {
                        "id": "a",
                        "class_iri": "http://lunetix.org/standards-atlas#Activity",
                        "label": "verification",
                        "confidence": 0.9,
                        "evidence": "activity is required",
                    },
                    {
                        "id": "bad",
                        "class_iri": "http://lunetix.org/standards-atlas#InventedClass",
                        "label": "invented",
                        "confidence": 0.7,
                        "evidence": "unsupported concept",
                    },
                ],
                "relations": [
                    {
                        "subject_id": "a",
                        "predicate": "http://lunetix.org/standards-atlas#partOf",
                        "object_id": "a",
                        "confidence": 0.8,
                        "evidence": "unsupported relation",
                    },
                    {
                        "subject_id": "a",
                        "predicate": "http://lunetix.org/standards-atlas#requires",
                        "object_id": "bad",
                        "confidence": 0.8,
                        "evidence": "references rejected entity",
                    },
                ],
            },
            model="test-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
        )


def test_undeclared_terms_are_rejected_without_aborting_extraction() -> None:
    gateway = _Gateway()
    clause = Clause(
        id=ClauseId(value="clause-1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
    )

    result = OntologyGuidedLlmExtractor(gateway).extract(
        clause,
        document_key="TEST",
        ontology_versions=(
            "standards-atlas-core@1.1.0",
            "functional-safety@1.1.0",
        ),
    )

    assert len(result.entities) == 1
    assert result.relations == ()
    assert [(item.kind, item.term) for item in result.violations] == [
        ("undeclared_class", "http://lunetix.org/standards-atlas#InventedClass"),
        ("undeclared_property", "http://lunetix.org/standards-atlas#partOf"),
        ("invalid_relation", "http://lunetix.org/standards-atlas#requires"),
    ]
    assert "closed vocabularies" in gateway.request.system_prompt
    assert "allowed_classes" in gateway.request.user_prompt
    assert "allowed_properties" in gateway.request.user_prompt
