from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.formal_semantics import DeterministicFormalSemanticProjector
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentKnowledge,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    KnowledgeDerivationMethod,
    KnowledgeEntity,
    KnowledgeProvenance,
    NormativeAssertion,
    NormativeForce,
    SemanticBox,
    SemanticResource,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
ONTOLOGY_VERSIONS = (
    "standards-atlas-core@2.0.0",
    "functional-safety@2.0.0",
)


def _document(
    *,
    unknown_class: bool = False,
    unknown_predicate: bool = False,
) -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="C1"),
        reference=StandardReference(standard="Example", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(
            TextBlock(
                id="C1-text",
                text="The verification plan shall specify the verification criteria.",
            ),
        ),
    )
    anchor_text = "verification plan shall specify the verification criteria"
    start = clause.plain_text.index(anchor_text)
    end = start + len(anchor_text)
    anchor = EvidenceAnchor(
        id="anchor:C1:knowledge",
        clause_id=clause.id,
        start_offset=start,
        end_offset=end,
        content_hash=hashlib.sha256(anchor_text.encode("utf-8")).hexdigest(),
    )
    plan = KnowledgeEntity(
        id="entity:verification-plan",
        class_iri=(
            "https://example.invalid/UnknownClass" if unknown_class else f"{STAT}VerificationPlan"
        ),
        normalized_label="verification plan",
        source_anchor_ids=(anchor.id,),
    )
    criteria = KnowledgeEntity(
        id="entity:verification-criteria",
        class_iri=f"{STAT}VerificationCriterion",
        normalized_label="verification criteria",
        source_anchor_ids=(anchor.id,),
    )
    assertion = NormativeAssertion(
        id="assertion:C1:specifies",
        source_clause_id=clause.id,
        subject_id=plan.id,
        predicate=(
            "https://example.invalid/unknownPredicate" if unknown_predicate else f"{STAT}specifies"
        ),
        object=EntityAssertionObject(entity_id=criteria.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        provenance=KnowledgeProvenance(
            method=KnowledgeDerivationMethod.MODEL_ASSISTED,
            producer="qualified-extractor",
            producer_version="2.0",
            qualification_reference="qualification:42",
            review_reference="review:7",
            input_hash="input:abc",
        ),
    )
    return EngineeringDocument(
        key=DocumentKey(value="EXAMPLE"),
        title="Example",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
        knowledge=DocumentKnowledge(
            ontology_versions=ONTOLOGY_VERSIONS,
            evidence_anchors=(anchor,),
            entities=(plan, criteria),
            assertions=(assertion,),
        ),
    )


def test_projector_projects_only_accepted_document_knowledge_into_abox() -> None:
    document = _document()

    projection = DeterministicFormalSemanticProjector().project(document)

    assert projection.ontology_versions == ONTOLOGY_VERSIONS
    knowledge_assertions = [
        assertion
        for assertion in projection.assertions
        if "/knowledge/entity/" in assertion.subject.iri
    ]
    type_assertions = [
        assertion for assertion in knowledge_assertions if assertion.predicate.iri == RDF_TYPE
    ]
    relation_assertions = [
        assertion
        for assertion in knowledge_assertions
        if assertion.predicate.iri == f"{STAT}specifies"
    ]

    assert len(type_assertions) == 2
    assert {assertion.object.iri for assertion in type_assertions} == {
        f"{STAT}VerificationPlan",
        f"{STAT}VerificationCriterion",
    }
    assert all(assertion.box is SemanticBox.ABOX for assertion in type_assertions)
    assert all(assertion.evidence_ids == ("anchor:C1:knowledge",) for assertion in type_assertions)

    assert len(relation_assertions) == 1
    relation = relation_assertions[0]
    assert relation.box is SemanticBox.ABOX
    assert isinstance(relation.object, SemanticResource)
    assert relation.object.iri.endswith("/knowledge/entity/entity%3Averification-criteria")
    assert relation.evidence_ids == ("anchor:C1:knowledge",)
    assert len(relation.context_ids) == 2
    assert relation.context_ids[0].iri.endswith("context/EXAMPLE/C1")
    assert "/knowledge/assertion/assertion%3AC1%3Aspecifies" in relation.context_ids[1].iri

    source_context = next(
        context for context in projection.contexts if context.id == relation.context_ids[0]
    )
    source_clause = next(
        facet for facet in source_context.facets if facet.predicate.iri == f"{STAT}sourceClause"
    )
    assert isinstance(source_clause.value, SemanticResource)
    assert source_clause.value.iri.endswith("document/EXAMPLE/clause/C1")

    knowledge_context = next(
        context for context in projection.contexts if context.id == relation.context_ids[1]
    )
    facets = {facet.predicate.iri: facet.value.value for facet in knowledge_context.facets}
    assert facets == {
        f"{STAT}normativeForce": "requirement",
        f"{STAT}knowledgeDerivationMethod": "model_assisted",
        f"{STAT}knowledgeProducer": "qualified-extractor",
        f"{STAT}knowledgeProducerVersion": "2.0",
        f"{STAT}qualificationReference": "qualification:42",
        f"{STAT}reviewReference": "review:7",
        f"{STAT}knowledgeInputHash": "input:abc",
    }


def test_projector_rejects_knowledge_class_not_declared_by_bound_ontologies() -> None:
    with pytest.raises(ValueError, match="terms not declared.*UnknownClass"):
        DeterministicFormalSemanticProjector().project(_document(unknown_class=True))


def test_projector_rejects_knowledge_predicate_not_declared_by_bound_ontologies() -> None:
    with pytest.raises(ValueError, match="terms not declared.*unknownPredicate"):
        DeterministicFormalSemanticProjector().project(_document(unknown_predicate=True))
