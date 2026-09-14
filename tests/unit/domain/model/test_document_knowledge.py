import hashlib

import pytest

from standards_atlas.domain.model import (
    ApplicabilityPolarity,
    Clause,
    ClauseApplicability,
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
    LiteralAssertionObject,
    NormativeAssertion,
    NormativeForce,
    StandardReference,
    TextBlock,
)


def _clause() -> Clause:
    return Clause(
        id=ClauseId(value="C1"),
        reference=StandardReference(standard="Example", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="C1-text", text="The verification plan shall define criteria."),),
    )


def _provenance() -> KnowledgeProvenance:
    return KnowledgeProvenance(
        method=KnowledgeDerivationMethod.HUMAN_AUTHORED,
        producer="test-review",
        review_reference="review:1",
    )


def _knowledge() -> DocumentKnowledge:
    text = _clause().plain_text
    anchor = EvidenceAnchor(
        id="anchor:C1:0",
        clause_id=ClauseId(value="C1"),
        start_offset=4,
        end_offset=21,
        content_hash=hashlib.sha256(text[4:21].encode()).hexdigest(),
    )
    plan = KnowledgeEntity(
        id="entity:verification-plan",
        class_iri="http://lunetix.org/standards-atlas#EngineeringArtifact",
        normalized_label="verification plan",
        source_anchor_ids=(anchor.id,),
    )
    criteria = KnowledgeEntity(
        id="entity:verification-criteria",
        class_iri="http://lunetix.org/standards-atlas#Concept",
        normalized_label="verification criteria",
        source_anchor_ids=(anchor.id,),
    )
    assertion = NormativeAssertion(
        id="assertion:C1:1",
        source_clause_id=ClauseId(value="C1"),
        subject_id=plan.id,
        predicate="shall_define",
        object=EntityAssertionObject(entity_id=criteria.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        provenance=_provenance(),
    )
    return DocumentKnowledge(
        evidence_anchors=(anchor,),
        entities=(plan, criteria),
        assertions=(assertion,),
    )


def test_document_knowledge_schema_starts_at_one_and_roundtrips() -> None:
    knowledge = _knowledge()

    payload = knowledge.model_dump(mode="json")
    restored = DocumentKnowledge.model_validate(payload)

    assert payload["schema_version"] == 1
    assert restored == knowledge
    assert restored.assertions[0].normative_force is NormativeForce.REQUIREMENT


@pytest.mark.parametrize("marker", [9, True, 1.0, "1"])
def test_document_knowledge_rejects_non_current_or_wrongly_typed_schema(marker: object) -> None:
    payload = _knowledge().model_dump(mode="python")
    payload["schema_version"] = marker

    with pytest.raises(ValueError, match="unsupported document knowledge schema version"):
        DocumentKnowledge.model_validate(payload)


def test_document_knowledge_rejects_unknown_entity_and_evidence_references() -> None:
    knowledge = _knowledge()
    assertion = knowledge.assertions[0].model_copy(
        update={"object": EntityAssertionObject(entity_id="entity:missing")}
    )
    with pytest.raises(ValueError, match="unknown objects"):
        DocumentKnowledge(
            evidence_anchors=knowledge.evidence_anchors,
            entities=knowledge.entities,
            assertions=(assertion,),
        )

    entity = knowledge.entities[0].model_copy(update={"source_anchor_ids": ("anchor:missing",)})
    with pytest.raises(ValueError, match="unknown evidence anchors"):
        DocumentKnowledge(
            evidence_anchors=knowledge.evidence_anchors,
            entities=(entity,),
        )


def test_engineering_document_validates_knowledge_against_canonical_clause_text() -> None:
    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Example",
        document_type=DocumentType.STANDARD,
        clauses=(_clause(),),
        knowledge=_knowledge(),
    )

    assert document.knowledge.assertions[0].source_clause_id.value == "C1"

    invalid_anchor = document.knowledge.evidence_anchors[0].model_copy(
        update={"content_hash": "0" * 64}
    )
    invalid_knowledge = document.knowledge.model_copy(
        update={"evidence_anchors": (invalid_anchor,)}
    )
    with pytest.raises(ValueError, match="content hash does not match"):
        EngineeringDocument(
            key=document.key,
            title=document.title,
            document_type=document.document_type,
            clauses=document.clauses,
            knowledge=invalid_knowledge,
        )


def test_assertions_support_literal_objects_without_rdf_serialization() -> None:
    knowledge = _knowledge()
    assertion = knowledge.assertions[0].model_copy(
        update={"object": LiteralAssertionObject(value=True)}
    )

    updated = DocumentKnowledge(
        evidence_anchors=knowledge.evidence_anchors,
        entities=knowledge.entities,
        assertions=(assertion,),
    )

    assert updated.assertions[0].object.value is True


def test_clause_applicability_is_minimal_presence_and_polarity_contract() -> None:
    assert ClauseApplicability().model_dump(mode="json") == {
        "present": False,
        "polarity": None,
    }
    assert (
        ClauseApplicability(
            present=True,
            polarity=ApplicabilityPolarity.EXCLUDED,
        ).polarity
        is ApplicabilityPolarity.EXCLUDED
    )
    assert ClauseApplicability(present=True).polarity is None

    with pytest.raises(ValueError, match="absent applicability"):
        ClauseApplicability(present=False, polarity=ApplicabilityPolarity.INCLUDED)
