"""Archive validation for completed applicability decision policy runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    POLICY_EXPRESSION,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailSelection,
)
from standards_atlas.application.semantic_qualification.applicability_policy_evaluation import (
    ApplicabilityPolicyEvaluationReport,
)
from standards_atlas.application.semantic_qualification.applicability_policy_qualification import (
    ApplicabilityDecisionPolicyConfig,
    ApplicabilityPolicyQualificationMode,
    ApplicabilityPolicyRunState,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    ApplicabilityPolicyRunReport,
)


class ApplicabilityPolicyQualitySummary(BaseModel):
    """Golden-corpus quality status kept separate from technical completion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    golden_corpus_id: str = Field(min_length=1)
    golden_corpus_version: str = Field(min_length=1)
    published_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    missing_cases: int = Field(ge=0)
    unknown_cases: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    max_false_positive: int = Field(ge=0)
    max_false_negative: int = Field(ge=0)
    passed: bool


class ApplicabilityPolicyArchiveSummary(BaseModel):
    """Validated archive metadata for one selective policy run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task: Literal["applicability-policy-run"] = "applicability-policy-run"
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    source_matrix_id: str = Field(min_length=1)
    source_corpus_id: str = Field(min_length=1)
    source_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_consensus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualification_mode: ApplicabilityPolicyQualificationMode
    fresh_requested: bool
    cache_disabled: bool
    required_fresh_repetitions: int = Field(ge=1)
    technical_complete: bool
    consensus_clause_count: int = Field(ge=0)
    selected_clause_count: int = Field(ge=0)
    final_positive_count: int = Field(ge=0)
    final_negative_count: int = Field(ge=0)
    final_unknown_count: int = Field(ge=0)
    stages: tuple[dict[str, object], ...]
    quality_evaluation: ApplicabilityPolicyQualitySummary | None = None


def validate_completed_applicability_policy(
    *,
    expected_selection: ApplicabilityDetailSelection,
    run_report: ApplicabilityPolicyRunReport,
    state: ApplicabilityPolicyRunState,
    role_selections: dict[str, ApplicabilityDetailSelection],
    role_reports: dict[str, ApplicabilityDetailEnrichmentReport],
    config: ApplicabilityDecisionPolicyConfig,
    model_id: str,
    model_ref: str,
    evaluation: ApplicabilityPolicyEvaluationReport | None,
) -> ApplicabilityPolicyArchiveSummary:
    """Validate persisted selective policy artifacts before immutable archiving."""

    if not config.enabled:
        raise ValueError("applicability decision policy is disabled")
    if config.model != model_id:
        raise ValueError("applicability policy archive model differs from manifest")
    if state.model_id != model_id or state.model_ref != model_ref:
        raise ValueError("applicability policy state model differs from manifest")
    if state.source_selection_sha256 != expected_selection.fingerprint:
        raise ValueError("applicability policy state belongs to a different selection")
    if (
        run_report.policy_id != config.policy_id
        or run_report.policy_version != config.policy_version
    ):
        raise ValueError("applicability policy report differs from manifest policy contract")
    if run_report.expression != POLICY_EXPRESSION:
        raise ValueError("applicability policy report uses an unexpected expression")
    if run_report.source_selection_sha256 != expected_selection.fingerprint:
        raise ValueError("applicability policy report belongs to a different selection")
    if run_report.qualification_mode != state.qualification_mode:
        raise ValueError("applicability policy report and state disagree on qualification mode")
    if run_report.fresh_requested != state.fresh_requested:
        raise ValueError("applicability policy report and state disagree on freshness")

    configured_roles = {
        "primary": config.primary,
        "rescue": config.rescue,
        "confirmation": config.confirmation,
    }
    stage_by_role = {stage.role: stage for stage in run_report.stages}
    if set(stage_by_role) != set(configured_roles):
        raise ValueError("applicability policy report has incomplete role metadata")

    for role, role_config in configured_roles.items():
        selection = role_selections.get(role)
        report = role_reports.get(role)
        if selection is None or report is None:
            raise ValueError(f"applicability policy {role} artifacts are incomplete")
        stage = stage_by_role[role]
        if selection.fingerprint != stage.selection_sha256:
            raise ValueError(f"applicability policy {role} selection hash mismatch")
        if report.selection_sha256 != selection.fingerprint:
            raise ValueError(f"applicability policy {role} report selection mismatch")
        if (selection.task_version, report.task_version, report.prompt_version) != (
            role_config.task_version,
            role_config.task_version,
            role_config.prompt_version,
        ):
            raise ValueError(f"applicability policy {role} task/prompt contract mismatch")
        if report.model_id != model_id or report.model_ref != model_ref:
            raise ValueError(f"applicability policy {role} model mismatch")
        if report.processed_clause_count != selection.selected_clause_count:
            raise ValueError(f"applicability policy {role} report is incomplete")
        if stage.selected_clause_count != selection.selected_clause_count:
            raise ValueError(f"applicability policy {role} stage count mismatch")

    quality = None
    if config.golden_corpus is not None:
        if evaluation is None:
            raise ValueError("applicability policy golden evaluation is missing")
        if (
            evaluation.policy_id != config.policy_id
            or evaluation.policy_version != config.policy_version
            or evaluation.max_false_positive != config.max_false_positive
            or evaluation.max_false_negative != config.max_false_negative
        ):
            raise ValueError("applicability policy golden evaluation uses the wrong contract")
        quality = ApplicabilityPolicyQualitySummary(
            golden_corpus_id=evaluation.golden_corpus_id,
            golden_corpus_version=evaluation.golden_corpus_version,
            published_cases=evaluation.published_cases,
            matched_cases=evaluation.matched_cases,
            missing_cases=len(evaluation.missing_cases),
            unknown_cases=len(evaluation.unknown_cases),
            false_positive=evaluation.metrics.false_positive,
            false_negative=evaluation.metrics.false_negative,
            max_false_positive=evaluation.max_false_positive,
            max_false_negative=evaluation.max_false_negative,
            passed=evaluation.passed,
        )
    elif evaluation is not None:
        raise ValueError("unexpected applicability policy golden evaluation")

    technical_complete = run_report.final_unknown_count == 0
    return ApplicabilityPolicyArchiveSummary(
        policy_id=run_report.policy_id,
        policy_version=run_report.policy_version,
        expression=run_report.expression,
        model_id=model_id,
        model_ref=model_ref,
        source_matrix_id=run_report.source_matrix_id,
        source_corpus_id=run_report.source_corpus_id,
        source_selection_sha256=run_report.source_selection_sha256,
        source_consensus_sha256=run_report.source_consensus_sha256,
        qualification_mode=run_report.qualification_mode,
        fresh_requested=run_report.fresh_requested,
        cache_disabled=state.cache_disabled,
        required_fresh_repetitions=config.required_fresh_repetitions,
        technical_complete=technical_complete,
        consensus_clause_count=run_report.consensus_clause_count,
        selected_clause_count=run_report.selected_clause_count,
        final_positive_count=run_report.final_positive_count,
        final_negative_count=run_report.final_negative_count,
        final_unknown_count=run_report.final_unknown_count,
        stages=tuple(stage.model_dump(mode="json") for stage in run_report.stages),
        quality_evaluation=quality,
    )
