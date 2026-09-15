from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationEvaluator,
    GoldenEvidenceSpan,
    GoldenKnowledgeEntity,
    GoldenNormativeAssertion,
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
CLAUSE = ClauseId(value="clause-1")
TEXT = "The verification plan shall specify the verification criteria."
START = TEXT.index("verification plan")
END = len(TEXT)
HASH = hashlib.sha256(TEXT[START:END].encode()).hexdigest()


def _suite(*, force: NormativeForce = NormativeForce.REQUIREMENT) -> AssertionGoldenSuite:
    return AssertionGoldenSuite(
        id="assertion-dev",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(
            AssertionGoldenCase(
                source_document_key="EN50716",
                entities=(
                    GoldenKnowledgeEntity(
                        id="g-plan",
                        class_iri=f"{STAT}VerificationPlan",
                        normalized_label="Verification Plan",
                    ),
                    GoldenKnowledgeEntity(
                        id="g-criteria",
                        class_iri=f"{STAT}Criterion",
                        normalized_label="Verification Criteria",
                    ),
                ),
                assertions=(
                    GoldenNormativeAssertion(
                        id="g-assertion",
                        source_clause_id=CLAUSE,
                        subject_id="g-plan",
                        predicate=f"{STAT}specifies",
                        object=EntityAssertionObject(entity_id="g-criteria"),
                        normative_force=force,
                        evidence=(
                            GoldenEvidenceSpan(
                                clause_id=CLAUSE,
                                start_offset=START,
                                end_offset=END,
                                content_hash=HASH,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _proposal(
    *,
    force: NormativeForce = NormativeForce.REQUIREMENT,
    predicate: str = f"{STAT}specifies",
    start_offset: int = START,
) -> DocumentKnowledgeProposal:
    anchor = EvidenceAnchor(
        id="anchor-1",
        clause_id=CLAUSE,
        start_offset=start_offset,
        end_offset=END,
        content_hash=HASH,
    )
    return DocumentKnowledgeProposal(
        proposal_run_id="run-1",
        source_document_key="EN50716",
        ontology_versions=("standards-atlas-core@2.0.0",),
        evidence_anchors=(anchor,),
        entity_proposals=(
            KnowledgeEntityProposal(
                id="proposal-plan",
                class_iri=f"{STAT}VerificationPlan",
                normalized_label="  verification   PLAN ",
                source_anchor_ids=(anchor.id,),
                confidence=0.9,
            ),
            KnowledgeEntityProposal(
                id="proposal-criteria",
                class_iri=f"{STAT}Criterion",
                normalized_label="verification criteria",
                source_anchor_ids=(anchor.id,),
                confidence=0.8,
            ),
        ),
        assertion_proposals=(
            NormativeAssertionProposal(
                id="proposal-assertion",
                source_clause_id=CLAUSE,
                subject_id="proposal-plan",
                predicate=predicate,
                object=EntityAssertionObject(entity_id="proposal-criteria"),
                normative_force=force,
                evidence_anchor_ids=(anchor.id,),
                confidence=0.85,
            ),
        ),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="test",
            extractor_version="1.0.0",
        ),
    )


def test_exact_semantic_match_is_independent_of_proposal_ids_and_label_case() -> None:
    report = AssertionQualificationEvaluator().evaluate(_suite(), (_proposal(),))

    assert report.aggregate.entities.true_positive == 2
    assert report.aggregate.entities.precision == 1.0
    assert report.aggregate.assertions.true_positive == 1
    assert report.aggregate.assertions.f1 == 1.0
    assert report.aggregate.predicate_accuracy.accuracy == 1.0
    assert report.aggregate.normative_force_accuracy.accuracy == 1.0
    assert report.aggregate.grounding_accuracy.accuracy == 1.0
    assert report.aggregate.exact_assertion_accuracy.accuracy == 1.0
    assert report.cases[0].assertion_false_positive_ids == ()
    assert report.cases[0].assertion_false_negative_ids == ()


def test_wrong_predicate_is_assertion_fp_fn_and_endpoint_predicate_error() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(predicate=f"{STAT}requires"),),
    )

    assert report.aggregate.assertions.true_positive == 0
    assert report.aggregate.assertions.false_positive == 1
    assert report.aggregate.assertions.false_negative == 1
    assert report.aggregate.predicate_accuracy.evaluated == 1
    assert report.aggregate.predicate_accuracy.accuracy == 0.0
    assert report.aggregate.normative_force_accuracy.accuracy is None


def test_force_and_grounding_are_measured_after_semantic_assertion_match() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(force=NormativeForce.RECOMMENDATION, start_offset=START + 1),),
    )

    assert report.aggregate.assertions.true_positive == 1
    assert report.aggregate.normative_force_accuracy.accuracy == 0.0
    assert report.aggregate.grounding_accuracy.accuracy == 0.0
    assert report.aggregate.exact_assertion_accuracy.accuracy == 0.0


def test_missing_proposal_is_reported_as_false_negatives_not_an_exception() -> None:
    report = AssertionQualificationEvaluator().evaluate(_suite(), ())

    assert report.aggregate.entities.false_negative == 2
    assert report.aggregate.assertions.false_negative == 1
    assert report.cases[0].proposal_run_id is None
    assert report.aggregate.predicate_accuracy.accuracy is None


def test_proposal_ontology_binding_must_match_golden_suite() -> None:
    proposal = _proposal().model_copy(update={"ontology_versions": ("other@1.0.0",)})
    with pytest.raises(ValueError, match="ontology versions do not match"):
        AssertionQualificationEvaluator().evaluate(_suite(), (proposal,))


def test_extra_proposal_document_is_rejected() -> None:
    proposal = _proposal().model_copy(update={"source_document_key": "OTHER"})
    with pytest.raises(ValueError, match="outside the golden suite"):
        AssertionQualificationEvaluator().evaluate(_suite(), (proposal,))


def test_evaluation_report_is_independent_of_proposal_input_order() -> None:
    first_case = _suite().cases[0]
    suite = _suite().model_copy(
        update={
            "cases": (
                first_case,
                first_case.model_copy(update={"source_document_key": "EN50716-2"}),
            )
        }
    )
    first = _proposal()
    second = first.model_copy(
        update={"proposal_run_id": "run-2", "source_document_key": "EN50716-2"}
    )

    left = AssertionQualificationEvaluator().evaluate(suite, (first, second))
    right = AssertionQualificationEvaluator().evaluate(suite, (second, first))

    assert left == right
