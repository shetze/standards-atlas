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
    assert metrics.false_acceptances == 1
    assert metrics.false_rejections == 1
    assert metrics.false_acceptance_rate == 1.0
    assert metrics.false_rejection_rate == 1.0
    assert metrics.missing_item_positive_support == 1
    assert metrics.missing_item_false_negatives == 1
    assert metrics.missing_item_recall == 0.0


def test_series_g_never_qualifies_from_synthetic_only_or_missing_human_freeze() -> None:
    metrics = evaluate_verifier_quality((_observation(kind=VerifierCaseKind.SYNTHETIC_MUTATION),))
    profile = SeriesGGateProfile(
        max_false_acceptance_rate=1.0,
        max_false_rejection_rate=1.0,
        min_missing_item_recall=0.0,
        min_verifier_coverage=1.0,
        min_real_annotated_cases=1,
        min_candidate_support=1,
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
