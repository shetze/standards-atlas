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
    EvidenceSourceKind,
    KnowledgeDerivationMethod,
    KnowledgeEntity,
    KnowledgeProvenance,
    LiteralAssertionObject,
    NormativeAssertion,
    NormativeForce,
    StandardReference,
    TextBlock,
)

STAT = "http://lunetix.org/standards-atlas#"
ONTOLOGY_VERSIONS = (
    "standards-atlas-core@2.0.0",
    "functional-safety@2.1.0",
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
        source_clause_id=ClauseId(value="C1"),
        source_kind=EvidenceSourceKind.BODY,
        start_offset=4,
        end_offset=21,
        content_hash=hashlib.sha256(text[4:21].encode()).hexdigest(),
    )
    plan = KnowledgeEntity(
        id="entity:verification-plan",
        class_iri=f"{STAT}VerificationPlan",
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
        id="assertion:C1:1",
        source_clause_id=ClauseId(value="C1"),
        subject_id=plan.id,
        predicate=f"{STAT}specifies",
        object=EntityAssertionObject(entity_id=criteria.id),
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        provenance=_provenance(),
    )
    return DocumentKnowledge(
        ontology_versions=ONTOLOGY_VERSIONS,
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
            ontology_versions=knowledge.ontology_versions,
            evidence_anchors=knowledge.evidence_anchors,
            entities=knowledge.entities,
            assertions=(assertion,),
        )

    entity = knowledge.entities[0].model_copy(update={"source_anchor_ids": ("anchor:missing",)})
    with pytest.raises(ValueError, match="unknown evidence anchors"):
        DocumentKnowledge(
            ontology_versions=knowledge.ontology_versions,
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
        ontology_versions=knowledge.ontology_versions,
        evidence_anchors=knowledge.evidence_anchors,
        entities=knowledge.entities,
        assertions=(assertion,),
    )

    assert updated.assertions[0].object.value is True


def test_document_knowledge_requires_ontology_binding_for_semantic_terms() -> None:
    knowledge = _knowledge()

    with pytest.raises(ValueError, match="requires ontology_versions"):
        DocumentKnowledge(
            evidence_anchors=knowledge.evidence_anchors,
            entities=knowledge.entities,
            assertions=knowledge.assertions,
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("class_iri", "VerificationPlan", "class_iri must be an absolute IRI"),
        ("predicate", "specifies", "predicate must be an absolute IRI"),
    ],
)
def test_document_knowledge_requires_absolute_semantic_iris(
    field: str,
    value: str,
    match: str,
) -> None:
    knowledge = _knowledge()
    if field == "class_iri":
        payload = knowledge.entities[0].model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValueError, match=match):
            KnowledgeEntity.model_validate(payload)
        return

    payload = knowledge.assertions[0].model_dump(mode="python")
    payload[field] = value
    with pytest.raises(ValueError, match=match):
        NormativeAssertion.model_validate(payload)


def test_engineering_document_rejects_unknown_knowledge_source_clause() -> None:
    knowledge = _knowledge()
    invalid_assertion = knowledge.assertions[0].model_copy(
        update={"source_clause_id": ClauseId(value="missing")}
    )
    invalid_knowledge = knowledge.model_copy(update={"assertions": (invalid_assertion,)})

    with pytest.raises(ValueError, match="unknown source clause"):
        EngineeringDocument(
            key=DocumentKey(value="DOC"),
            title="Example",
            document_type=DocumentType.STANDARD,
            clauses=(_clause(),),
            knowledge=invalid_knowledge,
        )


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


def test_engineering_document_validates_heading_evidence_against_heading_surface() -> None:
    clause = Clause(
        id=ClauseId(value="H1"),
        reference=StandardReference(standard="Example", clause="12.3.1.3"),
        clause_type=ClauseType.CLAUSE,
        heading="Emergency Operation Time Interval calculation if no PMHF value is available",
        content=(TextBlock(id="H1-text", text="If the method is used, the criteria apply."),),
    )
    heading = clause.heading or ""
    anchor = EvidenceAnchor(
        id="anchor:H1:heading",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=len(heading),
        content_hash=hashlib.sha256(heading.encode()).hexdigest(),
    )
    knowledge = DocumentKnowledge(evidence_anchors=(anchor,))

    document = EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Example",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
        knowledge=knowledge,
    )

    assert document.knowledge.evidence_anchors[0].source_kind is EvidenceSourceKind.HEADING


def test_engineering_document_rejects_heading_anchor_when_heading_is_missing() -> None:
    clause = _clause()
    anchor = EvidenceAnchor(
        id="anchor:C1:heading",
        source_clause_id=clause.id,
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=4,
    )

    with pytest.raises(ValueError, match="references a missing clause heading"):
        EngineeringDocument(
            key=DocumentKey(value="DOC"),
            title="Example",
            document_type=DocumentType.STANDARD,
            clauses=(clause,),
            knowledge=DocumentKnowledge(evidence_anchors=(anchor,)),
        )
