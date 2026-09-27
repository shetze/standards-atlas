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
from standards_atlas.domain.model import (
    ClauseId,
    DocumentKnowledgeProposal,
    EntityAssertionObject,
    EvidenceAnchor,
    EvidenceSourceKind,
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
        audit=AssertionAuditBinding(review_id="test", review_version="1", audit_sha256="b" * 64),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(
            AssertionGoldenCase(
                source_document_key="EN50716",
                clause_id=CLAUSE,
                reference="EN50716:1",
                canonical_reference="EN50716 1",
                text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
                source_sha256="a" * 64,
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
                                source_document_key="EN50716",
                                source_kind="body",
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
        source_clause_id=CLAUSE,
        source_kind=EvidenceSourceKind.BODY,
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
                proposal_clause_ids=(CLAUSE,),
                class_iri=f"{STAT}VerificationPlan",
                normalized_label="  verification   PLAN ",
                source_anchor_ids=(anchor.id,),
                confidence=0.9,
            ),
            KnowledgeEntityProposal(
                id="proposal-criteria",
                proposal_clause_ids=(CLAUSE,),
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
    assert report.cases[0].provenance is None
    assert report.cases[0].candidate_status == "missing"
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


def test_native_document_is_projected_to_selected_local_cases_only() -> None:
    base = _suite()
    second = base.cases[0].model_copy(
        update={
            "clause_id": ClauseId(value="clause-2"),
            "reference": "EN50716:2",
            "canonical_reference": "EN50716 2",
            "entities": (base.cases[0].entities[0],),
            "assertions": (),
        }
    )
    suite = AssertionGoldenSuite.model_validate(
        base.model_copy(update={"cases": (base.cases[0], second)}).model_dump(mode="json")
    )
    native = _proposal()
    extra_entities = tuple(
        native.entity_proposals[0].model_copy(
            update={
                "id": entity_id,
                "proposal_clause_ids": (ClauseId(value=clause_id),),
            }
        )
        for entity_id, clause_id in (("entity-only", "clause-2"), ("not-selected", "clause-3"))
    )
    native = native.model_copy(
        update={
            "entity_proposals": (*native.entity_proposals, *extra_entities),
        }
    )
    report = AssertionQualificationEvaluator().evaluate(suite, (native,))
    assert report.aggregate.documents == 1
    assert report.aggregate.clauses == report.aggregate.candidate_clauses == 2
    assert report.aggregate.entities.expected == report.aggregate.entities.predicted == 3
    assert report.aggregate.entities.true_positive == 3
    assert report.cases[1].entities.predicted == 1
    assert report.cases[1].assertions.predicted == 0
    assert len(report.proposal_sources) == 1
    assert report.cases[0].provenance == report.cases[1].provenance
    assert report.cases[0].candidate_sha256 != report.cases[1].candidate_sha256
    assert [case.clause_id.value for case in report.cases] == ["clause-1", "clause-2"]


def test_projection_retains_endpoint_entities_but_not_evidence_only_cases() -> None:
    from standards_atlas.application.assertion_qualification.projection import (
        project_native_proposal,
    )

    native = _proposal()
    foreign = ClauseId(value="foreign")
    native = native.model_copy(
        update={
            "entity_proposals": tuple(
                item.model_copy(update={"proposal_clause_ids": (foreign,)})
                for item in native.entity_proposals
            ),
            "evidence_anchors": tuple(
                item.model_copy(update={"source_clause_id": foreign})
                for item in native.evidence_anchors
            ),
        }
    )
    view = project_native_proposal(native, CLAUSE.value)
    assert len(view.entities) == 2  # endpoints are retained despite foreign assignment
    assert len(view.assertions) == 1
    assert view.assertions[0].evidence[0].source_clause_id == "foreign"
    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))
    assert report.aggregate.clauses == 1
    assert report.cases[0].assertions.true_positive == 1


def test_current_report_validates_distinct_documents_and_case_counts() -> None:
    from standards_atlas.application.assertion_qualification import AssertionQualificationReport

    report = AssertionQualificationEvaluator().evaluate(_suite(), (_proposal(),))
    payload = report.model_dump(mode="json")
    payload["aggregate"]["clauses"] = 2
    with pytest.raises(ValueError, match="clause count"):
        AssertionQualificationReport.model_validate(payload)
    payload = report.model_dump(mode="json")
    payload["aggregate"]["documents"] = 2
    with pytest.raises(ValueError, match="document count"):
        AssertionQualificationReport.model_validate(payload)
    payload = report.model_dump(mode="json")
    del payload["evaluation_contract"]
    with pytest.raises(ValueError, match="evaluation_contract"):
        AssertionQualificationReport.model_validate(payload)
