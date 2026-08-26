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
                        "class_iri": "http://lunetix.org/standards-atlas#Activity",
                        "label": "verification",
                        "confidence": 0.9,
                        "evidence": "activity is required",
                    },
                    {
                        "class_iri": "http://lunetix.org/standards-atlas#InventedClass",
                        "label": "invented",
                        "confidence": 0.7,
                        "evidence": "unsupported concept",
                    },
                ],
                "relations": [
                    {
                        "subject_index": 0,
                        "predicate": "http://lunetix.org/standards-atlas#partOf",
                        "object_index": 0,
                        "confidence": 0.8,
                        "evidence": "unsupported relation",
                    },
                    {
                        "subject_index": 0,
                        "predicate": "http://lunetix.org/standards-atlas#requires",
                        "object_index": 1,
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


class _IndexedRelationGateway:
    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={
                "entities": [
                    {
                        "class_iri": "http://lunetix.org/standards-atlas#Activity",
                        "label": "Verification",
                        "confidence": 0.9,
                        "evidence": "first entity",
                    },
                    {
                        "class_iri": "http://lunetix.org/standards-atlas#Artifact",
                        "label": "Verification report",
                        "confidence": 0.8,
                        "evidence": "second entity",
                    },
                ],
                "relations": [
                    {
                        "subject_index": 0,
                        "predicate": "http://lunetix.org/standards-atlas#requires",
                        "object_index": 1,
                        "confidence": 0.7,
                        "evidence": "indexed relation",
                    }
                ],
            },
            model="test-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
        )


def test_relation_indexes_resolve_distinct_entities_without_llm_ids() -> None:
    clause = Clause(
        id=ClauseId(value="clause-indexed"),
        reference=StandardReference(standard="TEST", year=2026, clause="2"),
        clause_type=ClauseType.CLAUSE,
        title="Indexed relation",
    )

    result = OntologyGuidedLlmExtractor(_IndexedRelationGateway()).extract(
        clause,
        document_key="TEST",
        ontology_versions=(
            "standards-atlas-core@1.1.0",
            "functional-safety@1.1.0",
        ),
    )

    assert len(result.entities) == 2
    assert len({entity.id.iri for entity in result.entities}) == 2
    assert len(result.relations) == 1
    assert result.violations == ()
    assert result.clause_reference == "TEST:2026 2"
    assert result.clause_title == "Indexed relation"


class _StableIdentityGateway:
    def __init__(self, label: str) -> None:
        self.label = label

    def generate_structured(self, request):
        return StructuredGenerationResult(
            value={
                "entities": [
                    {
                        "class_iri": "http://lunetix.org/standards-atlas#Activity",
                        "label": self.label,
                        "confidence": 0.9,
                        "evidence": "same semantic entity",
                    }
                ],
                "relations": [],
            },
            model="test-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="input",
            raw_response_hash="response",
            duration_ms=1,
        )


def test_entity_identity_is_stable_across_label_formatting() -> None:
    clause = Clause(
        id=ClauseId(value="clause-stable"),
        reference=StandardReference(standard="TEST", clause="3"),
        clause_type=ClauseType.CLAUSE,
    )
    ontology_versions = (
        "standards-atlas-core@1.1.0",
        "functional-safety@1.1.0",
    )

    first_gateway = _StableIdentityGateway(" Verification  Activity ")
    first = OntologyGuidedLlmExtractor(first_gateway).extract(
        clause,
        document_key="TEST",
        ontology_versions=ontology_versions,
    )
    second_gateway = _StableIdentityGateway("verification activity")
    second = OntologyGuidedLlmExtractor(second_gateway).extract(
        clause,
        document_key="TEST",
        ontology_versions=ontology_versions,
    )

    assert first.entities[0].id == second.entities[0].id
