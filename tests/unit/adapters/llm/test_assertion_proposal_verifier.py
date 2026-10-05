import hashlib
import json

import pytest

from standards_atlas.adapters.llm import OntologyGuidedAssertionProposalVerifier
from standards_atlas.application.context import (
    ContextSelectionProfile,
    build_context_source_package,
    build_structured_context_candidates,
    select_structured_context,
)
from standards_atlas.application.context.input_binding import context_source_package_binding
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
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


class _Gateway:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value
        self.request = None

    def generate_structured(self, request):
        self.request = request
        return StructuredGenerationResult(
            value=self.value,
            model="verifier-model",
            provider="test-provider",
            prompt_version=request.prompt_version,
            input_hash="c" * 64,
            raw_response_hash="d" * 64,
            duration_ms=3,
        )


def _fixture():
    parent_heading = "Safety plan confirmation review"
    statement = "The evaluation shall assess the verification criteria."
    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="TEST", clause="5"),
        clause_type=ClauseType.CLAUSE,
        heading=parent_heading,
    )
    target = Clause(
        id=ClauseId(value="target"),
        reference=StandardReference(standard="TEST", clause="5.1"),
        clause_type=ClauseType.REQUIREMENT,
        parent_id=parent.id,
        heading="Evaluation",
        content=(TextBlock(id="t", text=statement),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Test",
        document_type=DocumentType.STANDARD,
        clauses=(parent, target),
    )
    inventory = build_structured_context_candidates(document, target)
    selection = select_structured_context(
        inventory,
        profile=ContextSelectionProfile(character_budget=20_000, max_sequence_distance=8),
    )
    package = build_context_source_package(document, inventory, selection)
    parent_surface = next(
        item
        for item in package.input_surfaces
        if item.source_ref.clause_id == "parent"
        and item.source_ref.source_kind is EvidenceSourceKind.HEADING
    )
    body_surface = next(
        item
        for item in package.input_surfaces
        if item.source_ref.clause_id == "target"
        and item.source_ref.source_kind is EvidenceSourceKind.BODY
    )
    parent_anchor = EvidenceAnchor(
        id="a-parent",
        source_clause_id=parent.id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=len(parent_heading),
        content_hash=hashlib.sha256(parent_heading.encode()).hexdigest(),
    )
    body_anchor = EvidenceAnchor(
        id="a-body",
        source_clause_id=target.id,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(statement),
        content_hash=hashlib.sha256(statement.encode()).hexdigest(),
    )
    review_entity = KnowledgeEntityProposal(
        id="e-review",
        proposal_clause_ids=(target.id,),
        class_iri=f"{STAT}Activity",
        normalized_label="safety plan confirmation review",
        source_anchor_ids=(parent_anchor.id,),
        confidence=0.9,
    )
    criterion_entity = KnowledgeEntityProposal(
        id="e-criteria",
        proposal_clause_ids=(target.id,),
        class_iri=f"{STAT}VerificationCriterion",
        normalized_label="verification criteria",
        source_anchor_ids=(body_anchor.id,),
        confidence=0.9,
    )
    assertion = NormativeAssertionProposal(
        id="n-1",
        source_clause_id=target.id,
        subject_id=review_entity.id,
        predicate=f"{STAT}assesses",
        object=EntityAssertionObject(entity_id=criterion_entity.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(parent_anchor.id, body_anchor.id),
        confidence=0.9,
    )
    return (
        target,
        package,
        (parent_anchor, body_anchor),
        (review_entity, criterion_entity),
        assertion,
        parent_surface.package_source_ref,
        body_surface.package_source_ref,
    )


def test_verifier_preserves_cross_clause_multi_span_evidence_and_package_binding() -> None:
    target, package, anchors, entities, assertion, parent_ref, body_ref = _fixture()
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": "e-review", "disposition": "supported", "rationale": None},
                {"candidate_id": "e-criteria", "disposition": "supported", "rationale": None},
            ],
            "assertion_reviews": [
                {"candidate_id": "n-1", "disposition": "supported", "rationale": None}
            ],
            "missing_entity_detected": False,
            "missing_assertion_detected": False,
            "missing_rationale": None,
        }
    )

    result = OntologyGuidedAssertionProposalVerifier(gateway).verify(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=anchors,
        entity_proposals=entities,
        assertion_proposals=(assertion,),
        source_package=package,
    )

    assert result.source_package_sha256 == context_source_package_binding(package).package_sha256
    payload = json.loads(gateway.request.user_prompt)
    evidence = payload["assertion_candidates"][0]["evidence"]
    assert [item["source_ref"] for item in evidence] == [parent_ref, body_ref]
    assert {item["source_clause_id"] for item in evidence} == {"parent", "target"}
    assert "clause_text" not in payload
    assert "unclear semantic reach is uncertainty" in gateway.request.system_prompt


def test_verifier_rejects_anchor_not_contained_in_bound_package_before_gateway_call() -> None:
    target, package, anchors, entities, assertion, _parent_ref, _body_ref = _fixture()
    invalid = anchors[0].model_copy(
        update={
            "id": "outside",
            "source_clause_id": ClauseId(value="other"),
        }
    )
    assertion = assertion.model_copy(update={"evidence_anchor_ids": (invalid.id, anchors[1].id)})
    gateway = _Gateway({})

    with pytest.raises(ValueError, match="not uniquely contained"):
        OntologyGuidedAssertionProposalVerifier(gateway).verify(
            target,
            document_key="TEST",
            ontology_versions=ONTOLOGIES,
            evidence_anchors=(anchors[0], invalid, anchors[1]),
            entity_proposals=entities,
            assertion_proposals=(assertion,),
            source_package=package,
        )
    assert gateway.request is None


def test_p1_verifier_uses_shared_policy_and_can_report_important_omissions() -> None:
    target, package, anchors, entities, assertion, _parent_ref, _body_ref = _fixture()
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": item.id, "disposition": "supported", "rationale": None}
                for item in entities
            ],
            "assertion_reviews": [
                {"candidate_id": assertion.id, "disposition": "supported", "rationale": None}
            ],
            "missing_entity_detected": True,
            "missing_assertion_detected": True,
            "missing_rationale": "A required work product and its relation are absent.",
        }
    )

    result = OntologyGuidedAssertionProposalVerifier(
        gateway,
        prompt_version="engineering-policy-verifier-v1",
    ).verify(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=anchors,
        entity_proposals=entities,
        assertion_proposals=(assertion,),
        source_package=package,
    )

    assert result.missing_entity_detected is True
    assert result.missing_assertion_detected is True
    assert gateway.request.metadata["prompt_policy"]["id"] == "engineering-assertion-extraction"
    assert gateway.request.metadata["prompt_variant"] == {
        "id": "P1",
        "baseline_id": "B0-AP02",
        "qualification_status": "unqualified",
    }
    assert (
        "work products and evidence objects as first-class entities"
        in gateway.request.system_prompt
    )
    assert (
        "important omitted source-extractable entities or assertions"
        in gateway.request.system_prompt
    )


@pytest.mark.parametrize(
    ("entity_count", "expected_ids"),
    (
        (0, ()),
        (1, ("e-review",)),
        (2, ("e-review", "e-criteria")),
    ),
)
def test_series_g_v2_binds_review_schema_to_supplied_candidate_ids(
    entity_count: int,
    expected_ids: tuple[str, ...],
) -> None:
    target, package, anchors, entities, _assertion, _parent_ref, _body_ref = _fixture()
    selected_entities = entities[:entity_count]
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": item.id, "disposition": "supported", "rationale": None}
                for item in selected_entities
            ],
            "assertion_reviews": [],
            "missing_entity_detected": False,
            "missing_assertion_detected": False,
            "missing_rationale": None,
        }
    )

    OntologyGuidedAssertionProposalVerifier(
        gateway,
        prompt_version="ontology-guided-assertion-verifier-source-bound-v2",
    ).verify(
        target,
        document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=anchors,
        entity_proposals=selected_entities,
        assertion_proposals=(),
        source_package=package,
    )

    assert gateway.request is not None
    schema = gateway.request.output_schema
    entity_reviews = schema["properties"]["entity_reviews"]
    assertion_reviews = schema["properties"]["assertion_reviews"]
    assert entity_reviews["minItems"] == entity_reviews["maxItems"] == entity_count
    assert assertion_reviews["minItems"] == assertion_reviews["maxItems"] == 0
    if expected_ids:
        assert entity_reviews["items"]["properties"]["candidate_id"]["enum"] == list(expected_ids)
    else:
        assert "enum" not in entity_reviews["items"]["properties"]["candidate_id"]
    assert "enum" not in assertion_reviews["items"]["properties"]["candidate_id"]
    assert gateway.request.metadata["candidate_response_contract"] == (
        "exact-supplied-candidate-ids-v1"
    )
    assert len(gateway.request.metadata["effective_output_schema_sha256"]) == 64
    assert "If assertion_candidates is empty, assertion_reviews MUST be []" in (
        gateway.request.system_prompt
    )


def test_series_g_v2_keeps_strict_post_response_candidate_id_validation() -> None:
    target, package, anchors, entities, _assertion, _parent_ref, _body_ref = _fixture()
    gateway = _Gateway(
        {
            "entity_reviews": [
                {"candidate_id": "invented", "disposition": "supported", "rationale": None}
            ],
            "assertion_reviews": [],
            "missing_entity_detected": False,
            "missing_assertion_detected": False,
            "missing_rationale": None,
        }
    )

    with pytest.raises(ValueError, match="exactly the supplied entity candidate ids"):
        OntologyGuidedAssertionProposalVerifier(
            gateway,
            prompt_version="ontology-guided-assertion-verifier-source-bound-v2",
        ).verify(
            target,
            document_key="TEST",
            ontology_versions=ONTOLOGIES,
            evidence_anchors=anchors,
            entity_proposals=(entities[0],),
            assertion_proposals=(),
            source_package=package,
        )
