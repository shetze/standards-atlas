from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionDiagnosticCode,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    AssertionQualificationEvaluator,
    ExperimentBudget,
    ExperimentCaseBinding,
    RepetitionEvidence,
    SeriesGFreeze,
    SeriesGGateProfile,
    SeriesHCompletionState,
    SeriesHExperimentRole,
    SeriesHGateOperator,
    SeriesHGateProfile,
    SeriesHHoldoutCampaign,
    SeriesHMetric,
    SeriesHMetricGate,
    SeriesHReleaseAttestation,
    SeriesHReleaseDecision,
    VerifierQualityMetrics,
    assess_series_g_readiness,
    assess_series_h_holdout,
    build_series_h_campaign,
    finalize_series_h,
    golden_suite_sha256,
    series_h_campaign_sha256,
    validate_series_h_campaign,
)
from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentManifest,
    AssertionExperimentReport,
    ExperimentCoverage,
    ExperimentEffort,
    manifest_sha256,
)
from standards_atlas.application.assertion_qualification.reference_corpus import (
    ExposureRegisterEntry,
    PlannedReferenceCase,
    ReferenceCorpusPlan,
    _canonical_sha256,
)
from standards_atlas.application.context.input_binding import context_source_package_binding
from standards_atlas.application.knowledge_proposal_extraction import (
    assertion_context_source_package,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentKnowledgeProposal,
    DocumentType,
    EngineeringDocument,
    KnowledgeProposalProvenance,
    StandardReference,
    TextBlock,
)

TEXT = "No engineering assertion is expected for this synthetic Holdout clause."


def _suite() -> AssertionGoldenSuite:
    return AssertionGoldenSuite(
        id="holdout-suite",
        version="1.0.0",
        partition=AssertionGoldenPartition.HOLDOUT,
        audit=AssertionAuditBinding(
            review_id="holdout-review",
            review_version="1",
            audit_sha256="a" * 64,
        ),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(
            AssertionGoldenCase(
                source_document_key="TEST",
                clause_id=ClauseId(value="c1"),
                reference="TEST:1",
                canonical_reference="TEST 1",
                text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
                source_sha256="b" * 64,
                entities=(),
                assertions=(),
            ),
        ),
    )


def _document_and_package():
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="t1", text=TEXT),),
    )
    document = EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Synthetic",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )
    package = assertion_context_source_package(document, clause)
    return document, package, context_source_package_binding(package)


def _plan() -> ReferenceCorpusPlan:
    holdout = PlannedReferenceCase(
        document_key="TEST",
        clause_id="c1",
        reference="1",
        partition="holdout",
        source_group="group-h",
        bearing_source_groups=("group-h",),
        traits=("empty",),
    )
    exposure = ExposureRegisterEntry(
        document_key="TEST",
        clause_id="c1",
        source_group="group-h",
        exposures=(),
        holdout_independence_eligible=True,
    )
    body = {
        "contract_id": "assertion-reference-corpus-plan-v1",
        "plan_id": "p",
        "plan_version": "1",
        "seed": 7,
        "selection_method": "bearing-source-group-diversity-v1",
        "candidate_sha256": "c" * 64,
        "development": [],
        "holdout": [holdout.model_dump(mode="json")],
        "exposure_register": [exposure.model_dump(mode="json")],
        "excluded": {},
        "blockers": [],
    }
    return ReferenceCorpusPlan(**body, plan_sha256=_canonical_sha256(body))


def _manifest(suite: AssertionGoldenSuite, binding) -> AssertionExperimentManifest:
    return AssertionExperimentManifest(
        experiment_id="holdout-finalist",
        code_revision="snapshot:series-h",
        variant_id="P1",
        partition="holdout",
        golden_suite_id=suite.id,
        golden_suite_version=suite.version,
        golden_suite_sha256=golden_suite_sha256(suite),
        ontology_versions=suite.ontology_versions,
        prompt_version="engineering-policy-v1",
        model_route="fake",
        requested_model="fake",
        repetitions=1,
        execution_authorized=True,
        authorization_reference="H3-test",
        conservative_call_upper_bound=1,
        cases=(
            ExperimentCaseBinding(
                document_key="TEST",
                clause_id="c1",
                source_package_binding=binding,
                rendered_request_sha256="d" * 64,
            ),
        ),
        budget=ExperimentBudget(max_calls=1),
    )


def _gates() -> SeriesHGateProfile:
    return SeriesHGateProfile(
        profile_id="bounded-pilot",
        profile_version="1",
        min_holdout_cases=1,
        min_independent_source_groups=1,
        max_failed_cells=0,
        max_not_executed_cells=0,
        max_cached_calls=0,
        metric_gates=(
            SeriesHMetricGate(
                metric=SeriesHMetric.TECHNICAL_COMPLETION,
                operator=SeriesHGateOperator.GREATER_OR_EQUAL,
                threshold=1.0,
                min_support=1,
            ),
            SeriesHMetricGate(
                metric=SeriesHMetric.CLAUSE_EXACT_MATCH,
                operator=SeriesHGateOperator.GREATER_OR_EQUAL,
                threshold=1.0,
                min_support=1,
            ),
        ),
        critical_diagnostic_codes=(AssertionDiagnosticCode.WRONG_NORMATIVE_FORCE,),
        max_critical_findings_per_repetition=0,
    )


def _readiness(campaign_hash: str, plan_hash: str, code_revision: str):
    metrics = VerifierQualityMetrics(
        annotated_cases=1,
        real_annotated_cases=1,
        synthetic_cases=0,
        candidate_support=1,
        candidate_reviewed=1,
        false_acceptances=0,
        false_rejections=0,
        abstentions=0,
        missing_item_positive_support=1,
        missing_item_true_positives=1,
        missing_item_false_negatives=0,
        missing_item_false_positives=0,
        coverage=1.0,
        false_acceptance_rate=0.0,
        false_rejection_rate=0.0,
        missing_item_recall=1.0,
    )
    profile = SeriesGGateProfile(
        max_false_acceptance_rate=0.0,
        max_false_rejection_rate=0.0,
        min_missing_item_recall=1.0,
        min_verifier_coverage=1.0,
        min_real_annotated_cases=1,
        min_candidate_support=1,
        required_fresh_repetitions=1,
        human_confirmed=True,
        human_confirmation_reference="H3-test",
    )
    repetitions = RepetitionEvidence(
        variant_id="P1",
        planned_repetitions=1,
        completed_repetitions=1,
        fresh_inference_repetitions=1,
        report_hashes=("e" * 64,),
    )
    freeze = SeriesGFreeze(
        freeze_id="freeze-h",
        code_revision=code_revision,
        prompt_bundle_sha256="1" * 64,
        task_schema_sha256="2" * 64,
        ontology_fingerprint="3" * 64,
        source_context_policy_sha256="4" * 64,
        model_backend_sha256="5" * 64,
        cascade_policy_sha256="6" * 64,
        retry_budget_policy_sha256="7" * 64,
        development_golden_sha256="8" * 64,
        partition_exposure_sha256=plan_hash,
        evaluator_sha256="9" * 64,
        holdout_campaign_sha256=campaign_hash,
    )
    return assess_series_g_readiness(
        metrics=metrics,
        repetitions=repetitions,
        gate_profile=profile,
        freeze=freeze,
    )


def _qualification_report(suite, package, binding):
    proposal = DocumentKnowledgeProposal(
        proposal_run_id="holdout-run",
        source_document_key="TEST",
        ontology_versions=suite.ontology_versions,
        context_source_bindings=(binding,),
        entity_proposals=(),
        assertion_proposals=(),
        evidence_anchors=(),
        proposal_provenance=KnowledgeProposalProvenance(
            extractor="synthetic",
            extractor_version="1",
        ),
    )
    return AssertionQualificationEvaluator().evaluate(
        suite,
        (proposal,),
        source_packages=(package,),
    )


def test_series_h_preflight_binds_freeze_campaign_exposure_and_manifest() -> None:
    suite = _suite()
    _, _, binding = _document_and_package()
    manifest = _manifest(suite, binding)
    plan = _plan()
    campaign = build_series_h_campaign(
        campaign_id="h1",
        campaign_version="1",
        suite=suite,
        reference_plan=plan,
        gate_profile=_gates(),
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    readiness = _readiness(
        series_h_campaign_sha256(campaign),
        plan.plan_sha256,
        manifest.code_revision,
    )

    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=_gates(),
        suite=suite,
        reference_plan=plan,
        manifests=(manifest,),
    )

    assert preflight.ready_to_execute is True
    assert preflight.exposure_clear is True
    assert preflight.manifest_bindings_valid is True
    assert preflight.model_calls == 0


def test_series_h_preflight_rejects_campaign_changed_after_freeze() -> None:
    suite = _suite()
    _, _, binding = _document_and_package()
    manifest = _manifest(suite, binding)
    plan = _plan()
    campaign = build_series_h_campaign(
        campaign_id="h1",
        campaign_version="1",
        suite=suite,
        reference_plan=plan,
        gate_profile=_gates(),
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    readiness = _readiness("f" * 64, plan.plan_sha256, manifest.code_revision)

    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=_gates(),
        suite=suite,
        reference_plan=plan,
        manifests=(manifest,),
    )

    assert preflight.ready_to_execute is False
    assert "holdout_campaign_differs_from_freeze" in preflight.blockers


def test_series_h_passed_holdout_still_needs_explicit_human_release() -> None:
    suite = _suite()
    _, package, binding = _document_and_package()
    manifest = _manifest(suite, binding)
    plan = _plan()
    gates = _gates()
    campaign = build_series_h_campaign(
        campaign_id="h1",
        campaign_version="1",
        suite=suite,
        reference_plan=plan,
        gate_profile=gates,
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    readiness = _readiness(
        series_h_campaign_sha256(campaign),
        plan.plan_sha256,
        manifest.code_revision,
    )
    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=gates,
        suite=suite,
        reference_plan=plan,
        manifests=(manifest,),
    )
    qualification = _qualification_report(suite, package, binding)
    report = AssertionExperimentReport(
        experiment_id=manifest.experiment_id,
        manifest_sha256=manifest_sha256(manifest),
        variant_id=manifest.variant_id,
        coverage=ExperimentCoverage(
            selected_cases=1,
            planned_cells=1,
            attempted_cells=1,
            technically_completed_cells=1,
            failed_cells=0,
            not_executed_cells=0,
        ),
        stage_failures={},
        effort=ExperimentEffort(
            calls=1,
            cached_calls=0,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            duration_ms=1,
        ),
        qualification_report=qualification,
        evaluation_repetition=1,
    )

    assessment = assess_series_h_holdout(
        preflight=preflight,
        campaign=campaign,
        gate_profile=gates,
        reports=(report,),
    )
    open_completion = finalize_series_h(assessment=assessment)
    approved = finalize_series_h(
        assessment=assessment,
        release_attestation=SeriesHReleaseAttestation(
            decision=SeriesHReleaseDecision.APPROVE_BOUNDED_PILOT,
            reference="H3-release-test",
        ),
        qualification_scope="Synthetic single-clause pilot only",
    )

    assert assessment.status.value == "passed"
    assert open_completion.state is SeriesHCompletionState.EVALUATED_NOT_QUALIFIED
    assert "human_release_decision_missing" in open_completion.blockers
    assert approved.state is SeriesHCompletionState.QUALIFIED_FOR_BOUNDED_PILOT
    assert approved.canonical_adoption_enabled is False


def test_series_h_negative_holdout_is_nonrelease_not_retuning() -> None:
    suite = _suite()
    _, package, binding = _document_and_package()
    manifest = _manifest(suite, binding)
    plan = _plan()
    gates = _gates().model_copy(
        update={
            "metric_gates": (
                SeriesHMetricGate(
                    metric=SeriesHMetric.CLAUSE_EXACT_MATCH,
                    operator=SeriesHGateOperator.LESS_OR_EQUAL,
                    threshold=0.0,
                    min_support=1,
                ),
            )
        }
    )
    campaign = build_series_h_campaign(
        campaign_id="h1",
        campaign_version="1",
        suite=suite,
        reference_plan=plan,
        gate_profile=gates,
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    readiness = _readiness(
        series_h_campaign_sha256(campaign),
        plan.plan_sha256,
        manifest.code_revision,
    )
    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=gates,
        suite=suite,
        reference_plan=plan,
        manifests=(manifest,),
    )
    qualification = _qualification_report(suite, package, binding)
    report = AssertionExperimentReport(
        experiment_id=manifest.experiment_id,
        manifest_sha256=manifest_sha256(manifest),
        variant_id=manifest.variant_id,
        coverage=ExperimentCoverage(
            selected_cases=1,
            planned_cells=1,
            attempted_cells=1,
            technically_completed_cells=1,
            failed_cells=0,
            not_executed_cells=0,
        ),
        stage_failures={},
        effort=ExperimentEffort(
            calls=1,
            cached_calls=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            duration_ms=None,
        ),
        qualification_report=qualification,
    )

    assessment = assess_series_h_holdout(
        preflight=preflight,
        campaign=campaign,
        gate_profile=gates,
        reports=(report,),
    )
    completion = finalize_series_h(assessment=assessment)

    assert assessment.status.value == "failed"
    assert completion.state is SeriesHCompletionState.EVALUATED_NOT_QUALIFIED
    assert "holdout_gate_failed" in completion.blockers


def test_series_h_campaign_contract_forbids_post_freeze_optimizer_paths() -> None:
    suite = _suite()
    _, _, binding = _document_and_package()
    manifest = _manifest(suite, binding)
    plan = _plan()
    campaign = build_series_h_campaign(
        campaign_id="h-security",
        campaign_version="1",
        suite=suite,
        reference_plan=plan,
        gate_profile=_gates(),
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    payload = campaign.model_dump(mode="json")

    for field in (
        "optimizer_access_permitted",
        "expected_semantics_visible_to_extractor",
        "adaptive_variant_selection_permitted",
        "gate_changes_after_result_permitted",
        "canonical_adoption_permitted",
    ):
        mutated = dict(payload)
        mutated[field] = True
        with pytest.raises(ValidationError):
            SeriesHHoldoutCampaign.model_validate(mutated)
