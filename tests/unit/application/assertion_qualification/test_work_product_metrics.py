from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationEvaluator,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
)
from standards_atlas.application.formal_semantics import load_formal_class_hierarchy
from standards_atlas.domain.model import (
    ClauseId,
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
    KnowledgeEntityProposal,
    KnowledgeProposalProvenance,
    LiteralAssertionObject,
    NormativeAssertionProposal,
    NormativeForce,
)

STAT = "http://lunetix.org/standards-atlas#"
CLAUSE = ClauseId(value="wp-clause")
TEXT = "The safety requirement requires the verification plan."
TEXT_HASH = hashlib.sha256(TEXT.encode()).hexdigest()
ONTOLOGIES = ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")


def _suite(*, object_class: str = "VerificationPlan") -> AssertionGoldenSuite:
    evidence = GoldenEvidenceSpan(
        source_document_key="TEST",
        clause_id=CLAUSE,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(TEXT),
        content_hash=TEXT_HASH,
    )
    return AssertionGoldenSuite(
        id="wp-dev",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(review_id="wp", review_version="1", audit_sha256="a" * 64),
        ontology_versions=ONTOLOGIES,
        cases=(
            AssertionGoldenCase(
                source_document_key="TEST",
                clause_id=CLAUSE,
                reference="TEST:1",
                canonical_reference="TEST 1",
                text_sha256=TEXT_HASH,
                source_sha256="b" * 64,
                entities=(
                    GoldenKnowledgeEntity(
                        id="g-req",
                        class_iri=f"{STAT}SafetyRequirement",
                        normalized_label="safety requirement",
                    ),
                    GoldenKnowledgeEntity(
                        id="g-wp",
                        class_iri=f"{STAT}{object_class}",
                        normalized_label="verification plan",
                    ),
                ),
                assertions=(
                    GoldenNormativeAssertion(
                        id="g-requires",
                        source_clause_id=CLAUSE,
                        subject_id="g-req",
                        predicate=f"{STAT}requires",
                        object=EntityAssertionObject(entity_id="g-wp"),
                        normative_force=NormativeForce.REQUIREMENT,
                        evidence=(evidence,),
                    ),
                ),
            ),
        ),
    )


def _proposal(
    *,
    object_class: str = "VerificationPlan",
    predicate: str = "requires",
    literal_object: bool = False,
    reverse: bool = False,
) -> DocumentKnowledgeProposal:
    anchor = EvidenceAnchor(
        id="anchor",
        source_clause_id=CLAUSE,
        source_kind=EvidenceSourceKind.BODY,
        start_offset=0,
        end_offset=len(TEXT),
        content_hash=TEXT_HASH,
    )
    req = KnowledgeEntityProposal(
        id="p-req",
        proposal_clause_ids=(CLAUSE,),
        class_iri=f"{STAT}SafetyRequirement",
        normalized_label="safety requirement",
        source_anchor_ids=(anchor.id,),
        confidence=0.9,
    )
    wp = KnowledgeEntityProposal(
        id="p-wp",
        proposal_clause_ids=(CLAUSE,),
        class_iri=f"{STAT}{object_class}",
        normalized_label="verification plan",
        source_anchor_ids=(anchor.id,),
        confidence=0.9,
    )
    if literal_object:
        subject_id = req.id
        object_ = LiteralAssertionObject(value="verification plan")
    elif reverse:
        subject_id = wp.id
        object_ = EntityAssertionObject(entity_id=req.id)
    else:
        subject_id = req.id
        object_ = EntityAssertionObject(entity_id=wp.id)
    assertion = NormativeAssertionProposal(
        id="p-requires",
        source_clause_id=CLAUSE,
        subject_id=subject_id,
        predicate=f"{STAT}{predicate}",
        object=object_,
        normative_force=NormativeForce.REQUIREMENT,
        evidence_anchor_ids=(anchor.id,),
        confidence=0.9,
    )
    return DocumentKnowledgeProposal(
        proposal_run_id="run-wp",
        source_document_key="TEST",
        ontology_versions=ONTOLOGIES,
        evidence_anchors=(anchor,),
        entity_proposals=(req, wp),
        assertion_proposals=(assertion,),
        proposal_provenance=KnowledgeProposalProvenance(extractor="test", extractor_version="1"),
    )


def test_formal_hierarchy_recognises_direct_and_transitive_work_products_only() -> None:
    hierarchy = load_formal_class_hierarchy(ONTOLOGIES)

    assert hierarchy.is_ancestor_or_same(f"{STAT}WorkProduct", f"{STAT}EngineeringRecord")
    assert hierarchy.is_ancestor_or_same(f"{STAT}WorkProduct", f"{STAT}VerificationPlan")
    assert not hierarchy.is_ancestor_or_same(f"{STAT}WorkProduct", f"{STAT}EngineeringArtifact")


def test_work_product_metrics_use_bound_transitive_ontology_hierarchy() -> None:
    report = AssertionQualificationEvaluator().evaluate(_suite(), (_proposal(),))

    assert report.aggregate.work_product_precision.value == 1.0
    assert report.aggregate.work_product_recall.value == 1.0
    assert report.aggregate.work_product_class_accuracy.accuracy.value == 1.0
    assert report.aggregate.required_work_product_relation_recall.value == 1.0
    assert tuple(binding.reference for binding in report.ontology_resources) == ONTOLOGIES
    assert all(len(binding.resource_sha256) == 64 for binding in report.ontology_resources)


def test_generic_entity_prediction_remains_wrong_work_product_class_in_denominator() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(object_class="EngineeringEntity"),),
    )

    assert report.aggregate.work_product_precision.value is None
    assert report.aggregate.work_product_recall.value == 0.0
    assert report.aggregate.work_product_class_accuracy.evaluated == 1
    assert report.aggregate.work_product_class_accuracy.accuracy.value == 0.0
    assert report.aggregate.required_work_product_relation_recall.value == 0.0


def test_engineering_artifact_is_not_promoted_to_work_product_by_predicate_use() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(object_class="EngineeringArtifact", predicate="specifies"),),
    )

    assert report.aggregate.work_product_precision.value is None
    assert report.aggregate.work_product_recall.value == 0.0
    assert report.aggregate.required_work_product_relation_recall.value == 0.0


def test_required_work_product_relation_rejects_literal_and_wrong_direction() -> None:
    literal_report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(literal_object=True),),
    )
    reversed_report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(reverse=True),),
    )

    assert literal_report.aggregate.work_product_recall.value == 1.0
    assert literal_report.aggregate.required_work_product_relation_recall.value == 0.0
    assert reversed_report.aggregate.required_work_product_relation_recall.value == 0.0


def test_missing_strict_work_product_identity_stays_unclassified_until_review() -> None:
    native = _proposal().model_copy(
        update={
            "entity_proposals": (_proposal().entity_proposals[0],),
            "assertion_proposals": (),
        }
    )
    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))
    findings = report.cases[0].diagnostic_findings
    codes = {code.value for item in findings for code in item.codes}

    assert "unclassified_semantic_mismatch" in codes
    assert "missing_work_product" not in codes
    assert all(item.status.value == "needs_review" for item in findings)
    assert report.aggregate.work_product_recall.value == 0.0


def test_unavailable_bound_ontology_fails_instead_of_becoming_empty_wp_family() -> None:
    suite = _suite().model_copy(update={"ontology_versions": ("missing-ontology@9.9.9",)})
    proposal = _proposal().model_copy(update={"ontology_versions": ("missing-ontology@9.9.9",)})

    with pytest.raises((FileNotFoundError, ValueError)):
        AssertionQualificationEvaluator().evaluate(suite, (proposal,))
