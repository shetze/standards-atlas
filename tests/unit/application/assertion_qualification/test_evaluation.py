from __future__ import annotations

import hashlib

import pytest

from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionDiagnosticCode,
    AssertionDiagnosticOrigin,
    AssertionDiagnosticStatus,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationEvaluator,
    AssertionQualificationFinding,
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
    KnowledgeProposalViolation,
    KnowledgeProposalViolationKind,
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
    assert report.aggregate.entities.precision.value == 1.0
    assert report.aggregate.assertions.true_positive == 1
    assert report.aggregate.assertions.f1.value == 1.0
    assert report.aggregate.predicate_accuracy.accuracy.value == 1.0
    assert report.aggregate.normative_force_accuracy.accuracy.value == 1.0
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 1.0
    assert report.aggregate.exact_assertion_accuracy.accuracy.value == 1.0
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
    assert report.aggregate.predicate_accuracy.accuracy.value == 0.0
    assert report.aggregate.normative_force_accuracy.accuracy.value is None


def test_force_and_grounding_are_measured_after_semantic_assertion_match() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(force=NormativeForce.RECOMMENDATION, start_offset=START + 1),),
    )

    assert report.aggregate.assertions.true_positive == 1
    assert report.aggregate.normative_force_accuracy.accuracy.value == 0.0
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 0.0
    assert report.aggregate.exact_assertion_accuracy.accuracy.value == 0.0


def test_missing_proposal_is_reported_as_false_negatives_not_an_exception() -> None:
    report = AssertionQualificationEvaluator().evaluate(_suite(), ())

    assert report.aggregate.entities.false_negative == 2
    assert report.aggregate.assertions.false_negative == 1
    assert report.cases[0].provenance is None
    assert report.cases[0].candidate_status == "missing"
    assert report.aggregate.predicate_accuracy.accuracy.value is None
    assert report.cases[0].clause_exact_match.value is None
    assert report.aggregate.clause_exact_match.missing_candidates == 1
    assert report.aggregate.clause_exact_match.accuracy.value == 0.0


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


def test_wrong_entity_class_keeps_identity_match_but_fails_typed_and_class_metrics() -> None:
    native = _proposal()
    wrong_plan = native.entity_proposals[0].model_copy(update={"class_iri": f"{STAT}Plan"})
    native = native.model_copy(
        update={"entity_proposals": (wrong_plan, native.entity_proposals[1])}
    )

    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))

    assert report.aggregate.entities.true_positive == 2
    assert report.aggregate.typed_entities.true_positive == 1
    assert report.aggregate.typed_entities.false_positive == 1
    assert report.aggregate.typed_entities.false_negative == 1
    assert report.aggregate.entity_class_accuracy.evaluated == 2
    assert report.aggregate.entity_class_accuracy.accuracy.value == 0.5
    assert report.aggregate.assertions.true_positive == 1
    assert report.cases[0].clause_exact_match.value is False


def test_duplicate_prediction_counts_as_extra_and_makes_attribute_alignment_ambiguous() -> None:
    native = _proposal()
    duplicate = native.entity_proposals[0].model_copy(update={"id": "proposal-plan-duplicate"})
    native = native.model_copy(update={"entity_proposals": (*native.entity_proposals, duplicate)})

    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))
    case = report.cases[0]

    assert case.entities.expected == 2
    assert case.entities.predicted == 3
    assert case.entities.true_positive == 2
    assert case.entities.false_positive == 1
    assert case.entity_class_accuracy.evaluated == 1
    assert case.entity_class_accuracy.ambiguous_expected == 1
    assert case.entity_class_accuracy.ambiguous_predicted == 2
    ambiguous = [item for item in case.entity_alignment if item.status.value == "ambiguous"]
    assert len(ambiguous) == 1
    assert ambiguous[0].golden_ids == ("g-plan",)
    assert ambiguous[0].candidate_ids == ("proposal-plan", "proposal-plan-duplicate")


def test_one_candidate_does_not_satisfy_two_golden_entities_with_same_label() -> None:
    base = _suite()
    original = base.cases[0]
    suite = AssertionGoldenSuite.model_validate(
        base.model_copy(
            update={
                "cases": (
                    original.model_copy(
                        update={
                            "entities": (
                                original.entities[0],
                                original.entities[0].model_copy(
                                    update={"id": "g-plan-second", "class_iri": f"{STAT}Plan"}
                                ),
                            ),
                            "assertions": (),
                        }
                    ),
                )
            }
        ).model_dump(mode="json")
    )
    native = _proposal().model_copy(
        update={
            "entity_proposals": (_proposal().entity_proposals[0],),
            "assertion_proposals": (),
        }
    )

    report = AssertionQualificationEvaluator().evaluate(suite, (native,))
    case = report.cases[0]

    assert case.entities.true_positive == 1
    assert case.entities.false_negative == 1
    assert case.entity_class_accuracy.evaluated == 0
    assert case.entity_class_accuracy.ambiguous_expected == 2
    assert case.entity_class_accuracy.ambiguous_predicted == 1
    assert case.entity_class_accuracy.accuracy.value is None


def test_removed_label_restriction_is_not_a_strict_identity_match() -> None:
    base = _suite()
    restricted_case = base.cases[0].model_copy(
        update={
            "entities": (
                base.cases[0]
                .entities[0]
                .model_copy(update={"normalized_label": "verification plan only"}),
                base.cases[0].entities[1],
            )
        }
    )
    suite = AssertionGoldenSuite.model_validate(
        base.model_copy(update={"cases": (restricted_case,)}).model_dump(mode="json")
    )

    report = AssertionQualificationEvaluator().evaluate(suite, (_proposal(),))

    assert report.aggregate.entities.true_positive == 1
    assert report.aggregate.entities.false_positive == 1
    assert report.aggregate.entities.false_negative == 1
    assert report.aggregate.assertions.true_positive == 0


def test_empty_expected_and_predicted_sets_have_null_prf_but_exact_case_match() -> None:
    base = _suite()
    empty_case = base.cases[0].model_copy(update={"entities": (), "assertions": ()})
    suite = AssertionGoldenSuite.model_validate(
        base.model_copy(update={"cases": (empty_case,)}).model_dump(mode="json")
    )
    native = _proposal().model_copy(update={"entity_proposals": (), "assertion_proposals": ()})

    report = AssertionQualificationEvaluator().evaluate(suite, (native,))

    assert report.aggregate.entities.precision.value is None
    assert report.aggregate.entities.recall.value is None
    assert report.aggregate.entities.f1.value is None
    assert report.aggregate.entities.precision.status.value == "not_applicable"
    assert report.aggregate.assertions.f1.value is None
    assert report.cases[0].clause_exact_match.value is True
    assert report.aggregate.clause_exact_match.accuracy.value == 1.0


def test_nonempty_expected_with_empty_prediction_has_zero_recall_and_null_precision() -> None:
    native = _proposal().model_copy(update={"entity_proposals": (), "assertion_proposals": ()})

    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))

    assert report.aggregate.entities.precision.value is None
    assert report.aggregate.entities.recall.value == 0.0
    assert report.aggregate.entities.f1.value == 0.0
    assert report.aggregate.entities.under_extraction.value == 1.0
    assert report.aggregate.assertions.recall.value == 0.0
    assert report.cases[0].clause_exact_match.value is False


def test_entity_input_order_does_not_change_strict_metrics_or_alignment() -> None:
    native = _proposal()
    reversed_native = native.model_copy(
        update={"entity_proposals": tuple(reversed(native.entity_proposals))}
    )

    first = AssertionQualificationEvaluator().evaluate(_suite(), (native,))
    second = AssertionQualificationEvaluator().evaluate(_suite(), (reversed_native,))

    assert first.aggregate == second.aggregate
    assert first.cases[0].entity_alignment == second.cases[0].entity_alignment


def test_wrong_force_isolated_to_force_and_clause_exact_dimensions() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(force=NormativeForce.RECOMMENDATION),),
    )

    assert report.aggregate.assertions.true_positive == 1
    assert report.aggregate.predicate_accuracy.accuracy.value == 1.0
    assert report.aggregate.normative_force_accuracy.accuracy.value == 0.0
    assert report.aggregate.evidence_span_exact_match.accuracy.value == 1.0
    assert report.aggregate.exact_assertion_accuracy.accuracy.value == 0.0
    assert report.cases[0].clause_exact_match.value is False


def test_aggregate_attribute_accuracy_uses_global_support_not_case_average() -> None:
    base = _suite()
    first_case = base.cases[0].model_copy(
        update={"entities": (base.cases[0].entities[0],), "assertions": ()}
    )
    second_case = base.cases[0].model_copy(
        update={"source_document_key": "EN50716-2", "assertions": ()}
    )
    suite = AssertionGoldenSuite.model_validate(
        base.model_copy(update={"cases": (first_case, second_case)}).model_dump(mode="json")
    )

    first_native = _proposal().model_copy(
        update={
            "entity_proposals": (
                _proposal().entity_proposals[0].model_copy(update={"class_iri": f"{STAT}Plan"}),
            ),
            "assertion_proposals": (),
        }
    )
    second_native = _proposal().model_copy(
        update={
            "proposal_run_id": "run-2",
            "source_document_key": "EN50716-2",
            "assertion_proposals": (),
        }
    )

    report = AssertionQualificationEvaluator().evaluate(suite, (first_native, second_native))

    assert report.cases[0].entity_class_accuracy.accuracy.value == 0.0
    assert report.cases[1].entity_class_accuracy.accuracy.value == 1.0
    assert report.aggregate.entity_class_accuracy.correct == 2
    assert report.aggregate.entity_class_accuracy.evaluated == 3
    assert report.aggregate.entity_class_accuracy.accuracy.value == pytest.approx(2 / 3)


def test_report_validation_rejects_inconsistent_count_identity_and_interim_contract() -> None:
    from standards_atlas.application.assertion_qualification import AssertionQualificationReport

    report = AssertionQualificationEvaluator().evaluate(_suite(), (_proposal(),))
    payload = report.model_dump(mode="json")
    payload["aggregate"]["entities"]["false_positive"] = 1
    with pytest.raises(ValueError, match="false_positive"):
        AssertionQualificationReport.model_validate(payload)

    payload = report.model_dump(mode="json")
    payload["evaluation_contract"] = "assertion-clause-local-interim-v1"
    with pytest.raises(ValueError, match="evaluation_contract"):
        AssertionQualificationReport.model_validate(payload)


def _finding_codes(report) -> set[AssertionDiagnosticCode]:
    return {code for finding in report.cases[0].diagnostic_findings for code in finding.codes}


def test_diagnostics_name_unique_class_predicate_and_force_differences() -> None:
    native = _proposal()
    wrong_plan = native.entity_proposals[0].model_copy(update={"class_iri": f"{STAT}Plan"})
    wrong_assertion = native.assertion_proposals[0].model_copy(
        update={
            "predicate": f"{STAT}requires",
            "normative_force": NormativeForce.RECOMMENDATION,
        }
    )
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (
            native.model_copy(
                update={
                    "entity_proposals": (wrong_plan, native.entity_proposals[1]),
                    "assertion_proposals": (wrong_assertion,),
                }
            ),
        ),
    )

    codes = _finding_codes(report)
    assert AssertionDiagnosticCode.WRONG_ENTITY_CLASS in codes
    assert AssertionDiagnosticCode.WRONG_PREDICATE in codes
    # Force is compared only after the strict relation (including predicate) matches.
    assert AssertionDiagnosticCode.WRONG_NORMATIVE_FORCE not in codes
    assert all(
        finding.status is not AssertionDiagnosticStatus.HUMAN_CONFIRMED
        for finding in report.cases[0].diagnostic_findings
    )


def test_wrong_force_is_rule_based_only_after_strict_relation_alignment() -> None:
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (_proposal(force=NormativeForce.RECOMMENDATION),),
    )

    findings = [
        item
        for item in report.cases[0].diagnostic_findings
        if AssertionDiagnosticCode.WRONG_NORMATIVE_FORCE in item.codes
    ]
    assert len(findings) == 1
    assert findings[0].origin is AssertionDiagnosticOrigin.STRICT_COMPARISON
    assert findings[0].status is AssertionDiagnosticStatus.RULE_BASED


def test_extra_or_ambiguous_candidate_is_not_automatically_invented_or_over_atomized() -> None:
    native = _proposal()
    duplicate = native.assertion_proposals[0].model_copy(update={"id": "proposal-assertion-extra"})
    report = AssertionQualificationEvaluator().evaluate(
        _suite(),
        (
            native.model_copy(
                update={"assertion_proposals": (*native.assertion_proposals, duplicate)}
            ),
        ),
    )

    codes = _finding_codes(report)
    assert AssertionDiagnosticCode.UNCLASSIFIED_SEMANTIC_MISMATCH in codes
    assert AssertionDiagnosticCode.INVENTED_ASSERTION not in codes
    assert AssertionDiagnosticCode.LIST_OVER_ATOMIZATION not in codes


def test_retained_violation_can_suggest_multiple_codes_but_never_human_confirmation() -> None:
    native = _proposal().model_copy(
        update={
            "violations": (
                KnowledgeProposalViolation(
                    clause_id=CLAUSE,
                    kind=KnowledgeProposalViolationKind.INVALID_ASSERTION,
                    term="candidate-list",
                    reason="possible list over-atomization with conditional semantics loss",
                ),
            )
        }
    )
    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))
    suggestions = [
        item
        for item in report.cases[0].diagnostic_findings
        if item.origin is AssertionDiagnosticOrigin.PROPOSAL_DIAGNOSTIC
    ]

    assert len(suggestions) == 1
    assert set(suggestions[0].codes) == {
        AssertionDiagnosticCode.LIST_OVER_ATOMIZATION,
        AssertionDiagnosticCode.CONDITIONAL_SEMANTICS_LOSS,
    }
    assert suggestions[0].status is AssertionDiagnosticStatus.NEEDS_REVIEW
    assert suggestions[0].violation_reference == "violation[0]"


def test_heading_evidence_is_not_itself_a_wrong_context_diagnosis() -> None:
    native = _proposal()
    heading_anchor = native.evidence_anchors[0].model_copy(
        update={"source_kind": EvidenceSourceKind.HEADING}
    )
    native = native.model_copy(update={"evidence_anchors": (heading_anchor,)})

    report = AssertionQualificationEvaluator().evaluate(_suite(), (native,))

    assert AssertionDiagnosticCode.WRONG_CONTEXT_USE not in _finding_codes(report)


def test_human_confirmation_status_cannot_be_fabricated_without_annotation() -> None:
    with pytest.raises(ValueError, match="human-confirmed diagnostics"):
        AssertionQualificationFinding(
            source_document_key="EN50716",
            clause_id=CLAUSE,
            codes=(AssertionDiagnosticCode.WRONG_ENTITY_CLASS,),
            golden_ids=("g-plan",),
            observed_difference="class differs",
            rule="manual",
            origin=AssertionDiagnosticOrigin.STRICT_COMPARISON,
            status=AssertionDiagnosticStatus.HUMAN_CONFIRMED,
        )


def test_diagnostic_vocabulary_contains_the_ap01_codes_and_open_state() -> None:
    assert {item.value for item in AssertionDiagnosticCode} == {
        "missing_work_product",
        "wrong_entity_class",
        "over_extracted_detail",
        "note_over_extraction",
        "list_over_atomization",
        "missing_assertion",
        "invented_assertion",
        "wrong_predicate",
        "wrong_normative_force",
        "wrong_context_use",
        "grounding_failure",
        "conditional_semantics_loss",
        "unclassified_semantic_mismatch",
    }


def _native_source_package_with_parent_heading():
    from standards_atlas.application.context import (
        build_context_source_package,
        build_structured_context_candidates,
        context_source_package_binding,
        select_structured_context,
    )
    from standards_atlas.domain.model import (
        Clause,
        ClauseType,
        DocumentKey,
        DocumentType,
        EngineeringDocument,
        GeneratedAttribute,
        GenerationMethod,
        StandardReference,
        TextBlock,
    )

    parent = Clause(
        id=ClauseId(value="parent"),
        reference=StandardReference(standard="EN50716", clause="0"),
        clause_type=ClauseType.CLAUSE,
        heading="Verification context",
    ).mark_generated(
        GeneratedAttribute(
            path="baseline.heading",
            generator="test-source-extraction",
            method=GenerationMethod.SOURCE_EXTRACTION,
        )
    )
    target = Clause(
        id=CLAUSE,
        reference=StandardReference(standard="EN50716", clause="1"),
        clause_type=ClauseType.REQUIREMENT,
        parent_id=parent.id,
        content=(TextBlock(id="body", text=TEXT),),
    ).mark_generated(
        GeneratedAttribute(
            path="baseline.content",
            generator="test-source-extraction",
            method=GenerationMethod.SOURCE_EXTRACTION,
        )
    )
    document = EngineeringDocument(
        key=DocumentKey(value="EN50716"),
        title="Synthetic evaluation source",
        document_type=DocumentType.STANDARD,
        clauses=(parent, target),
    )
    inventory = build_structured_context_candidates(document, target)
    selection = select_structured_context(inventory)
    package = build_context_source_package(document, inventory, selection)
    return package, context_source_package_binding(package)


def test_native_package_resolves_foreign_heading_without_relaxing_golden_span_match() -> None:
    package, binding = _native_source_package_with_parent_heading()
    heading = "Verification context"
    anchor = EvidenceAnchor(
        id="parent-heading",
        source_clause_id=ClauseId(value="parent"),
        source_kind=EvidenceSourceKind.HEADING,
        start_offset=0,
        end_offset=len(heading),
        content_hash=hashlib.sha256(heading.encode()).hexdigest(),
    )
    proposal = _proposal().model_copy(
        update={
            "evidence_anchors": (anchor,),
            "entity_proposals": tuple(
                item.model_copy(update={"source_anchor_ids": (anchor.id,)})
                for item in _proposal().entity_proposals
            ),
            "assertion_proposals": (
                _proposal()
                .assertion_proposals[0]
                .model_copy(update={"evidence_anchor_ids": (anchor.id,)}),
            ),
            "context_source_bindings": (binding,),
        }
    )

    report = AssertionQualificationEvaluator().evaluate(
        _suite(), (proposal,), source_packages=(package,)
    )

    assert report.source_binding == "native_package_verified"
    assert report.cases[0].evidence_integrity.valid == 3
    assert report.cases[0].evidence_span_exact_match.accuracy.value == 0.0
    assert report.cases[0].source_comparison.status.value == "matching"
    assert report.cases[0].source_comparison.additional_candidate_surfaces >= 1


def test_native_package_missing_from_private_store_is_visible_and_not_a_frozen_fallback() -> None:
    package, binding = _native_source_package_with_parent_heading()
    proposal = _proposal().model_copy(update={"context_source_bindings": (binding,)})

    report = AssertionQualificationEvaluator().evaluate(_suite(), (proposal,), source_packages=())

    assert report.source_binding == "native_package_partial"
    assert report.cases[0].source_comparison.status.value == "partial"
    assert report.cases[0].evidence_integrity.unavailable == 3
