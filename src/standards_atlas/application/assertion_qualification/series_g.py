"""AP03 Series-G verifier measurement, repetition evidence and pre-Holdout freeze contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionClauseVerification,
    AssertionVerificationDisposition,
)

AP03_SERIES_G_CONTRACT = "ap03-series-g-verifier-freeze-v1"


class VerifierCaseKind(StrEnum):
    REAL_ANNOTATED = "real_annotated"
    SYNTHETIC_MUTATION = "synthetic_mutation"


class ExpectedCandidateDisposition(StrEnum):
    SUPPORTED = "supported"
    REJECTED = "rejected"


class VerifierCandidateTruth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    expected: ExpectedCandidateDisposition


class VerifierCaseTruth(BaseModel):
    """Human/fixture truth used to assess one verifier response without changing Golden data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    kind: VerifierCaseKind
    entity_candidates: tuple[VerifierCandidateTruth, ...] = ()
    assertion_candidates: tuple[VerifierCandidateTruth, ...] = ()
    missing_entity_expected: bool = False
    missing_assertion_expected: bool = False
    annotation_reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> VerifierCaseTruth:
        ids = [item.candidate_id for item in (*self.entity_candidates, *self.assertion_candidates)]
        if len(ids) != len(set(ids)):
            raise ValueError("verifier truth candidate ids must be unique per case")
        return self


class VerifierCaseObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    truth: VerifierCaseTruth
    verification: AssertionClauseVerification

    @model_validator(mode="after")
    def clause_matches(self) -> VerifierCaseObservation:
        if self.verification.clause_id.value != self.truth.clause_id:
            raise ValueError("verifier observation clause differs from annotated truth")
        return self


class VerifierQualityMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    annotated_cases: int = Field(ge=0)
    real_annotated_cases: int = Field(ge=0)
    synthetic_cases: int = Field(ge=0)
    candidate_support: int = Field(ge=0)
    candidate_reviewed: int = Field(ge=0)
    false_acceptances: int = Field(ge=0)
    false_rejections: int = Field(ge=0)
    abstentions: int = Field(ge=0)
    missing_item_positive_support: int = Field(ge=0)
    missing_item_true_positives: int = Field(ge=0)
    missing_item_false_negatives: int = Field(ge=0)
    missing_item_false_positives: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    false_acceptance_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    false_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_item_recall: float | None = Field(default=None, ge=0.0, le=1.0)


class RepetitionEvidence(BaseModel):
    """Evidence that stability runs are independent new inference attempts, not cache replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(min_length=1)
    planned_repetitions: int = Field(ge=1)
    completed_repetitions: int = Field(ge=0)
    fresh_inference_repetitions: int = Field(ge=0)
    cached_repetitions: int = Field(default=0, ge=0)
    report_hashes: tuple[str, ...] = ()
    unstable_case_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def counts_are_consistent(self) -> RepetitionEvidence:
        if self.completed_repetitions > self.planned_repetitions:
            raise ValueError("completed repetitions exceed the pre-authorized repetition count")
        if self.fresh_inference_repetitions + self.cached_repetitions != self.completed_repetitions:
            raise ValueError("fresh plus cached repetitions must equal completed repetitions")
        if self.fresh_inference_repetitions > len(self.report_hashes):
            raise ValueError("fresh repetitions require bound report hashes")
        return self


class SeriesGGateProfile(BaseModel):
    """Pre-Holdout G4/G5 gate values; no defaults that could silently qualify a system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_false_acceptance_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    max_false_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_missing_item_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    min_verifier_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    min_real_annotated_cases: int | None = Field(default=None, ge=1)
    min_candidate_support: int | None = Field(default=None, ge=1)
    required_fresh_repetitions: int | None = Field(default=None, ge=1)
    max_cached_repetitions: int = Field(default=0, ge=0)
    human_confirmed: bool = False
    human_confirmation_reference: str | None = None

    @model_validator(mode="after")
    def confirmation_is_bound(self) -> SeriesGGateProfile:
        if self.human_confirmed != (self.human_confirmation_reference is not None):
            raise ValueError("human confirmation boolean and reference must be supplied together")
        return self


class SeriesGFreeze(BaseModel):
    """Complete candidate freeze identity prepared before Holdout; never canonical adoption."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str = AP03_SERIES_G_CONTRACT
    freeze_id: str = Field(min_length=1)
    code_revision: str = Field(min_length=1)
    prompt_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_backend_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cascade_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retry_budget_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    development_golden_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    partition_exposure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_campaign_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_adoption_enabled: bool = False

    @model_validator(mode="after")
    def adoption_stays_disabled(self) -> SeriesGFreeze:
        if self.canonical_adoption_enabled:
            raise ValueError("Series G must not enable canonical adoption")
        return self


class SeriesGReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verifier_metrics: VerifierQualityMetrics
    repetition_evidence: RepetitionEvidence
    gate_profile: SeriesGGateProfile
    freeze: SeriesGFreeze | None = None
    gates_defined: bool
    verifier_evidence_sufficient: bool
    repetitions_sufficient: bool
    human_freeze_confirmed: bool
    ready_for_holdout: bool
    qualification_claim_permitted: bool = False
    blockers: tuple[str, ...] = ()


def evaluate_verifier_quality(
    observations: tuple[VerifierCaseObservation, ...],
) -> VerifierQualityMetrics:
    false_acceptances = false_rejections = abstentions = reviewed = support = 0
    missing_support = missing_tp = missing_fn = missing_fp = 0
    real = sum(item.truth.kind is VerifierCaseKind.REAL_ANNOTATED for item in observations)
    synthetic = len(observations) - real
    for observation in observations:
        actual = {
            review.candidate_id: review.disposition
            for review in (
                *observation.verification.entity_reviews,
                *observation.verification.assertion_reviews,
            )
        }
        for truth in (
            *observation.truth.entity_candidates,
            *observation.truth.assertion_candidates,
        ):
            support += 1
            disposition = actual.get(truth.candidate_id)
            if disposition is None:
                continue
            reviewed += 1
            if disposition is AssertionVerificationDisposition.UNCERTAIN:
                abstentions += 1
            elif (
                truth.expected is ExpectedCandidateDisposition.REJECTED
                and disposition is AssertionVerificationDisposition.SUPPORTED
            ):
                false_acceptances += 1
            elif (
                truth.expected is ExpectedCandidateDisposition.SUPPORTED
                and disposition is AssertionVerificationDisposition.REJECTED
            ):
                false_rejections += 1
        for expected, detected in (
            (
                observation.truth.missing_entity_expected,
                observation.verification.missing_entity_detected,
            ),
            (
                observation.truth.missing_assertion_expected,
                observation.verification.missing_assertion_detected,
            ),
        ):
            if expected:
                missing_support += 1
                if detected:
                    missing_tp += 1
                else:
                    missing_fn += 1
            elif detected:
                missing_fp += 1
    supported_expected = sum(
        item.expected is ExpectedCandidateDisposition.SUPPORTED
        for observation in observations
        for item in (*observation.truth.entity_candidates, *observation.truth.assertion_candidates)
    )
    rejected_expected = support - supported_expected
    return VerifierQualityMetrics(
        annotated_cases=len(observations),
        real_annotated_cases=real,
        synthetic_cases=synthetic,
        candidate_support=support,
        candidate_reviewed=reviewed,
        false_acceptances=false_acceptances,
        false_rejections=false_rejections,
        abstentions=abstentions,
        missing_item_positive_support=missing_support,
        missing_item_true_positives=missing_tp,
        missing_item_false_negatives=missing_fn,
        missing_item_false_positives=missing_fp,
        coverage=_ratio(reviewed, support),
        false_acceptance_rate=_ratio(false_acceptances, rejected_expected),
        false_rejection_rate=_ratio(false_rejections, supported_expected),
        missing_item_recall=_ratio(missing_tp, missing_support),
    )


def assess_series_g_readiness(
    *,
    metrics: VerifierQualityMetrics,
    repetitions: RepetitionEvidence,
    gate_profile: SeriesGGateProfile,
    freeze: SeriesGFreeze | None,
) -> SeriesGReadiness:
    required = (
        gate_profile.max_false_acceptance_rate,
        gate_profile.max_false_rejection_rate,
        gate_profile.min_missing_item_recall,
        gate_profile.min_verifier_coverage,
        gate_profile.min_real_annotated_cases,
        gate_profile.min_candidate_support,
        gate_profile.required_fresh_repetitions,
    )
    gates_defined = all(item is not None for item in required)
    blockers: list[str] = []
    if not gates_defined:
        blockers.append("gate_profile_incomplete")
    if metrics.real_annotated_cases == 0:
        blockers.append("no_real_annotated_verifier_cases")
    verifier_ok = gates_defined and all(
        (
            metrics.false_acceptance_rate is not None
            and metrics.false_acceptance_rate <= gate_profile.max_false_acceptance_rate,
            metrics.false_rejection_rate is not None
            and metrics.false_rejection_rate <= gate_profile.max_false_rejection_rate,
            metrics.missing_item_recall is not None
            and metrics.missing_item_recall >= gate_profile.min_missing_item_recall,
            metrics.coverage is not None and metrics.coverage >= gate_profile.min_verifier_coverage,
            metrics.real_annotated_cases >= gate_profile.min_real_annotated_cases,
            metrics.candidate_support >= gate_profile.min_candidate_support,
        )
    )
    if not verifier_ok:
        blockers.append("verifier_gate_not_met")
    repetitions_ok = bool(
        gates_defined
        and repetitions.fresh_inference_repetitions >= gate_profile.required_fresh_repetitions
        and repetitions.cached_repetitions <= gate_profile.max_cached_repetitions
        and repetitions.completed_repetitions == repetitions.planned_repetitions
    )
    if not repetitions_ok:
        blockers.append("fresh_repetition_evidence_incomplete")
    if not gate_profile.human_confirmed:
        blockers.append("human_gate_confirmation_missing")
    if freeze is None:
        blockers.append("finalist_freeze_missing")
    ready = not blockers
    return SeriesGReadiness(
        verifier_metrics=metrics,
        repetition_evidence=repetitions,
        gate_profile=gate_profile,
        freeze=freeze,
        gates_defined=gates_defined,
        verifier_evidence_sufficient=verifier_ok,
        repetitions_sufficient=repetitions_ok,
        human_freeze_confirmed=gate_profile.human_confirmed,
        ready_for_holdout=ready,
        qualification_claim_permitted=False,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def freeze_sha256(freeze: SeriesGFreeze) -> str:
    payload = json.dumps(
        freeze.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator
