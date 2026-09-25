import json

from standards_atlas.adapters.llm import OntologyGuidedAssertionProposalVerifier
from standards_atlas.application.assertion_qualification import AssertionVerificationDisposition
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeEntityProposal,
    NormativeAssertionProposal,
    NormativeForce,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
TEXT = "The verification plan shall specify the verification criteria."


class _Gateway:
    def __init__(self, value):
        self.value = value
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value=self.value,
            model="verify-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="a" * 64,
            raw_response_hash="b" * 64,
            duration_ms=3,
        )


def _inputs():
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id="t1", text=TEXT),),
    )
    anchor = EvidenceAnchor(
        id="anchor-1",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(TEXT),
    )
    entity = KnowledgeEntityProposal(
        id="entity-1",
        proposal_clause_ids=(clause.id,),
        class_iri=f"{STAT}VerificationPlan",
        normalized_label="verification plan",
        source_anchor_ids=(anchor.id,),
        confidence=0.8,
    )
    assertion = NormativeAssertionProposal(
        id="assertion-1",
        source_clause_id=clause.id,
        subject_id=entity.id,
        predicate=f"{STAT}requires",
        object=EntityAssertionObject(entity_id=entity.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        confidence=0.8,
    )
    return clause, anchor, entity, assertion


def test_verifier_reviews_candidates_and_runs_independent_missing_check() -> None:
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": "entity-1", "disposition": "supported", "rationale": None}
            ],
            "assertion_reviews": [
                {
                    "candidate_id": "assertion-1",
                    "disposition": "uncertain",
                    "rationale": "predicate needs escalation",
                }
            ],
            "missing_entity_detected": False,
            "missing_assertion_detected": True,
            "missing_rationale": "verification criteria relation may be missing",
        }
    )
    clause, anchor, entity, assertion = _inputs()

    result = OntologyGuidedAssertionProposalVerifier(gateway, model="verify-model").verify(
        clause,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=(anchor,),
        entity_proposals=(entity,),
        assertion_proposals=(assertion,),
    )

    assert result.entity_reviews[0].disposition is AssertionVerificationDisposition.SUPPORTED
    assert result.assertion_reviews[0].disposition is AssertionVerificationDisposition.UNCERTAIN
    assert result.missing_assertion_detected
    assert result.input_hash == "a" * 64
    payload = json.loads(gateway.request.user_prompt)
    assert payload["entity_candidates"][0]["evidence"][0]["quote"] == TEXT
    assert "mandatory even when the candidate arrays are empty" in gateway.request.system_prompt


def test_verifier_resolves_ancestor_heading_evidence_from_semantic_context() -> None:
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": "entity-heading", "disposition": "supported", "rationale": None}
            ],
            "assertion_reviews": [],
            "missing_entity_detected": False,
            "missing_assertion_detected": False,
            "missing_rationale": None,
        }
    )
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="12.3.1.3"),
        clause_type=ClauseType.CLAUSE,
        heading="Local heading",
        content=(TextBlock(id="t1", text="If the method is used, the criteria apply."),),
    )
    parent_id = ClauseId(value="parent")
    heading = "Random hardware fault quantitative analysis"
    anchor = EvidenceAnchor(
        id="anchor-heading",
        source_clause_id=parent_id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=len(heading),
    )
    entity = KnowledgeEntityProposal(
        id="entity-heading",
        proposal_clause_ids=(clause.id,),
        class_iri=f"{STAT}Activity",
        normalized_label="random hardware fault quantitative analysis",
        source_anchor_ids=(anchor.id,),
        confidence=0.9,
    )

    OntologyGuidedAssertionProposalVerifier(gateway).verify(
        clause,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=(anchor,),
        entity_proposals=(entity,),
        assertion_proposals=(),
        semantic_context={
            "ancestor_headings": [
                {"clause_id": parent_id.value, "reference": "12.3.1", "heading": heading}
            ]
        },
    )

    payload = json.loads(gateway.request.user_prompt)
    evidence = payload["entity_candidates"][0]["evidence"][0]
    assert evidence["source_clause_id"] == parent_id.value
    assert evidence["source_kind"] == "heading"
    assert evidence["quote"] == heading
