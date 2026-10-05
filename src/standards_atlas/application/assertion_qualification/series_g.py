"""AP03 Series-G verifier measurement, repetition evidence and pre-Holdout freeze contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.cascade_models import (
    AssertionClauseVerification,
    AssertionVerificationDisposition,
    AssertionVerifierProvenance,
)

AP03_SERIES_G_CONTRACT = "ap03-series-g-verifier-freeze-v1"
AP03_SERIES_G_VERIFIER_RUN_CONTRACT = "ap03-series-g-verifier-run-v2"
SERIES_G_VERIFIER_PROMPT_VERSION = "ontology-guided-assertion-verifier-source-bound-v2"
SERIES_G_VERIFIER_VERSION = "2.1.0"
VERIFIER_REVIEW_COLUMNS = (
    "verifier_run_sha256",
    "row_kind",
    "case_id",
    "document_key",
    "clause_id",
    "candidate_id",
    "candidate_summary",
    "expected",
    "missing_entity_expected",
    "missing_assertion_expected",
    "annotation_reference",
)


class VerifierCaseKind(StrEnum):
    REAL_ANNOTATED = "real_annotated"
    SYNTHETIC_MUTATION = "synthetic_mutation"


class ExpectedCandidateDisposition(StrEnum):
    SUPPORTED = "supported"
    REJECTED = "rejected"


class VerifierRunCandidateKind(StrEnum):
    ENTITY = "entity"
    ASSERTION = "assertion"


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
    """One human truth record paired with the actual verifier outcome.

    A transport/response failure is retained as verifier evidence instead of silently dropping the
    case. Such a case contributes candidate support but no reviewed candidates, reducing coverage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    truth: VerifierCaseTruth
    verification: AssertionClauseVerification | None = None
    verification_error_type: str | None = None
    verification_error_message: str | None = None

    @model_validator(mode="after")
    def outcome_matches_truth(self) -> VerifierCaseObservation:
        has_error = self.verification_error_type is not None
        if has_error != (self.verification_error_message is not None):
            raise ValueError(
                "verifier observation error type and message must be supplied together"
            )
        if (self.verification is None) == (not has_error):
            raise ValueError("verifier observation requires exactly one verification or error")
        if (
            self.verification is not None
            and self.verification.clause_id.value != self.truth.clause_id
        ):
            raise ValueError("verifier observation clause differs from annotated truth")
        return self


class VerifierQualityMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    annotated_cases: int = Field(ge=0)
    real_annotated_cases: int = Field(ge=0)
    synthetic_cases: int = Field(ge=0)
    verifier_error_cases: int = Field(default=0, ge=0)
    candidate_support: int = Field(ge=0)
    candidate_reviewed: int = Field(ge=0)
    supported_candidate_support: int = Field(default=0, ge=0)
    rejected_candidate_support: int = Field(default=0, ge=0)
    false_acceptances: int = Field(ge=0)
    false_rejections: int = Field(ge=0)
    abstentions: int = Field(ge=0)
    missing_item_annotated_positive_support: int = Field(default=0, ge=0)
    missing_item_positive_support: int = Field(ge=0)
    missing_item_true_positives: int = Field(ge=0)
    missing_item_false_negatives: int = Field(ge=0)
    missing_item_false_positives: int = Field(ge=0)
    case_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_item_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    false_acceptance_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    false_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_item_recall: float | None = Field(default=None, ge=0.0, le=1.0)


class VerifierRunCandidate(BaseModel):
    """Source-candidate identity shown to the human reviewer without verifier disposition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(min_length=1)
    kind: VerifierRunCandidateKind
    summary: str = Field(min_length=1)


class VerifierRunCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    source_package_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidates: tuple[VerifierRunCandidate, ...] = ()
    verification: AssertionClauseVerification | None = None
    verification_error_type: str | None = None
    verification_error_message: str | None = None

    @model_validator(mode="after")
    def run_case_is_consistent(self) -> VerifierRunCase:
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("verifier run candidate ids must be unique per case")
        has_error = self.verification_error_type is not None
        if has_error != (self.verification_error_message is not None):
            raise ValueError("verifier run error type and message must be supplied together")
        if (self.verification is None) == (not has_error):
            raise ValueError("verifier run case requires exactly one verification or error")
        if self.verification is not None:
            if self.verification.clause_id.value != self.clause_id:
                raise ValueError("verifier run result belongs to a different clause")
            reviewed = {
                item.candidate_id
                for item in (
                    *self.verification.entity_reviews,
                    *self.verification.assertion_reviews,
                )
            }
            if reviewed != set(candidate_ids):
                raise ValueError("verifier result does not review the exact bound candidate set")
        return self


class SeriesGVerifierRun(BaseModel):
    """Bound verifier run over already-persisted Development experiment candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str = AP03_SERIES_G_VERIFIER_RUN_CONTRACT
    campaign_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    experiment_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    variant_id: str = Field(min_length=1)
    verifier_provenance: AssertionVerifierProvenance
    runtime_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_bypassed: bool = True
    authorized_max_calls: int = Field(ge=1)
    actual_calls: int = Field(ge=0)
    authorization_reference: str = Field(min_length=1)
    retry_of_verifier_run_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    retried_case_ids: tuple[str, ...] = ()
    inherited_case_count: int = Field(default=0, ge=0)
    cases: tuple[VerifierRunCase, ...] = ()

    @model_validator(mode="after")
    def run_is_bounded(self) -> SeriesGVerifierRun:
        if not self.cache_bypassed:
            raise ValueError("Series-G verifier benchmark must bypass result cache")
        if self.actual_calls > self.authorized_max_calls:
            raise ValueError("verifier run exceeds its authorized max_calls")
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("verifier run case ids must be unique")
        retried = self.retried_case_ids
        if len(retried) != len(set(retried)):
            raise ValueError("verifier retry case ids must be unique")
        if self.retry_of_verifier_run_sha256 is None:
            if retried or self.inherited_case_count:
                raise ValueError("non-retry verifier run cannot declare inherited or retried cases")
            if self.actual_calls != len(self.cases):
                raise ValueError("verifier run actual call count must match persisted cases")
        else:
            if not retried:
                raise ValueError("verifier retry run requires at least one retried case")
            if not set(retried).issubset(ids):
                raise ValueError("verifier retry references a case outside the merged run")
            if self.actual_calls != len(retried):
                raise ValueError("verifier retry actual_calls must match retried case count")
            if self.inherited_case_count != len(self.cases) - self.actual_calls:
                raise ValueError("verifier retry inherited case count is inconsistent")
        return self


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
        if len(self.report_hashes) != self.completed_repetitions:
            raise ValueError("every completed repetition requires one bound report hash")
        if len(self.report_hashes) != len(set(self.report_hashes)):
            raise ValueError("repetition report hashes must be unique")
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
    min_supported_candidate_support: int | None = Field(default=None, ge=1)
    min_rejected_candidate_support: int | None = Field(default=None, ge=1)
    min_missing_item_positive_support: int | None = Field(default=None, ge=1)
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


def verifier_run_sha256(run: SeriesGVerifierRun) -> str:
    return _canonical_sha256(run.model_dump(mode="json"))


def render_verifier_review_csv(run: SeriesGVerifierRun) -> str:
    """Create a blind flat review sheet; verifier dispositions are deliberately omitted."""

    digest = verifier_run_sha256(run)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=VERIFIER_REVIEW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for case in run.cases:
        writer.writerow(
            {
                "verifier_run_sha256": digest,
                "row_kind": "case",
                "case_id": case.case_id,
                "document_key": case.document_key,
                "clause_id": case.clause_id,
                "candidate_id": "",
                "candidate_summary": "",
                "expected": "",
                "missing_entity_expected": "",
                "missing_assertion_expected": "",
                "annotation_reference": "",
            }
        )
        for candidate in case.candidates:
            writer.writerow(
                {
                    "verifier_run_sha256": digest,
                    "row_kind": candidate.kind.value,
                    "case_id": case.case_id,
                    "document_key": case.document_key,
                    "clause_id": case.clause_id,
                    "candidate_id": candidate.candidate_id,
                    "candidate_summary": candidate.summary,
                    "expected": "",
                    "missing_entity_expected": "",
                    "missing_assertion_expected": "",
                    "annotation_reference": "",
                }
            )
    return stream.getvalue()


def build_verifier_observations_from_review_csv(
    run: SeriesGVerifierRun,
    reviewed_csv: str,
) -> tuple[VerifierCaseObservation, ...]:
    """Bind human candidate truth to the hidden verifier result without inventing decisions."""

    reader = csv.DictReader(io.StringIO(reviewed_csv))
    if tuple(reader.fieldnames or ()) != VERIFIER_REVIEW_COLUMNS:
        raise ValueError("verifier review CSV header does not match the Series-G contract")
    rows = list(reader)
    expected_run_hash = verifier_run_sha256(run)
    if any(row["verifier_run_sha256"] != expected_run_hash for row in rows):
        raise ValueError("verifier review CSV belongs to a different verifier run")

    rows_by_case: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        rows_by_case.setdefault(row["case_id"], []).append(row)
    if set(rows_by_case) != {case.case_id for case in run.cases}:
        raise ValueError("verifier review CSV case set differs from the bound verifier run")

    observations: list[VerifierCaseObservation] = []
    for case in run.cases:
        case_rows = rows_by_case[case.case_id]
        metadata_rows = [row for row in case_rows if row["row_kind"] == "case"]
        if len(metadata_rows) != 1:
            raise ValueError(f"verifier review case {case.case_id} requires exactly one case row")
        metadata = metadata_rows[0]
        _validate_review_identity(metadata, case)
        annotation_reference = metadata["annotation_reference"].strip()
        if not annotation_reference:
            raise ValueError(f"verifier review case {case.case_id} lacks annotation_reference")
        missing_entity = _review_bool(
            metadata["missing_entity_expected"],
            field="missing_entity_expected",
            case_id=case.case_id,
        )
        missing_assertion = _review_bool(
            metadata["missing_assertion_expected"],
            field="missing_assertion_expected",
            case_id=case.case_id,
        )

        candidate_rows = [row for row in case_rows if row["row_kind"] != "case"]
        by_candidate = {row["candidate_id"]: row for row in candidate_rows}
        expected_candidates = {item.candidate_id for item in case.candidates}
        if set(by_candidate) != expected_candidates or len(by_candidate) != len(candidate_rows):
            raise ValueError(
                f"verifier review case {case.case_id} candidate rows differ from bound candidates"
            )
        entity_truth: list[VerifierCandidateTruth] = []
        assertion_truth: list[VerifierCandidateTruth] = []
        by_id = {item.candidate_id: item for item in case.candidates}
        for candidate_id in sorted(expected_candidates):
            candidate = by_id[candidate_id]
            row = by_candidate[candidate_id]
            _validate_review_identity(row, case)
            if row["row_kind"] != candidate.kind.value:
                raise ValueError(
                    f"verifier review candidate {candidate_id} kind differs from bound candidate"
                )
            if row["candidate_summary"] != candidate.summary:
                raise ValueError(f"verifier review candidate {candidate_id} summary was modified")
            try:
                expected = ExpectedCandidateDisposition(row["expected"].strip())
            except ValueError as exc:
                raise ValueError(
                    f"verifier review candidate {candidate_id} requires supported or rejected"
                ) from exc
            truth = VerifierCandidateTruth(candidate_id=candidate_id, expected=expected)
            target = (
                entity_truth
                if candidate.kind is VerifierRunCandidateKind.ENTITY
                else assertion_truth
            )
            target.append(truth)

        observations.append(
            VerifierCaseObservation(
                truth=VerifierCaseTruth(
                    case_id=case.case_id,
                    clause_id=case.clause_id,
                    kind=VerifierCaseKind.REAL_ANNOTATED,
                    entity_candidates=tuple(entity_truth),
                    assertion_candidates=tuple(assertion_truth),
                    missing_entity_expected=missing_entity,
                    missing_assertion_expected=missing_assertion,
                    annotation_reference=annotation_reference,
                ),
                verification=case.verification,
                verification_error_type=case.verification_error_type,
                verification_error_message=case.verification_error_message,
            )
        )
    return tuple(observations)


def evaluate_verifier_quality(
    observations: tuple[VerifierCaseObservation, ...],
) -> VerifierQualityMetrics:
    false_acceptances = false_rejections = abstentions = reviewed = support = 0
    supported_reviewed = rejected_reviewed = 0
    missing_support = missing_tp = missing_fn = missing_fp = 0
    real = sum(item.truth.kind is VerifierCaseKind.REAL_ANNOTATED for item in observations)
    synthetic = len(observations) - real
    verifier_errors = sum(item.verification is None for item in observations)
    annotated_missing_positive = sum(
        int(observation.truth.missing_entity_expected)
        + int(observation.truth.missing_assertion_expected)
        for observation in observations
    )
    for observation in observations:
        verification = observation.verification
        actual = (
            {
                review.candidate_id: review.disposition
                for review in (*verification.entity_reviews, *verification.assertion_reviews)
            }
            if verification is not None
            else {}
        )
        for truth in (
            *observation.truth.entity_candidates,
            *observation.truth.assertion_candidates,
        ):
            support += 1
            disposition = actual.get(truth.candidate_id)
            if disposition is None:
                continue
            reviewed += 1
            if truth.expected is ExpectedCandidateDisposition.SUPPORTED:
                supported_reviewed += 1
            else:
                rejected_reviewed += 1
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
        if verification is None:
            continue
        for expected, detected in (
            (
                observation.truth.missing_entity_expected,
                verification.missing_entity_detected,
            ),
            (
                observation.truth.missing_assertion_expected,
                verification.missing_assertion_detected,
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
    case_coverage = _ratio(len(observations) - verifier_errors, len(observations))
    candidate_coverage = _ratio(reviewed, support)
    missing_item_coverage = _ratio(
        2 * (len(observations) - verifier_errors),
        2 * len(observations),
    )
    coverage_values = tuple(
        item
        for item in (case_coverage, candidate_coverage, missing_item_coverage)
        if item is not None
    )
    conservative_coverage = min(coverage_values) if coverage_values else None
    return VerifierQualityMetrics(
        annotated_cases=len(observations),
        real_annotated_cases=real,
        synthetic_cases=synthetic,
        verifier_error_cases=verifier_errors,
        candidate_support=support,
        candidate_reviewed=reviewed,
        supported_candidate_support=supported_reviewed,
        rejected_candidate_support=rejected_reviewed,
        false_acceptances=false_acceptances,
        false_rejections=false_rejections,
        abstentions=abstentions,
        missing_item_annotated_positive_support=annotated_missing_positive,
        missing_item_positive_support=missing_support,
        missing_item_true_positives=missing_tp,
        missing_item_false_negatives=missing_fn,
        missing_item_false_positives=missing_fp,
        case_coverage=case_coverage,
        candidate_coverage=candidate_coverage,
        missing_item_coverage=missing_item_coverage,
        coverage=conservative_coverage,
        false_acceptance_rate=_ratio(false_acceptances, rejected_reviewed),
        false_rejection_rate=_ratio(false_rejections, supported_reviewed),
        missing_item_recall=_ratio(missing_tp, missing_support),
    )


def build_repetition_evidence(
    *,
    variant_id: str,
    planned_repetitions: int,
    reports: Sequence[object],
    report_hashes: Sequence[str],
) -> RepetitionEvidence:
    """Build S14 evidence from experiment reports without treating cache replay as fresh."""

    if len(reports) != len(report_hashes):
        raise ValueError("repetition reports and report hashes must have the same length")
    if any(getattr(report, "variant_id", None) != variant_id for report in reports):
        raise ValueError("repetition report variant differs from requested Finalist variant")
    experiment_ids = [str(getattr(report, "experiment_id", "")) for report in reports]
    if len(experiment_ids) != len(set(experiment_ids)):
        raise ValueError("fresh repetition evidence requires distinct experiment ids")

    fresh = cached = 0
    for report in reports:
        effort = report.effort
        if effort.cached_calls:
            cached += 1
        elif effort.calls > 0:
            fresh += 1
        else:
            raise ValueError("repetition report has neither fresh calls nor explicit cache use")
    return RepetitionEvidence(
        variant_id=variant_id,
        planned_repetitions=planned_repetitions,
        completed_repetitions=len(reports),
        fresh_inference_repetitions=fresh,
        cached_repetitions=cached,
        report_hashes=tuple(report_hashes),
        unstable_case_ids=_unstable_case_ids(reports),
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
        gate_profile.min_supported_candidate_support,
        gate_profile.min_rejected_candidate_support,
        gate_profile.min_missing_item_positive_support,
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
            metrics.supported_candidate_support >= gate_profile.min_supported_candidate_support,
            metrics.rejected_candidate_support >= gate_profile.min_rejected_candidate_support,
            metrics.missing_item_positive_support >= gate_profile.min_missing_item_positive_support,
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
    return _canonical_sha256(freeze.model_dump(mode="json"))


def _validate_review_identity(row: Mapping[str, str], case: VerifierRunCase) -> None:
    if row["document_key"] != case.document_key or row["clause_id"] != case.clause_id:
        raise ValueError(f"verifier review case {case.case_id} identity was modified")


def _review_bool(value: str, *, field: str, case_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"verifier review case {case_id} requires true/false for {field}")


def _unstable_case_ids(reports: Sequence[object]) -> tuple[str, ...]:
    if len(reports) < 2:
        return ()
    signatures: dict[str, set[str]] = {}
    for report in reports:
        qualification = report.qualification_report
        for case in qualification.cases:
            case_id = f"{case.source_document_key}:{case.clause_id.value}"
            payload = case.model_dump(
                mode="json",
                exclude={"candidate_sha256", "provenance"},
            )
            signatures.setdefault(case_id, set()).add(_canonical_sha256(payload))
    return tuple(sorted(case_id for case_id, values in signatures.items() if len(values) > 1))


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator
