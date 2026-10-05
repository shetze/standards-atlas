from __future__ import annotations

import hashlib
from pathlib import Path

from standards_atlas.adapters.filesystem import (
    FileSystemAssertionExperimentRepository,
    FileSystemContextSourcePackageRepository,
)
from standards_atlas.adapters.llm import OntologyGuidedKnowledgeProposalExtractor
from standards_atlas.application.assertion_qualification import (
    AssertionAuditBinding,
    AssertionExperimentService,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    ExperimentBudget,
    RepetitionEvidence,
    SeriesGFreeze,
    SeriesGGateProfile,
    SeriesHCompletionState,
    SeriesHExperimentRole,
    SeriesHGateOperator,
    SeriesHGateProfile,
    SeriesHMetric,
    SeriesHMetricGate,
    SeriesHReleaseAttestation,
    SeriesHReleaseDecision,
    VerifierQualityMetrics,
    assess_series_g_readiness,
    assess_series_h_holdout,
    build_series_h_campaign,
    evaluate_assertion_experiment,
    finalize_series_h,
    materialize_experiment_inputs,
    plan_assertion_experiment,
    render_series_h_quality_report,
    series_h_campaign_sha256,
    validate_series_h_campaign,
)
from standards_atlas.application.assertion_qualification.models import AssertionDiagnosticCode
from standards_atlas.application.assertion_qualification.reference_corpus import (
    ExposureRegisterEntry,
    PlannedReferenceCase,
    ReferenceCorpusPlan,
    _canonical_sha256,
)
from standards_atlas.application.ports.llm_gateway import LlmHealth, StructuredGenerationResult
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)

TEXT = "Synthetic Holdout clause with intentionally empty semantic output."


class _Gateway:
    provider = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> LlmHealth:
        return LlmHealth(available=True, models=("fake",))

    def generate_structured(self, request):
        self.calls += 1
        return StructuredGenerationResult(
            value={"entities": [], "assertions": []},
            model="fake",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash=f"{self.calls:064x}",
            raw_response_hash=f"{self.calls + 10:064x}",
            duration_ms=1,
            cached=False,
            raw_response={"synthetic": True},
        )


def _document() -> EngineeringDocument:
    clause = Clause(
        id=ClauseId(value="c1"),
        reference=StandardReference(standard="TEST", clause="1"),
        clause_type=ClauseType.CLAUSE,
        content=(TextBlock(id="t1", text=TEXT),),
    )
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Synthetic Holdout",
        document_type=DocumentType.STANDARD,
        clauses=(clause,),
    )


def _suite() -> AssertionGoldenSuite:
    return AssertionGoldenSuite(
        id="holdout",
        version="1",
        partition=AssertionGoldenPartition.HOLDOUT,
        audit=AssertionAuditBinding(review_id="holdout", review_version="1", audit_sha256="a" * 64),
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


def _reference_plan() -> ReferenceCorpusPlan:
    selected = PlannedReferenceCase(
        document_key="TEST",
        clause_id="c1",
        reference="1",
        partition="holdout",
        source_group="holdout-group",
        bearing_source_groups=("holdout-group",),
        traits=("empty",),
    )
    exposure = ExposureRegisterEntry(
        document_key="TEST",
        clause_id="c1",
        source_group="holdout-group",
        exposures=(),
        holdout_independence_eligible=True,
    )
    body = {
        "contract_id": "assertion-reference-corpus-plan-v1",
        "plan_id": "synthetic-h",
        "plan_version": "1",
        "seed": 1,
        "selection_method": "bearing-source-group-diversity-v1",
        "candidate_sha256": "c" * 64,
        "development": [],
        "holdout": [selected.model_dump(mode="json")],
        "exposure_register": [exposure.model_dump(mode="json")],
        "excluded": {},
        "blockers": [],
    }
    return ReferenceCorpusPlan(**body, plan_sha256=_canonical_sha256(body))


def _series_g_ready(campaign_hash: str, plan_hash: str, code_revision: str):
    metrics = VerifierQualityMetrics(
        annotated_cases=1,
        real_annotated_cases=1,
        synthetic_cases=0,
        candidate_support=2,
        candidate_reviewed=2,
        supported_candidate_support=1,
        rejected_candidate_support=1,
        false_acceptances=0,
        false_rejections=0,
        abstentions=0,
        missing_item_annotated_positive_support=1,
        missing_item_positive_support=1,
        missing_item_true_positives=1,
        missing_item_false_negatives=0,
        missing_item_false_positives=0,
        coverage=1.0,
        false_acceptance_rate=0.0,
        false_rejection_rate=0.0,
        missing_item_recall=1.0,
    )
    gates = SeriesGGateProfile(
        max_false_acceptance_rate=0.0,
        max_false_rejection_rate=0.0,
        min_missing_item_recall=1.0,
        min_verifier_coverage=1.0,
        min_real_annotated_cases=1,
        min_candidate_support=1,
        min_supported_candidate_support=1,
        min_rejected_candidate_support=1,
        min_missing_item_positive_support=1,
        required_fresh_repetitions=1,
        human_confirmed=True,
        human_confirmation_reference="synthetic-H3",
    )
    repetition = RepetitionEvidence(
        variant_id="P1",
        planned_repetitions=1,
        completed_repetitions=1,
        fresh_inference_repetitions=1,
        report_hashes=("d" * 64,),
    )
    freeze = SeriesGFreeze(
        freeze_id="synthetic-freeze",
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
        repetitions=repetition,
        gate_profile=gates,
        freeze=freeze,
    )


def test_synthetic_series_h_runs_frozen_campaign_through_existing_runner_and_evaluator(
    tmp_path: Path,
) -> None:
    suite = _suite()
    document = _document()
    reference_plan = _reference_plan()
    workspace = tmp_path / ".atlas" / "data"
    source_repo = FileSystemContextSourcePackageRepository(workspace)
    manifest = plan_assertion_experiment(
        suite,
        {"TEST": document},
        experiment_id="holdout-finalist",
        code_revision="synthetic-code",
        variant_id="P1",
        prompt_version="engineering-policy-v1",
        model_route="fake",
        source_packages=source_repo,
        budget=ExperimentBudget(max_calls=1),
        requested_model="fake",
        execution_authorized=True,
        authorization_reference="synthetic-holdout-authorization",
    )
    repository = FileSystemAssertionExperimentRepository(tmp_path, workspace)
    repository.save_manifest(manifest)
    gates = SeriesHGateProfile(
        profile_id="synthetic-bounded-pilot",
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
    campaign = build_series_h_campaign(
        campaign_id="synthetic-h",
        campaign_version="1",
        suite=suite,
        reference_plan=reference_plan,
        gate_profile=gates,
        experiments=((SeriesHExperimentRole.FINALIST, manifest),),
    )
    readiness = _series_g_ready(
        series_h_campaign_sha256(campaign),
        reference_plan.plan_sha256,
        manifest.code_revision,
    )
    preflight = validate_series_h_campaign(
        readiness=readiness,
        campaign=campaign,
        gate_profile=gates,
        suite=suite,
        reference_plan=reference_plan,
        manifests=(manifest,),
    )
    assert preflight.ready_to_execute

    gateway = _Gateway()

    def extractor_factory(bound_gateway, bound_manifest):
        return OntologyGuidedKnowledgeProposalExtractor(
            bound_gateway,
            model=bound_manifest.requested_model,
            provider="fake",
            prompt_version=bound_manifest.prompt_version,
            task_schema_version=bound_manifest.task_schema_version,
        )

    state = AssertionExperimentService(
        repository=repository,
        source_packages=source_repo,
        gateway=gateway,
        extractor_factory=extractor_factory,
    ).run(manifest, suite, {"TEST": document})
    proposals, packages = materialize_experiment_inputs(
        repository,
        source_repo,
        manifest,
        state,
    )
    experiment_report = evaluate_assertion_experiment(
        manifest,
        state,
        suite,
        proposals=proposals,
        source_packages=packages,
    )
    assessment = assess_series_h_holdout(
        preflight=preflight,
        campaign=campaign,
        gate_profile=gates,
        reports=(experiment_report,),
    )
    completion = finalize_series_h(
        assessment=assessment,
        release_attestation=SeriesHReleaseAttestation(
            decision=SeriesHReleaseDecision.APPROVE_BOUNDED_PILOT,
            reference="synthetic-release",
        ),
        qualification_scope="Synthetic fixture only",
    )

    assert gateway.calls == 1
    assert experiment_report.qualification_report.evaluation_contract == "assertion-clause-local-v1"
    assert experiment_report.qualification_report.source_binding == "native_package_verified"
    assert completion.state is SeriesHCompletionState.QUALIFIED_FOR_BOUNDED_PILOT
    assert completion.canonical_adoption_enabled is False
    quality = render_series_h_quality_report(
        completion,
        campaign=campaign,
        experiment_reports=(experiment_report,),
        reference_plan=reference_plan,
    )
    assert "Holdout source groups and diagnostic patterns" in quality
    assert "source group `holdout-group`" in quality
    assert "1/1 exact cases" in quality
