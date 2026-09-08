"""Selective inference runner for the qualified applicability decision policy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    POLICY_EXPRESSION,
    POLICY_ID,
    POLICY_VERSION,
    TriState,
    confirmation_is_required,
    decide_detail_presence,
    decide_final_presence,
    rescue_is_required,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailSelection,
    ApplicabilityDetailSelectionClause,
)
from standards_atlas.application.semantic_qualification.applicability_policy_normalization import (
    normalize_detail_presence,
)
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport

ApplicabilityPolicyRole = Literal["primary", "rescue", "confirmation"]

PRIMARY_TASK_VERSION = "2.0.0"
PRIMARY_PROMPT_VERSION = "detail-structure-aware-v4"
RESCUE_TASK_VERSION = "2.0.0"
RESCUE_PROMPT_VERSION = "detail-structure-aware-v3"
CONFIRMATION_TASK_VERSION = "1.0.0"
CONFIRMATION_PROMPT_VERSION = "detail-structure-aware-v1"


class _DetailService(Protocol):
    def pending_clause_count(
        self,
        *,
        selection: ApplicabilityDetailSelection,
        existing: ApplicabilityDetailEnrichmentReport | None = None,
        fresh: bool = False,
    ) -> int: ...

    def enrich(
        self,
        *,
        selection: ApplicabilityDetailSelection,
        examples: tuple[EvaluationExample, ...],
        existing: ApplicabilityDetailEnrichmentReport | None = None,
        fresh: bool = False,
        checkpoint: Callable[[ApplicabilityDetailEnrichmentReport], None] | None = None,
    ) -> ApplicabilityDetailEnrichmentReport: ...


class ApplicabilityPolicyStageSummary(BaseModel):
    """Execution accounting for one selectively-routed detail role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ApplicabilityPolicyRole
    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_clause_count: int = Field(ge=0)
    pending_clause_count: int = Field(ge=0)
    attempted_clause_count: int = Field(ge=0)
    reused_clause_count: int = Field(ge=0)
    fresh_prediction_count: int = Field(ge=0)
    cached_prediction_count: int = Field(ge=0)
    failed_clause_count: int = Field(ge=0)
    provider_request_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_accounting(self) -> ApplicabilityPolicyStageSummary:
        if self.attempted_clause_count + self.reused_clause_count != self.selected_clause_count:
            raise ValueError("policy stage accounting must cover the complete routed selection")
        if self.pending_clause_count != self.attempted_clause_count:
            raise ValueError("policy stage pending count must match attempted clauses")
        return self


class ApplicabilityPolicyRunCase(BaseModel):
    """One consensus clause and the selective policy route taken for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str | None = None
    gate_present: bool
    detail_selected: bool
    primary_selected: bool = False
    rescue_selected: bool = False
    confirmation_selected: bool = False
    primary_present: TriState = None
    rescue_present: TriState = None
    confirmation_present: TriState = None
    detail_present: TriState = None
    final_present: TriState = None

    @model_validator(mode="after")
    def validate_route(self) -> ApplicabilityPolicyRunCase:
        if self.detail_selected != self.gate_present:
            raise ValueError("Slice 10 detail selection must match the Presence-positive gate")
        if self.primary_selected != self.detail_selected:
            raise ValueError("primary must run for every detail-selected clause")
        if not self.detail_selected:
            if self.rescue_selected or self.confirmation_selected:
                raise ValueError("non-detail clauses cannot enter rescue or confirmation")
            if any(
                value is not None
                for value in (
                    self.primary_present,
                    self.rescue_present,
                    self.confirmation_present,
                    self.detail_present,
                )
            ):
                raise ValueError("non-detail clauses must not contain detail decisions")
        else:
            if self.rescue_selected != rescue_is_required(self.primary_present):
                raise ValueError("rescue routing does not match the policy")
            expected_confirmation = False
            if self.rescue_selected:
                expected_confirmation = confirmation_is_required(
                    primary=self.primary_present,
                    rescue=self.rescue_present,
                )
            if self.confirmation_selected != expected_confirmation:
                raise ValueError("confirmation routing does not match the policy")
            expected_detail = decide_detail_presence(
                primary=self.primary_present,
                rescue=self.rescue_present,
                confirmation=self.confirmation_present,
            )
            if self.detail_present != expected_detail:
                raise ValueError("detail_present does not match routed policy decisions")
        expected_final = decide_final_presence(
            gate_present=self.gate_present,
            detail_present=self.detail_present,
        )
        if self.final_present != expected_final:
            raise ValueError("final_present does not match gate and detail policy")
        return self


class ApplicabilityPolicyRunReport(BaseModel):
    """Persistable result of one selective policy inference run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    task: Literal["applicability-policy-run"] = "applicability-policy-run"
    policy_id: Literal[POLICY_ID] = POLICY_ID
    policy_version: Literal[POLICY_VERSION] = POLICY_VERSION
    expression: Literal[POLICY_EXPRESSION] = POLICY_EXPRESSION
    generated_at: datetime
    source_matrix_id: str = Field(min_length=1)
    source_corpus_id: str = Field(min_length=1)
    source_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_consensus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_clause_count: int = Field(ge=0)
    selected_clause_count: int = Field(ge=0)
    final_positive_count: int = Field(ge=0)
    final_negative_count: int = Field(ge=0)
    final_unknown_count: int = Field(ge=0)
    stages: tuple[ApplicabilityPolicyStageSummary, ...]
    cases: tuple[ApplicabilityPolicyRunCase, ...]

    @model_validator(mode="after")
    def validate_report(self) -> ApplicabilityPolicyRunReport:
        if tuple(stage.role for stage in self.stages) != (
            "primary",
            "rescue",
            "confirmation",
        ):
            raise ValueError("policy stages must be primary, rescue, confirmation")
        if self.consensus_clause_count != len(self.cases):
            raise ValueError("consensus_clause_count must match policy run cases")
        if self.selected_clause_count != sum(case.detail_selected for case in self.cases):
            raise ValueError("selected_clause_count must match policy run cases")
        positives = sum(case.final_present is True for case in self.cases)
        negatives = sum(case.final_present is False for case in self.cases)
        unknown = sum(case.final_present is None for case in self.cases)
        if (positives, negatives, unknown) != (
            self.final_positive_count,
            self.final_negative_count,
            self.final_unknown_count,
        ):
            raise ValueError("final policy counts do not match cases")
        return self


@dataclass(frozen=True)
class ApplicabilityPolicyRunResult:
    """Runner result plus role artifacts required by the CLI persistence layer."""

    report: ApplicabilityPolicyRunReport
    selections: Mapping[ApplicabilityPolicyRole, ApplicabilityDetailSelection]
    reports: Mapping[ApplicabilityPolicyRole, ApplicabilityDetailEnrichmentReport]


PolicyCheckpoint = Callable[
    [ApplicabilityPolicyRole, ApplicabilityDetailSelection, ApplicabilityDetailEnrichmentReport],
    None,
]


def applicability_policy_inference_required(
    *,
    selection: ApplicabilityDetailSelection,
    primary_service: _DetailService,
    rescue_service: _DetailService,
    confirmation_service: _DetailService,
    existing_primary: ApplicabilityDetailEnrichmentReport | None = None,
    existing_rescue: ApplicabilityDetailEnrichmentReport | None = None,
    existing_confirmation: ApplicabilityDetailEnrichmentReport | None = None,
) -> bool:
    """Return whether the current persisted selective run needs any provider inference."""

    primary_selection = _role_selection(
        selection,
        clauses=selection.clauses,
        task_version=PRIMARY_TASK_VERSION,
    )
    if primary_service.pending_clause_count(
        selection=primary_selection,
        existing=existing_primary,
        fresh=False,
    ):
        return True
    if not primary_selection.clauses:
        return False
    if existing_primary is None:
        raise ValueError("complete primary policy stage is missing persisted results")
    primary_by_coordinate = _normalized_results(
        existing_primary,
        primary_selection,
        role="primary",
    )

    rescue_clauses = tuple(
        item
        for item in selection.clauses
        if rescue_is_required(primary_by_coordinate[(item.document_key, item.clause_id)])
    )
    rescue_selection = _role_selection(
        selection,
        clauses=rescue_clauses,
        task_version=RESCUE_TASK_VERSION,
    )
    if rescue_service.pending_clause_count(
        selection=rescue_selection,
        existing=existing_rescue,
        fresh=False,
    ):
        return True
    if not rescue_selection.clauses:
        return False
    if existing_rescue is None:
        raise ValueError("complete rescue policy stage is missing persisted results")
    rescue_by_coordinate = _normalized_results(
        existing_rescue,
        rescue_selection,
        role="rescue",
    )

    confirmation_clauses = tuple(
        item
        for item in rescue_selection.clauses
        if confirmation_is_required(
            primary=primary_by_coordinate[(item.document_key, item.clause_id)],
            rescue=rescue_by_coordinate[(item.document_key, item.clause_id)],
        )
    )
    confirmation_selection = _role_selection(
        selection,
        clauses=confirmation_clauses,
        task_version=CONFIRMATION_TASK_VERSION,
    )
    return bool(
        confirmation_service.pending_clause_count(
            selection=confirmation_selection,
            existing=existing_confirmation,
            fresh=False,
        )
    )


def run_applicability_policy(
    *,
    selection: ApplicabilityDetailSelection,
    consensus: ConsensusReport,
    examples: tuple[EvaluationExample, ...],
    primary_service: _DetailService,
    rescue_service: _DetailService,
    confirmation_service: _DetailService,
    existing_primary: ApplicabilityDetailEnrichmentReport | None = None,
    existing_rescue: ApplicabilityDetailEnrichmentReport | None = None,
    existing_confirmation: ApplicabilityDetailEnrichmentReport | None = None,
    checkpoint: PolicyCheckpoint | None = None,
    request_count: Callable[[], int] | None = None,
) -> ApplicabilityPolicyRunResult:
    """Run only the detail roles that can still affect D4 OR (D3 AND D1)."""

    selected_coordinates = {(item.document_key, item.clause_id) for item in selection.clauses}
    expected_coordinates = {
        (item.document_key, item.clause_id)
        for item in consensus.clauses
        if item.applicability_present
    }
    if selected_coordinates != expected_coordinates:
        raise ValueError("policy input selection does not match Presence-positive consensus")
    if (
        consensus.matrix_id != selection.source_matrix_id
        or consensus.corpus_id != selection.source_corpus_id
    ):
        raise ValueError("policy input selection provenance differs from consensus")

    primary_selection = _role_selection(
        selection,
        clauses=selection.clauses,
        task_version=PRIMARY_TASK_VERSION,
    )
    primary_report, primary_summary = _run_stage(
        role="primary",
        selection=primary_selection,
        service=primary_service,
        examples=examples,
        existing=existing_primary,
        checkpoint=checkpoint,
        request_count=request_count,
    )
    primary_by_coordinate = _normalized_results(primary_report, primary_selection, role="primary")

    rescue_clauses = tuple(
        item
        for item in selection.clauses
        if rescue_is_required(primary_by_coordinate[(item.document_key, item.clause_id)])
    )
    rescue_selection = _role_selection(
        selection,
        clauses=rescue_clauses,
        task_version=RESCUE_TASK_VERSION,
    )
    rescue_report, rescue_summary = _run_stage(
        role="rescue",
        selection=rescue_selection,
        service=rescue_service,
        examples=examples,
        existing=existing_rescue,
        checkpoint=checkpoint,
        request_count=request_count,
    )
    rescue_by_coordinate = _normalized_results(rescue_report, rescue_selection, role="rescue")

    confirmation_clauses: list[ApplicabilityDetailSelectionClause] = []
    for item in rescue_selection.clauses:
        coordinate = (item.document_key, item.clause_id)
        if confirmation_is_required(
            primary=primary_by_coordinate[coordinate],
            rescue=rescue_by_coordinate[coordinate],
        ):
            confirmation_clauses.append(item)
    confirmation_selection = _role_selection(
        selection,
        clauses=tuple(confirmation_clauses),
        task_version=CONFIRMATION_TASK_VERSION,
    )
    confirmation_report, confirmation_summary = _run_stage(
        role="confirmation",
        selection=confirmation_selection,
        service=confirmation_service,
        examples=examples,
        existing=existing_confirmation,
        checkpoint=checkpoint,
        request_count=request_count,
    )
    confirmation_by_coordinate = _normalized_results(
        confirmation_report,
        confirmation_selection,
        role="confirmation",
    )

    rescue_coordinates = set(rescue_by_coordinate)
    confirmation_coordinates = set(confirmation_by_coordinate)
    cases: list[ApplicabilityPolicyRunCase] = []
    for consensus_clause in consensus.clauses:
        coordinate = (consensus_clause.document_key, consensus_clause.clause_id)
        selected = coordinate in selected_coordinates
        primary_present = None
        rescue_present = None
        confirmation_present = None
        detail_present = None
        if selected:
            primary_present = primary_by_coordinate[coordinate]
            if coordinate in rescue_coordinates:
                rescue_present = rescue_by_coordinate[coordinate]
            if coordinate in confirmation_coordinates:
                confirmation_present = confirmation_by_coordinate[coordinate]
            detail_present = decide_detail_presence(
                primary=primary_present,
                rescue=rescue_present,
                confirmation=confirmation_present,
            )
        final_present = decide_final_presence(
            gate_present=consensus_clause.applicability_present,
            detail_present=detail_present,
        )
        cases.append(
            ApplicabilityPolicyRunCase(
                document_key=consensus_clause.document_key,
                clause_id=consensus_clause.clause_id,
                reference=consensus_clause.reference,
                gate_present=consensus_clause.applicability_present,
                detail_selected=selected,
                primary_selected=selected,
                rescue_selected=coordinate in rescue_coordinates,
                confirmation_selected=coordinate in confirmation_coordinates,
                primary_present=primary_present,
                rescue_present=rescue_present,
                confirmation_present=confirmation_present,
                detail_present=detail_present,
                final_present=final_present,
            )
        )

    stage_models = {
        (primary_report.model_id, primary_report.model_ref),
        (rescue_report.model_id, rescue_report.model_ref),
        (confirmation_report.model_id, confirmation_report.model_ref),
    }
    if len(stage_models) != 1:
        raise ValueError("policy stages must use the same detail model")

    report = ApplicabilityPolicyRunReport(
        generated_at=datetime.now(UTC),
        source_matrix_id=consensus.matrix_id,
        source_corpus_id=consensus.corpus_id,
        source_selection_sha256=selection.fingerprint,
        source_consensus_sha256=selection.source_consensus_sha256,
        consensus_clause_count=len(consensus.clauses),
        selected_clause_count=selection.selected_clause_count,
        final_positive_count=sum(case.final_present is True for case in cases),
        final_negative_count=sum(case.final_present is False for case in cases),
        final_unknown_count=sum(case.final_present is None for case in cases),
        stages=(primary_summary, rescue_summary, confirmation_summary),
        cases=tuple(cases),
    )
    return ApplicabilityPolicyRunResult(
        report=report,
        selections={
            "primary": primary_selection,
            "rescue": rescue_selection,
            "confirmation": confirmation_selection,
        },
        reports={
            "primary": primary_report,
            "rescue": rescue_report,
            "confirmation": confirmation_report,
        },
    )


def _run_stage(
    *,
    role: ApplicabilityPolicyRole,
    selection: ApplicabilityDetailSelection,
    service: _DetailService,
    examples: tuple[EvaluationExample, ...],
    existing: ApplicabilityDetailEnrichmentReport | None,
    checkpoint: PolicyCheckpoint | None,
    request_count: Callable[[], int] | None,
) -> tuple[ApplicabilityDetailEnrichmentReport, ApplicabilityPolicyStageSummary]:
    pending = service.pending_clause_count(selection=selection, existing=existing, fresh=False)
    before = request_count() if request_count is not None else None

    def role_checkpoint(report: ApplicabilityDetailEnrichmentReport) -> None:
        if checkpoint is not None:
            checkpoint(role, selection, report)

    report = service.enrich(
        selection=selection,
        examples=examples,
        existing=existing,
        fresh=False,
        checkpoint=role_checkpoint,
    )
    after = request_count() if request_count is not None else None
    if report.processed_clause_count != selection.selected_clause_count:
        raise ValueError(f"{role} policy stage did not complete its routed selection")
    expected_contract = {
        "primary": (PRIMARY_TASK_VERSION, PRIMARY_PROMPT_VERSION),
        "rescue": (RESCUE_TASK_VERSION, RESCUE_PROMPT_VERSION),
        "confirmation": (CONFIRMATION_TASK_VERSION, CONFIRMATION_PROMPT_VERSION),
    }[role]
    if (report.task_version, report.prompt_version) != expected_contract:
        raise ValueError(f"{role} policy stage uses the wrong task/prompt contract")
    provider_requests = None if before is None or after is None else after - before
    stats = report.run_statistics
    summary = ApplicabilityPolicyStageSummary(
        role=role,
        task_version=report.task_version,
        prompt_version=report.prompt_version,
        model_id=report.model_id,
        model_ref=report.model_ref,
        selection_sha256=selection.fingerprint,
        selected_clause_count=selection.selected_clause_count,
        pending_clause_count=pending,
        attempted_clause_count=stats.attempted_clause_count,
        reused_clause_count=stats.reused_clause_count,
        fresh_prediction_count=stats.fresh_prediction_count,
        cached_prediction_count=stats.cached_prediction_count,
        failed_clause_count=report.failed_clause_count,
        provider_request_count=provider_requests,
    )
    return report, summary


def _role_selection(
    source: ApplicabilityDetailSelection,
    *,
    clauses: tuple[ApplicabilityDetailSelectionClause, ...],
    task_version: str,
) -> ApplicabilityDetailSelection:
    data = source.model_dump(mode="python")
    data["task_version"] = task_version
    data["selected_clause_count"] = len(clauses)
    data["clauses"] = clauses
    return ApplicabilityDetailSelection.model_validate(data)


def _normalized_results(
    report: ApplicabilityDetailEnrichmentReport,
    selection: ApplicabilityDetailSelection,
    *,
    role: ApplicabilityPolicyRole,
) -> dict[tuple[str, str], TriState]:
    results = {(item.document_key, item.clause_id): item for item in report.clauses}
    expected = {(item.document_key, item.clause_id): item for item in selection.clauses}
    if set(results) != set(expected):
        raise ValueError(f"{role} policy stage does not cover the exact routed selection")
    normalized: dict[tuple[str, str], TriState] = {}
    for coordinate, item in results.items():
        if item.content_hash != expected[coordinate].content_hash:
            raise ValueError(f"{role} policy stage content hash differs from selection")
        normalized[coordinate] = normalize_detail_presence(item)
    return normalized
