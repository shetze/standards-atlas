from standards_atlas.application.assertion_qualification import (
    ExpectedCandidateDisposition,
    RepetitionEvidence,
    SeriesGFreeze,
    SeriesGGateProfile,
    VerifierCandidateTruth,
    VerifierCaseKind,
    VerifierCaseObservation,
    VerifierCaseTruth,
    assess_series_g_readiness,
    evaluate_verifier_quality,
)
from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionCandidateVerification,
    AssertionClauseVerification,
    AssertionVerificationDisposition,
)
from standards_atlas.domain.model import ClauseId


def _observation(*, kind=VerifierCaseKind.REAL_ANNOTATED):
    truth = VerifierCaseTruth(
        case_id="case-1",
        clause_id="c1",
        kind=kind,
        entity_candidates=(
            VerifierCandidateTruth(
                candidate_id="good",
                expected=ExpectedCandidateDisposition.SUPPORTED,
            ),
            VerifierCandidateTruth(
                candidate_id="bad",
                expected=ExpectedCandidateDisposition.REJECTED,
            ),
        ),
        missing_assertion_expected=True,
        annotation_reference="review:case-1",
    )
    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        entity_reviews=(
            AssertionCandidateVerification(
                candidate_id="good",
                disposition=AssertionVerificationDisposition.REJECTED,
            ),
            AssertionCandidateVerification(
                candidate_id="bad",
                disposition=AssertionVerificationDisposition.SUPPORTED,
            ),
        ),
        missing_assertion_detected=False,
        source_package_sha256="sha256:" + "a" * 64,
    )
    return VerifierCaseObservation(truth=truth, verification=verification)


def test_verifier_quality_counts_false_decisions_and_missing_detection() -> None:
    metrics = evaluate_verifier_quality((_observation(),))

    assert metrics.real_annotated_cases == 1
    assert metrics.candidate_support == 2
    assert metrics.candidate_reviewed == 2
    assert metrics.supported_candidate_support == 1
    assert metrics.rejected_candidate_support == 1
    assert metrics.false_acceptances == 1
    assert metrics.false_rejections == 1
    assert metrics.false_acceptance_rate == 1.0
    assert metrics.false_rejection_rate == 1.0
    assert metrics.missing_item_positive_support == 1
    assert metrics.missing_item_annotated_positive_support == 1
    assert metrics.missing_item_false_negatives == 1
    assert metrics.missing_item_recall == 0.0
    assert metrics.coverage == 1.0


def test_series_g_never_qualifies_from_synthetic_only_or_missing_human_freeze() -> None:
    metrics = evaluate_verifier_quality((_observation(kind=VerifierCaseKind.SYNTHETIC_MUTATION),))
    profile = SeriesGGateProfile(
        max_false_acceptance_rate=1.0,
        max_false_rejection_rate=1.0,
        min_missing_item_recall=0.0,
        min_verifier_coverage=1.0,
        min_real_annotated_cases=1,
        min_candidate_support=1,
        min_supported_candidate_support=1,
        min_rejected_candidate_support=1,
        min_missing_item_positive_support=1,
        required_fresh_repetitions=3,
    )
    repetitions = RepetitionEvidence(
        variant_id="P1",
        planned_repetitions=3,
        completed_repetitions=3,
        fresh_inference_repetitions=3,
        report_hashes=("1" * 64, "2" * 64, "3" * 64),
    )

    readiness = assess_series_g_readiness(
        metrics=metrics,
        repetitions=repetitions,
        gate_profile=profile,
        freeze=None,
    )

    assert readiness.ready_for_holdout is False
    assert readiness.qualification_claim_permitted is False
    assert "no_real_annotated_verifier_cases" in readiness.blockers
    assert "human_gate_confirmation_missing" in readiness.blockers
    assert "finalist_freeze_missing" in readiness.blockers


def test_series_g_readiness_requires_complete_bound_evidence() -> None:
    truth = _observation().truth
    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        entity_reviews=(
            AssertionCandidateVerification(
                candidate_id="good",
                disposition=AssertionVerificationDisposition.SUPPORTED,
            ),
            AssertionCandidateVerification(
                candidate_id="bad",
                disposition=AssertionVerificationDisposition.REJECTED,
            ),
        ),
        missing_assertion_detected=True,
        missing_rationale="expected omission detected",
        source_package_sha256="sha256:" + "a" * 64,
    )
    metrics = evaluate_verifier_quality(
        (VerifierCaseObservation(truth=truth, verification=verification),)
    )
    profile = SeriesGGateProfile(
        max_false_acceptance_rate=0.0,
        max_false_rejection_rate=0.0,
        min_missing_item_recall=1.0,
        min_verifier_coverage=1.0,
        min_real_annotated_cases=1,
        min_candidate_support=2,
        min_supported_candidate_support=1,
        min_rejected_candidate_support=1,
        min_missing_item_positive_support=1,
        required_fresh_repetitions=3,
        human_confirmed=True,
        human_confirmation_reference="H3-20261004",
    )
    repetitions = RepetitionEvidence(
        variant_id="P1",
        planned_repetitions=3,
        completed_repetitions=3,
        fresh_inference_repetitions=3,
        report_hashes=("1" * 64, "2" * 64, "3" * 64),
    )
    values = {
        name: char * 64
        for name, char in zip(
            (
                "prompt_bundle_sha256",
                "task_schema_sha256",
                "ontology_fingerprint",
                "source_context_policy_sha256",
                "model_backend_sha256",
                "cascade_policy_sha256",
                "retry_budget_policy_sha256",
                "development_golden_sha256",
                "partition_exposure_sha256",
                "evaluator_sha256",
                "holdout_campaign_sha256",
            ),
            "123456789ab",
            strict=True,
        )
    }
    freeze = SeriesGFreeze(freeze_id="freeze-g", code_revision="rev", **values)

    readiness = assess_series_g_readiness(
        metrics=metrics,
        repetitions=repetitions,
        gate_profile=profile,
        freeze=freeze,
    )

    assert readiness.ready_for_holdout is True
    assert readiness.qualification_claim_permitted is False
    assert readiness.blockers == ()


def test_series_g_readiness_requires_separate_reviewed_candidate_supports() -> None:
    truth = VerifierCaseTruth(
        case_id="case-positive-only",
        clause_id="c1",
        kind=VerifierCaseKind.REAL_ANNOTATED,
        entity_candidates=(
            VerifierCandidateTruth(
                candidate_id="good",
                expected=ExpectedCandidateDisposition.SUPPORTED,
            ),
        ),
        missing_entity_expected=True,
        annotation_reference="H2:positive-only",
    )
    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        entity_reviews=(
            AssertionCandidateVerification(
                candidate_id="good",
                disposition=AssertionVerificationDisposition.SUPPORTED,
            ),
        ),
        missing_entity_detected=True,
        missing_rationale="expected omission detected",
        source_package_sha256="sha256:" + "a" * 64,
    )
    metrics = evaluate_verifier_quality(
        (VerifierCaseObservation(truth=truth, verification=verification),)
    )
    profile = SeriesGGateProfile(
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
        human_confirmation_reference="H3-test",
    )
    repetitions = RepetitionEvidence(
        variant_id="P1",
        planned_repetitions=1,
        completed_repetitions=1,
        fresh_inference_repetitions=1,
        report_hashes=("1" * 64,),
    )

    readiness = assess_series_g_readiness(
        metrics=metrics,
        repetitions=repetitions,
        gate_profile=profile,
        freeze=None,
    )

    assert metrics.candidate_support == 1
    assert metrics.supported_candidate_support == 1
    assert metrics.rejected_candidate_support == 0
    assert readiness.verifier_evidence_sufficient is False
    assert "verifier_gate_not_met" in readiness.blockers


def test_series_g_review_csv_builds_observations_without_exposing_verifier_decision() -> None:
    import csv
    import io

    from standards_atlas.application.assertion_qualification import (
        SeriesGVerifierRun,
        VerifierRunCandidate,
        VerifierRunCandidateKind,
        VerifierRunCase,
        build_verifier_observations_from_review_csv,
        render_verifier_review_csv,
    )
    from standards_atlas.application.assertion_qualification.cascade_models import (
        AssertionVerifierProvenance,
    )

    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        entity_reviews=(
            AssertionCandidateVerification(
                candidate_id="e1",
                disposition=AssertionVerificationDisposition.SUPPORTED,
            ),
        ),
        missing_entity_detected=False,
        missing_assertion_detected=False,
        source_package_sha256="sha256:" + "a" * 64,
    )
    run = SeriesGVerifierRun(
        campaign_id="g-dev",
        experiment_id="f-finalist",
        experiment_manifest_sha256="1" * 64,
        variant_id="B0-AP02",
        verifier_provenance=AssertionVerifierProvenance(
            verifier="test-verifier",
            verifier_version="1",
        ),
        runtime_config_sha256="2" * 64,
        authorized_max_calls=1,
        actual_calls=1,
        authorization_reference="H1-series-g",
        cases=(
            VerifierRunCase(
                case_id="case-1",
                document_key="DOC",
                clause_id="c1",
                source_package_sha256="sha256:" + "a" * 64,
                candidates=(
                    VerifierRunCandidate(
                        candidate_id="e1",
                        kind=VerifierRunCandidateKind.ENTITY,
                        summary="WorkProduct | report",
                    ),
                ),
                verification=verification,
            ),
        ),
    )

    prepared = render_verifier_review_csv(run)
    assert "supported" not in prepared
    rows = list(csv.DictReader(io.StringIO(prepared)))
    rows[0]["missing_entity_expected"] = "false"
    rows[0]["missing_assertion_expected"] = "true"
    rows[0]["annotation_reference"] = "H2:case-1"
    rows[1]["expected"] = "supported"
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    observations = build_verifier_observations_from_review_csv(run, stream.getvalue())

    assert len(observations) == 1
    assert observations[0].truth.annotation_reference == "H2:case-1"
    assert observations[0].truth.missing_assertion_expected is True
    assert observations[0].verification == verification


def test_series_g_retry_run_counts_only_retried_calls_and_preserves_full_case_set() -> None:
    from standards_atlas.application.assertion_qualification import (
        SeriesGVerifierRun,
        VerifierRunCase,
    )
    from standards_atlas.application.assertion_qualification.cascade_models import (
        AssertionVerifierProvenance,
    )

    verification = AssertionClauseVerification(
        clause_id=ClauseId(value="c1"),
        source_package_sha256="sha256:" + "a" * 64,
    )
    valid = VerifierRunCase(
        case_id="case-valid",
        document_key="DOC",
        clause_id="c1",
        source_package_sha256="sha256:" + "a" * 64,
        verification=verification,
    )
    retried = VerifierRunCase(
        case_id="case-retry",
        document_key="DOC",
        clause_id="c2",
        source_package_sha256="sha256:" + "b" * 64,
        verification=AssertionClauseVerification(
            clause_id=ClauseId(value="c2"),
            source_package_sha256="sha256:" + "b" * 64,
        ),
    )

    run = SeriesGVerifierRun(
        campaign_id="g-retry",
        experiment_id="f-finalist",
        experiment_manifest_sha256="1" * 64,
        variant_id="B0-AP02",
        verifier_provenance=AssertionVerifierProvenance(
            verifier="test-verifier",
            verifier_version="2.1.0",
        ),
        runtime_config_sha256="2" * 64,
        authorized_max_calls=1,
        actual_calls=1,
        authorization_reference="H1-retry",
        retry_of_verifier_run_sha256="3" * 64,
        retried_case_ids=("case-retry",),
        inherited_case_count=1,
        cases=(valid, retried),
    )

    assert run.actual_calls == 1
    assert len(run.cases) == 2
    assert run.inherited_case_count == 1


def test_verifier_error_case_reduces_coverage_instead_of_disappearing() -> None:
    truth = VerifierCaseTruth(
        case_id="case-error",
        clause_id="c1",
        kind=VerifierCaseKind.REAL_ANNOTATED,
        entity_candidates=(
            VerifierCandidateTruth(
                candidate_id="e1",
                expected=ExpectedCandidateDisposition.SUPPORTED,
            ),
        ),
        missing_entity_expected=True,
        annotation_reference="H2:case-error",
    )
    observation = VerifierCaseObservation(
        truth=truth,
        verification_error_type="LlmTimeoutError",
        verification_error_message="timeout",
    )

    metrics = evaluate_verifier_quality((observation,))

    assert metrics.verifier_error_cases == 1
    assert metrics.candidate_support == 1
    assert metrics.candidate_reviewed == 0
    assert metrics.supported_candidate_support == 0
    assert metrics.rejected_candidate_support == 0
    assert metrics.coverage == 0.0
    assert metrics.case_coverage == 0.0
    assert metrics.candidate_coverage == 0.0
    assert metrics.missing_item_coverage == 0.0
    assert metrics.missing_item_annotated_positive_support == 1
    assert metrics.missing_item_positive_support == 0
    assert metrics.missing_item_false_negatives == 0
    assert metrics.missing_item_recall is None


def test_verifier_error_does_not_enter_semantic_rate_denominators() -> None:
    valid = _observation()
    error_truth = VerifierCaseTruth(
        case_id="case-error",
        clause_id="c2",
        kind=VerifierCaseKind.REAL_ANNOTATED,
        entity_candidates=(
            VerifierCandidateTruth(
                candidate_id="unreviewed-supported",
                expected=ExpectedCandidateDisposition.SUPPORTED,
            ),
            VerifierCandidateTruth(
                candidate_id="unreviewed-rejected",
                expected=ExpectedCandidateDisposition.REJECTED,
            ),
        ),
        missing_entity_expected=True,
        missing_assertion_expected=True,
        annotation_reference="H2:case-error",
    )
    error = VerifierCaseObservation(
        truth=error_truth,
        verification_error_type="LlmTimeoutError",
        verification_error_message="timeout",
    )

    metrics = evaluate_verifier_quality((valid, error))

    assert metrics.candidate_support == 4
    assert metrics.candidate_reviewed == 2
    assert metrics.supported_candidate_support == 1
    assert metrics.rejected_candidate_support == 1
    assert metrics.false_acceptance_rate == 1.0
    assert metrics.false_rejection_rate == 1.0
    assert metrics.missing_item_annotated_positive_support == 3
    assert metrics.missing_item_positive_support == 1
    assert metrics.missing_item_false_negatives == 1
    assert metrics.missing_item_recall == 0.0
    assert metrics.coverage == 0.5


def test_build_repetition_evidence_counts_fresh_and_detects_unstable_cases() -> None:
    from types import SimpleNamespace

    from standards_atlas.application.assertion_qualification import build_repetition_evidence

    class FakeCase:
        source_document_key = "DOC"
        clause_id = ClauseId(value="c1")

        def __init__(self, exact: bool) -> None:
            self.exact = exact

        def model_dump(self, *, mode: str, exclude: set[str]):
            assert mode == "json"
            assert exclude == {"candidate_sha256", "provenance"}
            return {"exact": self.exact}

    reports = (
        SimpleNamespace(
            experiment_id="rep-1",
            variant_id="P2",
            effort=SimpleNamespace(calls=20, cached_calls=0),
            qualification_report=SimpleNamespace(cases=(FakeCase(True),)),
        ),
        SimpleNamespace(
            experiment_id="rep-2",
            variant_id="P2",
            effort=SimpleNamespace(calls=20, cached_calls=0),
            qualification_report=SimpleNamespace(cases=(FakeCase(False),)),
        ),
    )

    evidence = build_repetition_evidence(
        variant_id="P2",
        planned_repetitions=2,
        reports=reports,
        report_hashes=("1" * 64, "2" * 64),
    )

    assert evidence.fresh_inference_repetitions == 2
    assert evidence.cached_repetitions == 0
    assert evidence.unstable_case_ids == ("DOC:c1",)
