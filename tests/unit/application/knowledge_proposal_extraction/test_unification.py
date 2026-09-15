import hashlib

import pytest

from standards_atlas.application.knowledge_proposal_extraction import (
    KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION,
    DocumentKnowledgeProposalUnifier,
)
from standards_atlas.domain.model import (
    ClauseId,
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    NormativeAssertionProposal,
    NormativeForce,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


def _anchor(anchor_id: str, clause_id: str, text: str, start: int) -> EvidenceAnchor:
    return EvidenceAnchor(
        id=anchor_id,
        clause_id=ClauseId(value=clause_id),
        start_offset=start,
        end_offset=start + len(text),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def _proposal(
    run_id: str,
    *,
    entities: tuple[KnowledgeEntityProposal, ...],
    assertions: tuple[NormativeAssertionProposal, ...] = (),
    anchors: tuple[EvidenceAnchor, ...],
    document_key: str = "DOMAIN",
    extractor: str = "test-extractor",
) -> DocumentKnowledgeProposal:
    return DocumentKnowledgeProposal(
        proposal_run_id=run_id,
        source_document_key=document_key,
        ontology_versions=ONTOLOGIES,
        evidence_anchors=anchors,
        entity_proposals=entities,
        assertion_proposals=assertions,
        proposal_provenance=KnowledgeProposalProvenance(
            extractor=extractor,
            extractor_version="1.0.0",
        ),
    )


def test_unifies_prose_and_table_entities_with_subclass_refinement_and_lineage() -> None:
    prose_plan_anchor = _anchor("a-prose-plan", "C1", "Verification Plan", 0)
    prose_criterion_anchor = _anchor("a-prose-criterion", "C1", "Independent Review", 20)
    table_plan_anchor = _anchor("a-table-plan", "C1", "Verification plan", 40)
    table_criterion_anchor = _anchor("a-table-criterion", "C1", "Independent review", 60)

    prose_plan = KnowledgeEntityProposal(
        id="prose-plan",
        class_iri=f"{STAT}VerificationPlan",
        normalized_label="verification plan",
        aliases=("Verification Plan",),
        source_anchor_ids=(prose_plan_anchor.id,),
        confidence=0.92,
        rationale="Explicit work-product mention.",
    )
    prose_criterion = KnowledgeEntityProposal(
        id="prose-criterion",
        class_iri=f"{STAT}VerificationCriterion",
        normalized_label="independent review",
        source_anchor_ids=(prose_criterion_anchor.id,),
        confidence=0.88,
    )
    prose_assertion = NormativeAssertionProposal(
        id="prose-assertion",
        source_clause_id=ClauseId(value="C1"),
        subject_id=prose_plan.id,
        predicate=f"{STAT}requires",
        object=EntityAssertionObject(entity_id=prose_criterion.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(prose_plan_anchor.id, prose_criterion_anchor.id),
        confidence=0.86,
    )
    prose = _proposal(
        "prose-run",
        entities=(prose_plan, prose_criterion),
        assertions=(prose_assertion,),
        anchors=(prose_plan_anchor, prose_criterion_anchor),
        extractor="ontology-guided-llm",
    )

    table_plan = KnowledgeEntityProposal(
        id="table-plan",
        class_iri=f"{STAT}EngineeringEntity",
        normalized_label="verification plan",
        aliases=("Verification plan",),
        source_anchor_ids=(table_plan_anchor.id,),
        confidence=1.0,
    )
    table_criterion = KnowledgeEntityProposal(
        id="table-criterion",
        class_iri=f"{STAT}Criterion",
        normalized_label="independent review",
        source_anchor_ids=(table_criterion_anchor.id,),
        confidence=1.0,
    )
    table_assertion = NormativeAssertionProposal(
        id="table-assertion",
        source_clause_id=ClauseId(value="C1"),
        subject_id=table_plan.id,
        predicate=f"{STAT}requires",
        object=EntityAssertionObject(entity_id=table_criterion.id),
        normative_force=NormativeForce.UNSPECIFIED,
        evidence_anchor_ids=(table_plan_anchor.id, table_criterion_anchor.id),
        confidence=1.0,
    )
    table = _proposal(
        "table-run",
        entities=(table_plan, table_criterion),
        assertions=(table_assertion,),
        anchors=(table_plan_anchor, table_criterion_anchor),
        extractor="structured-table-projector",
    )

    unified = DocumentKnowledgeProposalUnifier().unify(
        (table, prose), proposal_run_id="unified-run"
    )

    assert unified.proposal_provenance.extractor == "document-knowledge-proposal-unifier"
    assert unified.proposal_provenance.extractor_version == KNOWLEDGE_PROPOSAL_UNIFICATION_VERSION
    assert [item.proposal_run_id for item in unified.input_proposals] == ["prose-run", "table-run"]
    assert all(len(item.proposal_hash) == 64 for item in unified.input_proposals)

    by_label = {entity.normalized_label: entity for entity in unified.entity_proposals}
    assert set(by_label) == {"verification plan", "independent review"}
    assert by_label["verification plan"].class_iri == f"{STAT}VerificationPlan"
    assert by_label["independent review"].class_iri == f"{STAT}VerificationCriterion"
    assert set(by_label["verification plan"].source_anchor_ids) == {
        prose_plan_anchor.id,
        table_plan_anchor.id,
    }
    assert set(by_label["verification plan"].aliases) == {
        "Verification Plan",
        "Verification plan",
    }

    assert len(unified.assertion_proposals) == 1
    assertion = unified.assertion_proposals[0]
    assert assertion.subject_id == by_label["verification plan"].id
    assert assertion.object.kind == "entity"
    assert assertion.object.entity_id == by_label["independent review"].id
    assert assertion.normative_force is NormativeForce.REQUIREMENT
    assert set(assertion.evidence_anchor_ids) == {
        prose_plan_anchor.id,
        prose_criterion_anchor.id,
        table_plan_anchor.id,
        table_criterion_anchor.id,
    }


def test_same_label_in_incompatible_sibling_classes_is_not_merged() -> None:
    role_anchor = _anchor("role-anchor", "C1", "Owner", 0)
    product_anchor = _anchor("product-anchor", "C2", "Owner", 0)
    generic_anchor = _anchor("generic-anchor", "C3", "Owner", 0)
    proposal = _proposal(
        "run",
        entities=(
            KnowledgeEntityProposal(
                id="role",
                class_iri=f"{STAT}Role",
                normalized_label="owner",
                source_anchor_ids=(role_anchor.id,),
                confidence=1.0,
            ),
            KnowledgeEntityProposal(
                id="product",
                class_iri=f"{STAT}WorkProduct",
                normalized_label="owner",
                source_anchor_ids=(product_anchor.id,),
                confidence=1.0,
            ),
            KnowledgeEntityProposal(
                id="generic",
                class_iri=f"{STAT}EngineeringEntity",
                normalized_label="owner",
                source_anchor_ids=(generic_anchor.id,),
                confidence=0.7,
            ),
        ),
        anchors=(role_anchor, product_anchor, generic_anchor),
    )

    unified = DocumentKnowledgeProposalUnifier().unify((proposal,), proposal_run_id="unified-run")

    assert {entity.class_iri for entity in unified.entity_proposals} == {
        f"{STAT}Role",
        f"{STAT}WorkProduct",
        f"{STAT}EngineeringEntity",
    }


def test_unification_is_independent_of_input_order() -> None:
    first_anchor = _anchor("a1", "C1", "Plan", 0)
    second_anchor = _anchor("a2", "C1", "Plan", 10)
    first = _proposal(
        "a-run",
        entities=(
            KnowledgeEntityProposal(
                id="a-entity",
                class_iri=f"{STAT}Plan",
                normalized_label="plan",
                source_anchor_ids=(first_anchor.id,),
                confidence=0.8,
            ),
        ),
        anchors=(first_anchor,),
    )
    second = _proposal(
        "b-run",
        entities=(
            KnowledgeEntityProposal(
                id="b-entity",
                class_iri=f"{STAT}WorkProduct",
                normalized_label="plan",
                source_anchor_ids=(second_anchor.id,),
                confidence=0.9,
            ),
        ),
        anchors=(second_anchor,),
    )
    unifier = DocumentKnowledgeProposalUnifier()

    forward = unifier.unify((first, second), proposal_run_id="resolved")
    reverse = unifier.unify((second, first), proposal_run_id="resolved")

    assert forward == reverse
    assert forward.entity_proposals[0].class_iri == f"{STAT}Plan"


def test_assertions_from_different_source_clauses_remain_distinct() -> None:
    anchors = (
        _anchor("e1", "C1", "Plan", 0),
        _anchor("e2", "C2", "Plan", 0),
        _anchor("e3", "C1", "Criterion", 10),
        _anchor("e4", "C2", "Criterion", 10),
    )
    entities = (
        KnowledgeEntityProposal(
            id="plan",
            class_iri=f"{STAT}Plan",
            normalized_label="plan",
            source_anchor_ids=("e1", "e2"),
            confidence=1.0,
        ),
        KnowledgeEntityProposal(
            id="criterion",
            class_iri=f"{STAT}Criterion",
            normalized_label="criterion",
            source_anchor_ids=("e3", "e4"),
            confidence=1.0,
        ),
    )
    assertions = tuple(
        NormativeAssertionProposal(
            id=f"assertion-{clause}",
            source_clause_id=ClauseId(value=clause),
            subject_id="plan",
            predicate=f"{STAT}requires",
            object=EntityAssertionObject(entity_id="criterion"),
            evidence_anchor_ids=(evidence,),
            confidence=1.0,
        )
        for clause, evidence in (("C1", "e1"), ("C2", "e2"))
    )
    proposal = _proposal(
        "run",
        entities=entities,
        assertions=assertions,
        anchors=anchors,
    )

    unified = DocumentKnowledgeProposalUnifier().unify((proposal,), proposal_run_id="unified-run")

    assert len(unified.assertion_proposals) == 2
    assert {item.source_clause_id.value for item in unified.assertion_proposals} == {"C1", "C2"}


def test_rejects_mismatched_documents_or_ontology_selections() -> None:
    anchor = _anchor("a1", "C1", "Plan", 0)
    entity = KnowledgeEntityProposal(
        id="plan",
        class_iri=f"{STAT}Plan",
        normalized_label="plan",
        source_anchor_ids=(anchor.id,),
        confidence=1.0,
    )
    first = _proposal("first", entities=(entity,), anchors=(anchor,))
    other_document = _proposal(
        "other-document",
        entities=(entity,),
        anchors=(anchor,),
        document_key="OTHER",
    )
    other_ontology = _proposal("other-ontology", entities=(entity,), anchors=(anchor,)).model_copy(
        update={"ontology_versions": tuple(reversed(ONTOLOGIES))}
    )
    unifier = DocumentKnowledgeProposalUnifier()

    with pytest.raises(ValueError, match="same document"):
        unifier.unify((first, other_document), proposal_run_id="resolved")
    with pytest.raises(ValueError, match="same ordered ontology selection"):
        unifier.unify((first, other_ontology), proposal_run_id="resolved")
