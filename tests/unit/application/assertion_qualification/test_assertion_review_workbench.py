import hashlib
from pathlib import Path

import pytest

from standards_atlas.application.assertion_qualification.assertion_review import (
    AssertionHumanDecisionInput,
    AssertionReviewSurface,
    AssertionReviewWorkbenchCase,
    EvidenceSelectionInput,
    ReviewAssertionInput,
    ReviewEntityInput,
    ReviewOntologyOption,
    active_assertion_decisions,
    initial_assertion_review_state,
    package_from_cases,
    publish_confirmed_assertion_suite,
    record_assertion_human_decision,
    write_assertion_review_package,
)
from standards_atlas.application.assertion_qualification.models import AssertionGoldenPartition
from standards_atlas.application.review_workbench.service import ReviewWorkbenchService
from standards_atlas.domain.model import EvidenceSourceKind

CLASS = "https://example.test/WorkProduct"
PRED = "https://example.test/requires"


def surface(text="The report shall be recorded."):
    return AssertionReviewSurface(
        source_ref="target-body",
        source_clause_id="c1",
        source_kind=EvidenceSourceKind.BODY,
        label="Target clause body",
        text=text,
        start_offset=0,
        content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
    )


def package(partition=AssertionGoldenPartition.DEVELOPMENT):
    case = AssertionReviewWorkbenchCase(
        case_id="DOC:c1",
        document_key="DOC",
        clause_id="c1",
        reference="DOC:1",
        partition=partition,
        source_group="g1",
        source_package_sha256="sha256:" + "1" * 64,
        surfaces=(surface(),),
    )
    return package_from_cases(
        id="review",
        version="1",
        corpus_plan_sha256="2" * 64,
        ontology_versions=("core@2.0.0",),
        class_options=(ReviewOntologyOption(iri=CLASS, label="WorkProduct"),),
        predicate_options=(ReviewOntologyOption(iri=PRED, label="requires"),),
        cases=(case,),
    )


def corrected():
    return AssertionHumanDecisionInput(
        status="corrected",
        entities=(
            ReviewEntityInput(
                id="report",
                class_iri=CLASS,
                normalized_label="report",
                evidence=(EvidenceSelectionInput(source_ref="target-body", quote="report"),),
            ),
        ),
        assertions=(
            ReviewAssertionInput(
                id="req",
                subject_id="report",
                predicate=PRED,
                object={"kind": "literal", "value": "recorded"},
                normative_force="requirement",
                evidence=(
                    EvidenceSelectionInput(source_ref="target-body", quote="shall be recorded"),
                ),
            ),
        ),
        comment="human correction",
    )


def test_server_computes_offsets_and_only_human_decision_is_publishable():
    pkg = package()
    state = initial_assertion_review_state(pkg)
    updated = record_assertion_human_decision(
        pkg,
        state,
        case_id="DOC:c1",
        reviewer="alice",
        decision=corrected(),
    )
    decision = active_assertion_decisions(updated)["DOC:c1"]
    assert decision.expected is not None
    assert decision.expected.assertions[0].evidence[0].start_offset == len("The report ")
    suite = publish_confirmed_assertion_suite(
        pkg,
        updated,
        partition=AssertionGoldenPartition.DEVELOPMENT,
        suite_id="dev",
        suite_version="1",
    )
    assert suite.cases[0].entities[0].id == "report"
    assert suite.audit.review_id == "review"


def test_explicit_empty_is_distinct_from_pending():
    pkg = package()
    state = initial_assertion_review_state(pkg)
    with pytest.raises(ValueError, match="explicitly confirmed empty"):
        AssertionHumanDecisionInput(status="corrected")
    updated = record_assertion_human_decision(
        pkg,
        state,
        case_id="DOC:c1",
        reviewer="alice",
        decision=AssertionHumanDecisionInput(
            status="corrected",
            explicit_empty=True,
            comment="intentionally empty",
        ),
    )
    assert active_assertion_decisions(updated)["DOC:c1"].expected.entities == ()


def test_workbench_requires_server_bound_human_view_and_revision(tmp_path: Path):
    pkg = package()
    root = tmp_path / "casepack"
    write_assertion_review_package(root, pkg)
    service = ReviewWorkbenchService(tmp_path)
    view = service.get_case("casepack", "DOC:c1", reviewer="alice")["view"]
    with pytest.raises(ValueError, match="server-bound human"):
        service.decide(
            "casepack",
            view={**view, "human_origin": "forged"},
            decisions=(corrected(),),
        )
    result = service.decide("casepack", view=view, decisions=(corrected(),))
    assert result["decisions_saved"] == 1
    with pytest.raises(ValueError, match="stale review revision"):
        service.decide("casepack", view=view, decisions=(corrected(),))


def test_holdout_cannot_expose_or_confirm_model_proposal_by_default():
    pkg = package(AssertionGoldenPartition.HOLDOUT)
    state = initial_assertion_review_state(pkg)
    with pytest.raises(ValueError, match="confirmation must bind"):
        AssertionHumanDecisionInput(status="confirmed")
    with pytest.raises(ValueError, match="no genuinely human-confirmed"):
        publish_confirmed_assertion_suite(
            pkg,
            state,
            partition=AssertionGoldenPartition.HOLDOUT,
            suite_id="h",
            suite_version="1",
        )


def test_review_ontology_options_use_productive_extraction_vocabulary():
    from standards_atlas.application.assertion_qualification.assertion_review import (
        review_ontology_options,
    )

    classes, predicates = review_ontology_options(
        ("standards-atlas-core@2.0.0", "functional-safety@2.1.0")
    )
    by_class = {item.label: item.iri for item in classes}
    by_predicate = {item.label: item.iri for item in predicates}
    assert by_class["WorkProduct"] == "http://lunetix.org/standards-atlas#WorkProduct"
    assert by_class["AssessmentActivity"] == (
        "http://lunetix.org/standards-atlas#AssessmentActivity"
    )
    assert by_predicate["requires"] == "http://lunetix.org/standards-atlas#requires"
    assert by_predicate["assesses"] == "http://lunetix.org/standards-atlas#assesses"
