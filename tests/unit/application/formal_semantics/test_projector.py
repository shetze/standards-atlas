from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.context import SourceAccessPolicy
from standards_atlas.application.formal_semantics import (
    DeterministicFormalSemanticProjector,
    FormalEvidenceResolutionStatus,
    FormalProjectionEvidenceResolver,
)
from standards_atlas.domain.model import (
    ArtifactLineage,
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentKnowledge,
    DocumentType,
    EngineeringDocument,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeDerivationMethod,
    KnowledgeEntity,
    KnowledgeProvenance,
    NormativeAssertion,
    NormativeForce,
    SemanticBox,
    SemanticResource,
    StandardReference,
    TextBlock,
    artifact_reference,
)

STAT = "http://lunetix.org/standards-atlas#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
ONTOLOGY_VERSIONS = (
    "standards-atlas-core@2.0.0",
    "functional-safety@2.1.0",
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
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.BODY,
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


def _document_with_multisurface_evidence() -> EngineeringDocument:
    base = _document()
    clause = base.clauses[0].with_baseline_updates(heading="Verification context")
    heading_anchor = EvidenceAnchor(
        id="anchor:C1:heading",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=len(clause.heading or ""),
        content_hash=hashlib.sha256((clause.heading or "").encode()).hexdigest(),
    )
    knowledge = base.knowledge.model_copy(
        update={
            "evidence_anchors": (*base.knowledge.evidence_anchors, heading_anchor),
            "entities": tuple(
                entity.model_copy(
                    update={"source_anchor_ids": (*entity.source_anchor_ids, heading_anchor.id)}
                )
                for entity in base.knowledge.entities
            ),
            "assertions": tuple(
                assertion.model_copy(
                    update={
                        "evidence_anchor_ids": (
                            *assertion.evidence_anchor_ids,
                            heading_anchor.id,
                        )
                    }
                )
                for assertion in base.knowledge.assertions
            ),
        }
    )
    candidate = base.model_copy(update={"clauses": (clause,), "knowledge": knowledge})
    document = EngineeringDocument.model_validate(candidate.model_dump(mode="json"))
    lineage = ArtifactLineage(artifact=artifact_reference("engineering_document", document))
    return EngineeringDocument.model_validate(
        document.model_copy(update={"lineage": lineage}).model_dump(mode="json")
    )


def test_every_formal_projection_evidence_id_resolves_to_canonical_owner_and_surface() -> None:
    document = _document_with_multisurface_evidence()
    projection = DeterministicFormalSemanticProjector().project(document)
    resolver = FormalProjectionEvidenceResolver(document, projection)

    resolutions = [
        resolution
        for assertion in projection.assertions
        for resolution in resolver.resolve_assertion_evidence(assertion)
    ]

    assert resolutions
    assert all(item.status is FormalEvidenceResolutionStatus.RESOLVED for item in resolutions)
    assert {item.kind for item in resolutions} == {"knowledge_anchor", "artifact_lineage"}
    knowledge_sources = [item.source for item in resolutions if item.kind == "knowledge_anchor"]
    assert any(
        item is not None and item.identity.source_kind is EvidenceSourceKind.BODY
        for item in knowledge_sources
    )
    assert any(
        item is not None and item.identity.source_kind is EvidenceSourceKind.HEADING
        for item in knowledge_sources
    )


def test_formal_evidence_resolution_honors_text_access_policy() -> None:
    document = _document_with_multisurface_evidence()
    projection = DeterministicFormalSemanticProjector().project(document)
    resolver = FormalProjectionEvidenceResolver(
        document,
        projection,
        access_policy=SourceAccessPolicy(
            allowed_document_keys=(document.key.value,),
            expose_text=False,
        ),
    )
    relation = next(
        item for item in projection.assertions if item.predicate.iri == f"{STAT}specifies"
    )

    resolutions = resolver.resolve_assertion_evidence(relation)

    assert resolutions
    assert all(item.status is FormalEvidenceResolutionStatus.NOT_AUTHORIZED for item in resolutions)
    assert all(item.source is not None and item.source.text is None for item in resolutions)
