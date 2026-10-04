"""AP03 Series-H isolated Holdout campaign and bounded release decision contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.assertion_qualification.evaluation import golden_suite_sha256
from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentManifest,
    AssertionExperimentReport,
    manifest_sha256,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionDiagnosticCode,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
    RatioMetric,
)
from standards_atlas.application.assertion_qualification.reference_corpus import ReferenceCorpusPlan
from standards_atlas.application.assertion_qualification.series_g import (
    SeriesGReadiness,
    freeze_sha256,
)
from standards_atlas.application.schema.model import SchemaBoundModel

AP03_SERIES_H_CAMPAIGN_CONTRACT = "ap03-series-h-holdout-campaign-v1"
AP03_SERIES_H_GATE_PROFILE_CONTRACT = "ap03-series-h-g0-g6-profile-v1"
AP03_SERIES_H_COMPLETION_CONTRACT = "ap03-series-h-completion-v1"
AP03_SERIES_H_SCHEMA_VERSION = 1


class SeriesHExperimentRole(StrEnum):
    FINALIST = "finalist"
    BASELINE = "baseline"


class SeriesHMetric(StrEnum):
    TECHNICAL_COMPLETION = "technical_completion"
    CANDIDATE_CLAUSE_COVERAGE = "candidate_clause_coverage"
    ENTITY_PRECISION = "entity_precision"
    ENTITY_RECALL = "entity_recall"
    TYPED_ENTITY_PRECISION = "typed_entity_precision"
    TYPED_ENTITY_RECALL = "typed_entity_recall"
    ENTITY_CLASS_ACCURACY = "entity_class_accuracy"
    WORK_PRODUCT_PRECISION = "work_product_precision"
    WORK_PRODUCT_RECALL = "work_product_recall"
    WORK_PRODUCT_CLASS_ACCURACY = "work_product_class_accuracy"
    REQUIRED_WORK_PRODUCT_RELATION_RECALL = "required_work_product_relation_recall"
    ASSERTION_PRECISION = "assertion_precision"
    ASSERTION_RECALL = "assertion_recall"
    PREDICATE_ACCURACY = "predicate_accuracy"
    NORMATIVE_FORCE_ACCURACY = "normative_force_accuracy"
    EVIDENCE_INTEGRITY_VALIDITY = "evidence_integrity_validity"
    EVIDENCE_SPAN_EXACT_MATCH = "evidence_span_exact_match"
    EXACT_ASSERTION_ACCURACY = "exact_assertion_accuracy"
    CLAUSE_EXACT_MATCH = "clause_exact_match"


class SeriesHGateOperator(StrEnum):
    GREATER_OR_EQUAL = "ge"
    LESS_OR_EQUAL = "le"


class SeriesHMetricGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: SeriesHMetric
    operator: SeriesHGateOperator
    threshold: float = Field(ge=0.0, le=1.0)
    min_support: int = Field(ge=1)


class SeriesHGateProfile(SchemaBoundModel):
    """Pre-Holdout G0-G6 policy.

    Numeric values are project-owned and have no qualifying defaults.
    """

    SCHEMA_FAMILY: ClassVar[str] = "ap03-series-h-gate-profile"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = AP03_SERIES_H_SCHEMA_VERSION
    contract_id: str = AP03_SERIES_H_GATE_PROFILE_CONTRACT
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    min_holdout_cases: int = Field(ge=1)
    min_independent_source_groups: int = Field(ge=1)
    max_failed_cells: int = Field(ge=0)
    max_not_executed_cells: int = Field(ge=0)
    max_cached_calls: int = Field(ge=0)
    require_native_package_verified: Literal[True] = True
    metric_gates: tuple[SeriesHMetricGate, ...] = Field(min_length=1)
    critical_diagnostic_codes: tuple[AssertionDiagnosticCode, ...] = Field(min_length=1)
    max_critical_findings_per_repetition: int = Field(ge=0)

    @model_validator(mode="after")
    def gates_are_unique(self) -> SeriesHGateProfile:
        metrics = [item.metric for item in self.metric_gates]
        if len(metrics) != len(set(metrics)):
            raise ValueError("Series-H metric gates must be unique")
        if len(self.critical_diagnostic_codes) != len(set(self.critical_diagnostic_codes)):
            raise ValueError("Series-H critical diagnostic codes must be unique")
        return self


class SeriesHHoldoutExperimentRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: SeriesHExperimentRole
    experiment_id: str = Field(min_length=1)
    variant_id: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repetitions: int = Field(ge=1)


class SeriesHHoldoutCampaign(SchemaBoundModel):
    """Frozen Holdout run order. It contains identities only, never expected semantic content."""

    SCHEMA_FAMILY: ClassVar[str] = "ap03-series-h-holdout-campaign"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = AP03_SERIES_H_SCHEMA_VERSION
    contract_id: str = AP03_SERIES_H_CAMPAIGN_CONTRACT
    campaign_id: str = Field(min_length=1)
    campaign_version: str = Field(min_length=1)
    holdout_suite_id: str = Field(min_length=1)
    holdout_suite_version: str = Field(min_length=1)
    holdout_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    partition_exposure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiments: tuple[SeriesHHoldoutExperimentRef, ...] = Field(min_length=1)
    execution_order: tuple[str, ...] = Field(min_length=1)
    optimizer_access_permitted: Literal[False] = False
    expected_values_exposed_to_extractor: Literal[False] = False
    adaptive_variant_selection: Literal[False] = False
    gate_changes_after_start_permitted: Literal[False] = False
    canonical_adoption_enabled: Literal[False] = False

    @model_validator(mode="after")
    def campaign_is_fixed(self) -> SeriesHHoldoutCampaign:
        ids = [item.experiment_id for item in self.experiments]
        if len(ids) != len(set(ids)):
            raise ValueError("Series-H experiment ids must be unique")
        if tuple(ids) != self.execution_order:
            raise ValueError(
                "Series-H execution_order must exactly match the frozen experiment list"
            )
        if sum(item.role is SeriesHExperimentRole.FINALIST for item in self.experiments) != 1:
            raise ValueError("Series H requires exactly one finalist experiment")
        return self


class SeriesHHoldoutPreflight(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: Literal["ap03-series-h-preflight-v1"] = "ap03-series-h-preflight-v1"
    campaign_id: str
    campaign_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_id: str | None = None
    freeze_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    gate_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    partition_exposure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_cases: int = Field(ge=0)
    independent_source_groups: int = Field(ge=0)
    manifest_bindings_valid: bool
    exposure_clear: bool
    ready_to_execute: bool
    model_calls: Literal[0] = 0
    blockers: tuple[str, ...] = ()


class SeriesHMetricGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: SeriesHMetric
    operator: SeriesHGateOperator
    threshold: float
    min_support: int
    observed_values: tuple[float | None, ...]
    supports: tuple[int, ...]
    passed: bool


class SeriesHHoldoutStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class SeriesHHoldoutAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    campaign_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_id: str | None = None
    freeze_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    gate_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    partition_exposure_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: SeriesHHoldoutStatus
    planned_reports: int = Field(ge=1)
    supplied_reports: int = Field(ge=0)
    report_hashes: tuple[str, ...] = ()
    metric_checks: tuple[SeriesHMetricGateResult, ...] = ()
    critical_findings_per_finalist_repetition: tuple[int, ...] = ()
    technical_gate_passed: bool
    engineering_gate_passed: bool
    critical_semantics_gate_passed: bool
    all_planned_evidence_present: bool
    blockers: tuple[str, ...] = ()


class SeriesHReleaseDecision(StrEnum):
    APPROVE_BOUNDED_PILOT = "approve_bounded_pilot"
    DO_NOT_APPROVE = "do_not_approve"


class SeriesHReleaseAttestation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: SeriesHReleaseDecision
    reference: str = Field(min_length=1)


class SeriesHCompletionState(StrEnum):
    IMPLEMENTED_NOT_EVALUATED = "implemented_not_evaluated"
    EVALUATED_NOT_QUALIFIED = "evaluated_not_qualified"
    QUALIFIED_FOR_BOUNDED_PILOT = "qualified_for_bounded_pilot"
    BLOCKED_BY_MISSING_EVIDENCE = "blocked_by_missing_evidence"


class SeriesHCompletionReport(SchemaBoundModel):
    SCHEMA_FAMILY: ClassVar[str] = "ap03-series-h-completion-report"
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = AP03_SERIES_H_SCHEMA_VERSION
    contract_id: str = AP03_SERIES_H_COMPLETION_CONTRACT
    campaign_id: str
    campaign_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: SeriesHCompletionState
    technically_implemented: Literal[True] = True
    experimentally_evaluated: bool
    qualified_for_bounded_pilot: bool
    qualification_scope: str | None = None
    holdout_assessment: SeriesHHoldoutAssessment
    release_attestation: SeriesHReleaseAttestation | None = None
    canonical_adoption_enabled: Literal[False] = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def qualification_is_bounded(self) -> SeriesHCompletionReport:
        if self.qualified_for_bounded_pilot:
            if self.state is not SeriesHCompletionState.QUALIFIED_FOR_BOUNDED_PILOT:
                raise ValueError("qualified flag requires qualified_for_bounded_pilot state")
            if not self.qualification_scope:
                raise ValueError("bounded qualification requires an explicit qualification scope")
            if self.release_attestation is None or (
                self.release_attestation.decision
                is not SeriesHReleaseDecision.APPROVE_BOUNDED_PILOT
            ):
                raise ValueError("bounded qualification requires explicit human approval")
        return self


def series_h_gate_profile_sha256(profile: SeriesHGateProfile) -> str:
    return _model_sha256(profile.model_dump(mode="json"))


def series_h_campaign_sha256(campaign: SeriesHHoldoutCampaign) -> str:
    return _model_sha256(campaign.model_dump(mode="json"))


def series_h_report_sha256(report: AssertionExperimentReport) -> str:
    return _model_sha256(report.model_dump(mode="json"))


def build_series_h_campaign(
    *,
    campaign_id: str,
    campaign_version: str,
    suite: AssertionGoldenSuite,
    reference_plan: ReferenceCorpusPlan,
    gate_profile: SeriesHGateProfile,
    experiments: tuple[tuple[SeriesHExperimentRole, AssertionExperimentManifest], ...],
) -> SeriesHHoldoutCampaign:
    if suite.partition is not AssertionGoldenPartition.HOLDOUT:
        raise ValueError("Series H requires a Holdout golden suite")
    _validate_suite_against_reference_plan(suite, reference_plan)
    refs: list[SeriesHHoldoutExperimentRef] = []
    for role, manifest in experiments:
        _validate_manifest_for_holdout(manifest, suite)
        refs.append(
            SeriesHHoldoutExperimentRef(
                role=role,
                experiment_id=manifest.experiment_id,
                variant_id=manifest.variant_id,
                manifest_sha256=manifest_sha256(manifest),
                repetitions=manifest.repetitions,
            )
        )
    return SeriesHHoldoutCampaign(
        campaign_id=campaign_id,
        campaign_version=campaign_version,
        holdout_suite_id=suite.id,
        holdout_suite_version=suite.version,
        holdout_suite_sha256=golden_suite_sha256(suite),
        partition_exposure_sha256=reference_plan.plan_sha256,
        gate_profile_sha256=series_h_gate_profile_sha256(gate_profile),
        experiments=tuple(refs),
        execution_order=tuple(item.experiment_id for item in refs),
    )


def validate_series_h_campaign(
    *,
    readiness: SeriesGReadiness,
    campaign: SeriesHHoldoutCampaign,
    gate_profile: SeriesHGateProfile,
    suite: AssertionGoldenSuite,
    reference_plan: ReferenceCorpusPlan,
    manifests: tuple[AssertionExperimentManifest, ...],
) -> SeriesHHoldoutPreflight:
    blockers: list[str] = []
    campaign_hash = series_h_campaign_sha256(campaign)
    gate_hash = series_h_gate_profile_sha256(gate_profile)
    suite_hash = golden_suite_sha256(suite)
    freeze = readiness.freeze

    if not readiness.ready_for_holdout or readiness.blockers:
        blockers.append("series_g_readiness_not_clear")
    if freeze is None:
        blockers.append("series_g_freeze_missing")
    elif freeze.holdout_campaign_sha256 != campaign_hash:
        blockers.append("holdout_campaign_differs_from_freeze")
    if campaign.gate_profile_sha256 != gate_hash:
        blockers.append("gate_profile_differs_from_campaign")
    if campaign.partition_exposure_sha256 != reference_plan.plan_sha256:
        blockers.append("partition_exposure_differs_from_campaign")
    if freeze is not None and freeze.partition_exposure_sha256 != reference_plan.plan_sha256:
        blockers.append("partition_exposure_differs_from_freeze")

    if suite.partition is not AssertionGoldenPartition.HOLDOUT:
        blockers.append("golden_suite_is_not_holdout")
    if (
        campaign.holdout_suite_id,
        campaign.holdout_suite_version,
        campaign.holdout_suite_sha256,
    ) != (suite.id, suite.version, suite_hash):
        blockers.append("holdout_suite_differs_from_campaign")

    exposure_clear = True
    try:
        _validate_suite_against_reference_plan(suite, reference_plan)
    except ValueError:
        exposure_clear = False
        blockers.append("holdout_exposure_or_partition_not_clear")

    by_id = {item.experiment_id: item for item in manifests}
    if len(by_id) != len(manifests) or set(by_id) != set(campaign.execution_order):
        blockers.append("holdout_manifest_set_differs_from_campaign")
    manifest_bindings_valid = True
    for ref in campaign.experiments:
        manifest = by_id.get(ref.experiment_id)
        if manifest is None:
            manifest_bindings_valid = False
            continue
        try:
            _validate_manifest_for_holdout(manifest, suite)
        except ValueError:
            manifest_bindings_valid = False
            continue
        if (
            manifest_sha256(manifest) != ref.manifest_sha256
            or manifest.variant_id != ref.variant_id
            or manifest.repetitions != ref.repetitions
        ):
            manifest_bindings_valid = False
        if not manifest.execution_authorized or not manifest.authorization_reference:
            manifest_bindings_valid = False
        if freeze is not None and manifest.code_revision != freeze.code_revision:
            manifest_bindings_valid = False
    if not manifest_bindings_valid:
        blockers.append("holdout_manifest_binding_invalid")

    groups = {
        planned.source_group
        for planned in reference_plan.holdout
        if (planned.document_key, planned.clause_id)
        in {(case.source_document_key, case.clause_id.value) for case in suite.cases}
    }
    return SeriesHHoldoutPreflight(
        campaign_id=campaign.campaign_id,
        campaign_sha256=campaign_hash,
        freeze_id=freeze.freeze_id if freeze is not None else None,
        freeze_sha256=freeze_sha256(freeze) if freeze is not None else None,
        gate_profile_sha256=gate_hash,
        holdout_suite_sha256=suite_hash,
        partition_exposure_sha256=reference_plan.plan_sha256,
        holdout_cases=len(suite.cases),
        independent_source_groups=len(groups) if exposure_clear else 0,
        manifest_bindings_valid=manifest_bindings_valid,
        exposure_clear=exposure_clear,
        ready_to_execute=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def assess_series_h_holdout(
    *,
    preflight: SeriesHHoldoutPreflight,
    campaign: SeriesHHoldoutCampaign,
    gate_profile: SeriesHGateProfile,
    reports: tuple[AssertionExperimentReport, ...],
) -> SeriesHHoldoutAssessment:
    planned = sum(item.repetitions for item in campaign.experiments)
    blockers: list[str] = list(preflight.blockers)
    if not preflight.ready_to_execute:
        return SeriesHHoldoutAssessment(
            campaign_id=campaign.campaign_id,
            campaign_sha256=series_h_campaign_sha256(campaign),
            freeze_id=preflight.freeze_id,
            freeze_sha256=preflight.freeze_sha256,
            gate_profile_sha256=preflight.gate_profile_sha256,
            holdout_suite_sha256=preflight.holdout_suite_sha256,
            partition_exposure_sha256=preflight.partition_exposure_sha256,
            status=SeriesHHoldoutStatus.NOT_EVALUABLE,
            planned_reports=planned,
            supplied_reports=len(reports),
            technical_gate_passed=False,
            engineering_gate_passed=False,
            critical_semantics_gate_passed=False,
            all_planned_evidence_present=False,
            blockers=tuple(dict.fromkeys((*blockers, "holdout_preflight_not_clear"))),
        )

    refs = {item.experiment_id: item for item in campaign.experiments}
    expected_keys = {
        (item.experiment_id, repetition)
        for item in campaign.experiments
        for repetition in range(1, item.repetitions + 1)
    }
    actual: dict[tuple[str, int], AssertionExperimentReport] = {}
    report_hashes: list[str] = []
    for report in reports:
        key = (report.experiment_id, report.evaluation_repetition)
        if key in actual:
            raise ValueError(f"duplicate Series-H report for {key!r}")
        ref = refs.get(report.experiment_id)
        if ref is None:
            raise ValueError(f"Series-H report is outside frozen campaign: {report.experiment_id}")
        if report.manifest_sha256 != ref.manifest_sha256 or report.variant_id != ref.variant_id:
            raise ValueError("Series-H report identity differs from frozen campaign")
        qualification = report.qualification_report
        if qualification.golden_partition is not AssertionGoldenPartition.HOLDOUT:
            raise ValueError("Series-H report is not bound to a Holdout qualification")
        if (
            qualification.golden_suite_id,
            qualification.golden_suite_version,
            qualification.golden_suite_hash,
        ) != (
            campaign.holdout_suite_id,
            campaign.holdout_suite_version,
            campaign.holdout_suite_sha256,
        ):
            raise ValueError("Series-H report Holdout suite differs from frozen campaign")
        actual[key] = report
        report_hashes.append(series_h_report_sha256(report))

    missing = expected_keys - set(actual)
    extra = set(actual) - expected_keys
    all_present = not missing and not extra
    if missing:
        blockers.append("planned_holdout_reports_missing")
    if extra:
        blockers.append("unexpected_holdout_reports_present")

    technical_ok = all_present and preflight.holdout_cases >= gate_profile.min_holdout_cases
    technical_ok = technical_ok and (
        preflight.independent_source_groups >= gate_profile.min_independent_source_groups
    )
    for report in actual.values():
        technical_ok = (
            technical_ok and report.coverage.failed_cells <= gate_profile.max_failed_cells
        )
        technical_ok = technical_ok and (
            report.coverage.not_executed_cells <= gate_profile.max_not_executed_cells
        )
        technical_ok = technical_ok and report.effort.cached_calls <= gate_profile.max_cached_calls
        if gate_profile.require_native_package_verified:
            technical_ok = technical_ok and (
                report.qualification_report.source_binding == "native_package_verified"
            )
    if not technical_ok:
        blockers.append("g0_g1_technical_gate_not_met")

    finalist = next(
        item for item in campaign.experiments if item.role is SeriesHExperimentRole.FINALIST
    )
    finalist_reports = tuple(
        actual[key] for key in sorted(actual) if key[0] == finalist.experiment_id
    )
    metric_checks = tuple(
        _metric_gate_result(gate, finalist_reports) for gate in gate_profile.metric_gates
    )
    engineering_ok = bool(finalist_reports) and all(item.passed for item in metric_checks)
    if not engineering_ok:
        blockers.append("g2_engineering_quality_gate_not_met")

    critical_counts = tuple(
        _critical_finding_count(report, gate_profile.critical_diagnostic_codes)
        for report in finalist_reports
    )
    critical_ok = bool(finalist_reports) and all(
        count <= gate_profile.max_critical_findings_per_repetition for count in critical_counts
    )
    if not critical_ok:
        blockers.append("g3_critical_semantics_gate_not_met")

    if not all_present:
        status = SeriesHHoldoutStatus.NOT_EVALUABLE
    elif technical_ok and engineering_ok and critical_ok:
        status = SeriesHHoldoutStatus.PASSED
    else:
        status = SeriesHHoldoutStatus.FAILED
    return SeriesHHoldoutAssessment(
        campaign_id=campaign.campaign_id,
        campaign_sha256=series_h_campaign_sha256(campaign),
        freeze_id=preflight.freeze_id,
        freeze_sha256=preflight.freeze_sha256,
        gate_profile_sha256=preflight.gate_profile_sha256,
        holdout_suite_sha256=preflight.holdout_suite_sha256,
        partition_exposure_sha256=preflight.partition_exposure_sha256,
        status=status,
        planned_reports=planned,
        supplied_reports=len(reports),
        report_hashes=tuple(report_hashes),
        metric_checks=metric_checks,
        critical_findings_per_finalist_repetition=critical_counts,
        technical_gate_passed=technical_ok,
        engineering_gate_passed=engineering_ok,
        critical_semantics_gate_passed=critical_ok,
        all_planned_evidence_present=all_present,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def finalize_series_h(
    *,
    assessment: SeriesHHoldoutAssessment,
    release_attestation: SeriesHReleaseAttestation | None = None,
    qualification_scope: str | None = None,
) -> SeriesHCompletionReport:
    blockers = list(assessment.blockers)
    experimentally_evaluated = assessment.status in {
        SeriesHHoldoutStatus.PASSED,
        SeriesHHoldoutStatus.FAILED,
    }
    qualified = False
    if assessment.status is SeriesHHoldoutStatus.NOT_EVALUABLE:
        state = (
            SeriesHCompletionState.BLOCKED_BY_MISSING_EVIDENCE
            if blockers
            else SeriesHCompletionState.IMPLEMENTED_NOT_EVALUATED
        )
    elif assessment.status is SeriesHHoldoutStatus.FAILED:
        state = SeriesHCompletionState.EVALUATED_NOT_QUALIFIED
        blockers.append("holdout_gate_failed")
    elif release_attestation is None:
        state = SeriesHCompletionState.EVALUATED_NOT_QUALIFIED
        blockers.append("human_release_decision_missing")
    elif release_attestation.decision is SeriesHReleaseDecision.DO_NOT_APPROVE:
        state = SeriesHCompletionState.EVALUATED_NOT_QUALIFIED
        blockers.append("human_release_not_approved")
    else:
        if qualification_scope is None or not qualification_scope.strip():
            raise ValueError("approved bounded pilot requires --qualification-scope")
        state = SeriesHCompletionState.QUALIFIED_FOR_BOUNDED_PILOT
        qualified = True
    return SeriesHCompletionReport(
        campaign_id=assessment.campaign_id,
        campaign_sha256=assessment.campaign_sha256,
        state=state,
        experimentally_evaluated=experimentally_evaluated,
        qualified_for_bounded_pilot=qualified,
        qualification_scope=(
            qualification_scope.strip() if qualified and qualification_scope else None
        ),
        holdout_assessment=assessment,
        release_attestation=release_attestation,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def render_series_h_quality_report(
    report: SeriesHCompletionReport,
    *,
    campaign: SeriesHHoldoutCampaign | None = None,
    experiment_reports: tuple[AssertionExperimentReport, ...] = (),
    reference_plan: ReferenceCorpusPlan | None = None,
) -> str:
    assessment = report.holdout_assessment
    lines = [
        f"# AP03 Series H quality report — {report.campaign_id}",
        "",
        f"- Completion state: `{report.state.value}`",
        f"- Technically implemented: `{str(report.technically_implemented).lower()}`",
        f"- Experimentally evaluated: `{str(report.experimentally_evaluated).lower()}`",
        f"- Qualified for bounded pilot: `{str(report.qualified_for_bounded_pilot).lower()}`",
        f"- Campaign SHA-256: `{report.campaign_sha256}`",
        f"- Freeze: `{assessment.freeze_id or 'none'}` / `{assessment.freeze_sha256 or 'none'}`",
        f"- Gate profile SHA-256: `{assessment.gate_profile_sha256}`",
        f"- Holdout suite SHA-256: `{assessment.holdout_suite_sha256}`",
        f"- Partition/exposure SHA-256: `{assessment.partition_exposure_sha256}`",
        f"- Holdout assessment: `{assessment.status.value}`",
        f"- Planned/supplied reports: {assessment.planned_reports}/{assessment.supplied_reports}",
        f"- Canonical adoption enabled: `{str(report.canonical_adoption_enabled).lower()}`",
        "",
        "## Gate results",
        "",
        f"- G0/G1 technical: {'PASS' if assessment.technical_gate_passed else 'FAIL/OPEN'}",
        "- G2 engineering quality: "
        f"{'PASS' if assessment.engineering_gate_passed else 'FAIL/OPEN'}",
        "- G3 critical semantics: "
        f"{'PASS' if assessment.critical_semantics_gate_passed else 'FAIL/OPEN'}",
    ]
    for check in assessment.metric_checks:
        values = ", ".join(
            "null" if value is None else f"{value:.6f}" for value in check.observed_values
        )
        supports = ", ".join(str(item) for item in check.supports)
        lines.append(
            f"- `{check.metric.value}` {check.operator.value} {check.threshold} "
            f"(min support {check.min_support}): {'PASS' if check.passed else 'FAIL'}; "
            f"values=[{values}], supports=[{supports}]"
        )
    if campaign is not None and experiment_reports:
        lines.extend(["", "## Frozen Holdout comparisons", ""])
        by_experiment: dict[str, list[AssertionExperimentReport]] = {}
        for item in experiment_reports:
            by_experiment.setdefault(item.experiment_id, []).append(item)
        for ref in campaign.experiments:
            role = ref.role.value
            reports_for_ref = sorted(
                by_experiment.get(ref.experiment_id, []),
                key=lambda item: item.evaluation_repetition,
            )
            lines.append(f"- `{role}` `{ref.variant_id}` / `{ref.experiment_id}`")
            if not reports_for_ref:
                lines.append("  - no evaluated report available")
                continue
            for item in reports_for_ref:
                exact = item.qualification_report.aggregate.clause_exact_match.accuracy
                assertions = item.qualification_report.aggregate.assertions.f1
                lines.append(
                    "  - repetition "
                    f"{item.evaluation_repetition}: clause_exact="
                    f"{exact.value if exact.value is not None else 'null'} "
                    f"(support {exact.denominator}), assertion_f1="
                    f"{assertions.value if assertions.value is not None else 'null'} "
                    f"(support {assertions.denominator}), calls={item.effort.calls}"
                )
        lines.extend(
            [
                "",
                "Historical V8 is not rerun or reinterpreted by Series H. Any V8 comparison "
                "remains the separately bound historical AP01 evidence and is not an independent "
                "Holdout result.",
            ]
        )
        if reference_plan is not None:
            lines.extend(
                _render_holdout_group_and_pattern_summary(
                    campaign=campaign,
                    reports=experiment_reports,
                    reference_plan=reference_plan,
                )
            )
    lines.extend(["", "## Decision boundary", ""])
    if report.qualified_for_bounded_pilot:
        lines.append(f"- Qualified scope: {report.qualification_scope}")
    elif report.release_attestation is not None:
        lines.append(f"- Human decision: `{report.release_attestation.decision.value}`")
    else:
        lines.append("- Human release decision: not present")
    lines.extend(["", "## Blockers / non-release reasons", ""])
    lines.extend(f"- `{item}`" for item in report.blockers or ("none",))
    lines.extend(
        [
            "",
            "This report does not activate canonical knowledge adoption and does not claim quality "
            "outside the frozen Holdout campaign and any explicitly named bounded pilot scope.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_holdout_group_and_pattern_summary(
    *,
    campaign: SeriesHHoldoutCampaign,
    reports: tuple[AssertionExperimentReport, ...],
    reference_plan: ReferenceCorpusPlan,
) -> list[str]:
    group_by_case = {
        (item.document_key, item.clause_id): item.source_group for item in reference_plan.holdout
    }
    finalist_id = next(
        item.experiment_id
        for item in campaign.experiments
        if item.role is SeriesHExperimentRole.FINALIST
    )
    finalist_reports = sorted(
        (item for item in reports if item.experiment_id == finalist_id),
        key=lambda item: item.evaluation_repetition,
    )
    lines = [
        "",
        "## Holdout source groups and diagnostic patterns",
        "",
        "Counts are shown instead of small-denominator percentages.",
    ]
    for report in finalist_reports:
        groups: dict[str, list[object]] = {}
        diagnostics: dict[str, int] = {}
        for case in report.qualification_report.cases:
            group = group_by_case.get(case.case_key, "unmapped")
            groups.setdefault(group, []).append(case)
            for finding in case.diagnostic_findings:
                for code in finding.codes:
                    diagnostics[code.value] = diagnostics.get(code.value, 0) + 1
        lines.append(f"- Finalist repetition {report.evaluation_repetition}:")
        for group in sorted(groups):
            cases = groups[group]
            exact = sum(case.clause_exact_match.value is True for case in cases)
            missing = sum(case.candidate_status == "missing" for case in cases)
            lines.append(
                f"  - source group `{group}`: {exact}/{len(cases)} exact cases; "
                f"missing candidates={missing}"
            )
        if diagnostics:
            rendered = ", ".join(f"{code}={diagnostics[code]}" for code in sorted(diagnostics))
            lines.append(f"  - diagnostic findings: {rendered}")
        else:
            lines.append("  - diagnostic findings: none")
    return lines


def render_ap04_handover(
    *,
    completion: SeriesHCompletionReport,
    reports: tuple[AssertionExperimentReport, ...],
) -> str:
    proposal_refs = sorted(
        {
            (
                source.source_document_key,
                source.proposal_run_id,
                source.proposal_hash,
            )
            for report in reports
            for source in report.qualification_report.proposal_sources
        }
    )
    source_packages = sorted(
        {
            binding.package_sha256
            for report in reports
            for source in report.qualification_report.proposal_sources
            for binding in source.context_source_bindings
        }
    )
    lines = [
        "# AP04 handover from AP03",
        "",
        f"- AP03 state: `{completion.state.value}`",
        f"- Campaign: `{completion.campaign_id}` / `{completion.campaign_sha256}`",
        f"- Freeze: `{completion.holdout_assessment.freeze_id or 'none'}` / "
        f"`{completion.holdout_assessment.freeze_sha256 or 'none'}`",
        f"- Gate profile: `{completion.holdout_assessment.gate_profile_sha256}`",
        f"- Holdout suite: `{completion.holdout_assessment.holdout_suite_sha256}`",
        f"- Partition/exposure: `{completion.holdout_assessment.partition_exposure_sha256}`",
        f"- Qualified bounded scope: {completion.qualification_scope or 'none'}",
        "- Canonical adoption remains disabled by AP03.",
        "- This handover starts no AP04 workflow and grants no adoption authority.",
        "",
        "## Bound proposal references",
        "",
    ]
    if proposal_refs:
        lines.extend(
            f"- `{document}` / `{run_id}` / `{digest}`"
            for document, run_id, digest in proposal_refs
        )
    else:
        lines.append("- none; no evaluated native Holdout proposal references are available")
    lines.extend(["", "## Bound source-package references", ""])
    lines.extend(f"- `{item}`" for item in source_packages or ("none",))
    lines.extend(["", "## Open blockers", ""])
    lines.extend(f"- `{item}`" for item in completion.blockers or ("none",))
    lines.append("")
    return "\n".join(lines)


def _validate_suite_against_reference_plan(
    suite: AssertionGoldenSuite, reference_plan: ReferenceCorpusPlan
) -> None:
    expected = {(item.document_key, item.clause_id) for item in reference_plan.holdout}
    actual = {(case.source_document_key, case.clause_id.value) for case in suite.cases}
    if actual != expected:
        raise ValueError("Holdout Golden suite does not exactly match the bound corpus Holdout")
    exposure = {
        (item.document_key, item.clause_id): item for item in reference_plan.exposure_register
    }
    for key in actual:
        row = exposure.get(key)
        if row is None or not row.holdout_independence_eligible or row.blockers:
            raise ValueError(f"Holdout case is not exposure-clear: {key!r}")


def _validate_manifest_for_holdout(
    manifest: AssertionExperimentManifest, suite: AssertionGoldenSuite
) -> None:
    if manifest.partition != AssertionGoldenPartition.HOLDOUT.value:
        raise ValueError("Series-H experiment manifest is not Holdout-bound")
    if (
        manifest.golden_suite_id,
        manifest.golden_suite_version,
        manifest.golden_suite_sha256,
    ) != (suite.id, suite.version, golden_suite_sha256(suite)):
        raise ValueError("Series-H manifest Golden binding differs from Holdout suite")
    manifest_cases = {(item.document_key, item.clause_id) for item in manifest.cases}
    suite_cases = {(item.source_document_key, item.clause_id.value) for item in suite.cases}
    if manifest_cases != suite_cases:
        raise ValueError("Series-H manifest cases differ from Holdout suite")
    if not manifest.bypass_cache_for_repetitions:
        raise ValueError("Series-H Holdout repetitions must bypass result cache")


def _metric_gate_result(
    gate: SeriesHMetricGate,
    reports: tuple[AssertionExperimentReport, ...],
) -> SeriesHMetricGateResult:
    values: list[float | None] = []
    supports: list[int] = []
    for report in reports:
        ratio = _metric_ratio(report, gate.metric)
        values.append(ratio.value)
        supports.append(ratio.denominator)
    passed = bool(reports)
    for value, support in zip(values, supports, strict=True):
        if value is None or support < gate.min_support:
            passed = False
            continue
        if gate.operator is SeriesHGateOperator.GREATER_OR_EQUAL:
            passed = passed and value >= gate.threshold
        else:
            passed = passed and value <= gate.threshold
    return SeriesHMetricGateResult(
        metric=gate.metric,
        operator=gate.operator,
        threshold=gate.threshold,
        min_support=gate.min_support,
        observed_values=tuple(values),
        supports=tuple(supports),
        passed=passed,
    )


def _metric_ratio(report: AssertionExperimentReport, metric: SeriesHMetric) -> RatioMetric:
    aggregate = report.qualification_report.aggregate
    if metric is SeriesHMetric.TECHNICAL_COMPLETION:
        planned = report.coverage.planned_cells
        completed = report.coverage.technically_completed_cells
        return RatioMetric(
            numerator=completed,
            denominator=planned,
            value=(completed / planned) if planned else None,
            status="ok" if planned else "not_evaluable",
        )
    candidate_clauses = RatioMetric(
        numerator=aggregate.candidate_clauses,
        denominator=aggregate.clauses,
        value=(aggregate.candidate_clauses / aggregate.clauses) if aggregate.clauses else None,
        status="ok" if aggregate.clauses else "not_evaluable",
    )
    mapping = {
        SeriesHMetric.CANDIDATE_CLAUSE_COVERAGE: candidate_clauses,
        SeriesHMetric.ENTITY_PRECISION: aggregate.entities.precision,
        SeriesHMetric.ENTITY_RECALL: aggregate.entities.recall,
        SeriesHMetric.TYPED_ENTITY_PRECISION: aggregate.typed_entities.precision,
        SeriesHMetric.TYPED_ENTITY_RECALL: aggregate.typed_entities.recall,
        SeriesHMetric.ENTITY_CLASS_ACCURACY: aggregate.entity_class_accuracy.accuracy,
        SeriesHMetric.WORK_PRODUCT_PRECISION: aggregate.work_product_precision,
        SeriesHMetric.WORK_PRODUCT_RECALL: aggregate.work_product_recall,
        SeriesHMetric.WORK_PRODUCT_CLASS_ACCURACY: aggregate.work_product_class_accuracy.accuracy,
        SeriesHMetric.REQUIRED_WORK_PRODUCT_RELATION_RECALL: (
            aggregate.required_work_product_relation_recall
        ),
        SeriesHMetric.ASSERTION_PRECISION: aggregate.assertions.precision,
        SeriesHMetric.ASSERTION_RECALL: aggregate.assertions.recall,
        SeriesHMetric.PREDICATE_ACCURACY: aggregate.predicate_accuracy.accuracy,
        SeriesHMetric.NORMATIVE_FORCE_ACCURACY: aggregate.normative_force_accuracy.accuracy,
        SeriesHMetric.EVIDENCE_INTEGRITY_VALIDITY: aggregate.evidence_integrity.validity,
        SeriesHMetric.EVIDENCE_SPAN_EXACT_MATCH: aggregate.evidence_span_exact_match.accuracy,
        SeriesHMetric.EXACT_ASSERTION_ACCURACY: aggregate.exact_assertion_accuracy.accuracy,
        SeriesHMetric.CLAUSE_EXACT_MATCH: aggregate.clause_exact_match.accuracy,
    }
    return mapping[metric]


def _critical_finding_count(
    report: AssertionExperimentReport,
    critical_codes: tuple[AssertionDiagnosticCode, ...],
) -> int:
    selected = set(critical_codes)
    return sum(
        bool(selected.intersection(finding.codes))
        for case in report.qualification_report.cases
        for finding in case.diagnostic_findings
    )


def _model_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
