import json

from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    EntityAssertionObject,
    EvidenceSourceKind,
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


def _clause(
    text: str,
    *,
    heading: str | None = None,
    clause_type: ClauseType = ClauseType.REQUIREMENT,
) -> Clause:
    return Clause(
        id=ClauseId(value="c-5b"),
        reference=StandardReference(standard="TEST", year=2026, clause="5"),
        clause_type=clause_type,
        heading=heading,
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
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
                    "evidence_quote": "verification plan",
                    "rationale": "the clause names the work product",
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "verification criteria",
                    "confidence": 0.94,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
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
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
                    "evidence_quote": "Verification Plan",
                    "rationale": None,
                },
                {
                    "class_iri": f"{STAT}InventedClass",
                    "label": "invented",
                    "confidence": 0.7,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
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
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
                    "evidence_quote": "verification plan",
                    "rationale": None,
                },
                {
                    "class_iri": f"{STAT}VerificationCriterion",
                    "label": "criterion",
                    "confidence": 0.9,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
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


def test_extractor_accepts_ancestor_heading_as_entity_evidence() -> None:
    text = "If the method is used, the criteria apply."
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "random hardware fault quantitative analysis",
                    "confidence": 0.9,
                    "evidence_source_kind": "heading",
                    "evidence_source_clause_id": "parent-1",
                    "evidence_quote": "Random hardware fault quantitative analysis",
                    "rationale": "ancestor heading frames the engineering activity",
                }
            ],
            "assertions": [],
        }
    )
    clause = _clause(text)

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        clause,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        semantic_context={
            "ancestor_headings": [
                {
                    "clause_id": "parent-1",
                    "reference": "12.3.1",
                    "heading": "Random hardware fault quantitative analysis",
                }
            ]
        },
    )

    assert len(result.entity_proposals) == 1
    entity = result.entity_proposals[0]
    assert entity.proposal_clause_ids == (clause.id,)
    anchor = result.evidence_anchors[0]
    assert anchor.source_clause_id.value == "parent-1"
    assert anchor.source_kind.value == "heading"
    assert result.violations == ()


def test_extractor_recovers_local_heading_when_model_declares_body() -> None:
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}EngineeringEntity",
                    "label": "hazard log",
                    "confidence": 1.0,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "c-5b",
                    "evidence_quote": "hazard log",
                    "rationale": "the term heading identifies the defined engineering entity",
                }
            ],
            "assertions": [],
        }
    )

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        _clause(
            "document in which hazards identified, decisions made, solutions adopted are recorded",
            heading="hazard log",
            clause_type=ClauseType.TERM,
        ),
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
    )

    assert len(result.entity_proposals) == 1
    assert result.violations == ()
    anchor = result.evidence_anchors[0]
    assert anchor.source_clause_id == ClauseId(value="c-5b")
    assert anchor.source_kind is EvidenceSourceKind.HEADING


def test_extractor_accepts_associative_body_as_entity_evidence() -> None:
    text = "If the method is used, the criteria apply."
    gateway = _Gateway(
        {
            "entities": [
                {
                    "class_iri": f"{STAT}Activity",
                    "label": "emergency operation tolerance time interval calculation",
                    "confidence": 0.9,
                    "evidence_source_kind": "body",
                    "evidence_source_clause_id": "intro-1",
                    "evidence_quote": "Emergency Operation Tolerance Time Interval",
                    "rationale": "the leading clause establishes the calculation activity",
                }
            ],
            "assertions": [],
        }
    )
    clause = _clause(text)

    result = OntologyGuidedKnowledgeProposalExtractor(gateway).extract(
        clause,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        semantic_context={
            "associative_context": [
                {
                    "clause_id": "intro-1",
                    "reference": "12.3.1.1",
                    "heading": "Emergency Operation Tolerance Time Interval calculation method",
                    "text": "The Emergency Operation Tolerance Time Interval uses the PMHF.",
                    "role": "leading_substantive_descendant",
                }
            ]
        },
    )

    assert len(result.entity_proposals) == 1
    anchor = result.evidence_anchors[0]
    assert anchor.source_clause_id.value == "intro-1"
    assert anchor.source_kind is EvidenceSourceKind.BODY
    assert result.violations == ()
    assert "structural framing only" in gateway.request.system_prompt
    assert "Assertion evidence must always come from clause_text" in gateway.request.system_prompt
