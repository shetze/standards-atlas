import json

from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    EntityAssertionObject,
    KnowledgeProposalViolationKind,
    NormativeForce,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


class _Gateway:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value=self.value,
            model="test-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="a" * 64,
            raw_response_hash="b" * 64,
            duration_ms=4,
        )


def _clause(text: str) -> Clause:
    return Clause(
        id=ClauseId(value="c-5b"),
        reference=StandardReference(standard="TEST", year=2026, clause="5"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="t-1", text=text),),
    )


def test_extractor_builds_grounded_entity_assertion_proposals() -> None:
    text = "The verification plan shall specify the verification criteria."
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}VerificationPlan",
                    "label": "verification plan",
                    "confidence": 0.96,
                    "evidence_quote": "verification plan",
                    "rationale": "the clause names the work product",
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "verification criteria",
                    "confidence": 0.94,
                    "evidence_quote": "verification criteria",
                    "rationale": None,
                },
            ],
            "assertions": [
                {
                    "subject_index": 0,
                    "predicate": f"{STAT}specifies",
                    "object_kind": "entity",
                    "object_index": 1,
                    "literal_value": None,
                    "literal_datatype_iri": None,
                    "literal_language": None,
                    "normative_force": "requirement",
                    "confidence": 0.93,
                    "evidence_quote": text,
                    "rationale": "shall expresses the mandatory assertion",
                }
            ],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway, model="configured-model").extract(
        _clause(text), document_key="TEST", ontology_versions=ONTOLOGIES
    )

    assert len(result.entity_proposals) == 2
    assert len(result.assertion_proposals) == 1
    assert len(result.evidence_anchors) == 3
    assertion = result.assertion_proposals[0]
    assert assertion.normative_force is NormativeForce.REQUIREMENT
    assert assertion.predicate == f"{STAT}specifies"
    assert isinstance(assertion.object, EntityAssertionObject)
    assert assertion.object.entity_id == result.entity_proposals[1].id
    assert assertion.subject_id == result.entity_proposals[0].id
    assert result.violations == ()
    assert result.input_hash == "a" * 64
    assert result.raw_response_hash == "b" * 64
    assert result.proposal_provenance is not None
    assert result.proposal_provenance.model == "test-model"
    assert result.proposal_provenance.provider == "test-provider"

    payload = json.loads(gateway.request.user_prompt)
    assert payload["allowed_normative_force"] == [item.value for item in NormativeForce]
    assert "exact, case-sensitive" in gateway.request.system_prompt
    assert "not rationales" in gateway.request.system_prompt


def test_unresolved_and_undeclared_items_become_nonfatal_violations() -> None:
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}VerificationPlan",
                    "label": "verification plan",
                    "confidence": 0.9,
                    "evidence_quote": "Verification Plan",
                    "rationale": None,
                },
                {
                    "class_iri": f"{STAT}InventedClass",
                    "label": "invented",
                    "confidence": 0.7,
                    "evidence_quote": "verification",
                    "rationale": None,
                },
            ],
            "assertions": [],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        _clause("The verification plan shall be prepared."),
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
    )

    assert result.entity_proposals == ()
    assert {item.kind for item in result.violations} == {
        KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
        KnowledgeProposalViolationKind.UNDECLARED_CLASS,
    }


def test_rejected_entity_prevents_assertion_without_aborting_clause() -> None:
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}VerificationPlan",
                    "label": "verification plan",
                    "confidence": 0.9,
                    "evidence_quote": "verification plan",
                    "rationale": None,
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "criterion",
                    "confidence": 0.9,
                    "evidence_quote": "missing criterion quote",
                    "rationale": None,
                },
            ],
            "assertions": [
                {
                    "subject_index": 0,
                    "predicate": f"{STAT}specifies",
                    "object_kind": "entity",
                    "object_index": 1,
                    "literal_value": None,
                    "literal_datatype_iri": None,
                    "literal_language": None,
                    "normative_force": "requirement",
                    "confidence": 0.8,
                    "evidence_quote": "The verification plan shall specify a criterion.",
                    "rationale": None,
                }
            ],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        _clause("The verification plan shall specify a criterion."),
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
    )

    assert len(result.entity_proposals) == 1
    assert result.assertion_proposals == ()
    assert [item.kind for item in result.violations] == [
        KnowledgeProposalViolationKind.UNRESOLVED_GROUNDING,
        KnowledgeProposalViolationKind.INVALID_ASSERTION,
    ]
