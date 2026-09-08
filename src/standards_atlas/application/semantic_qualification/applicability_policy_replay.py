"""Offline replay for the deterministic applicability decision policy."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_decision_policy import (
    POLICY_ID,
    POLICY_VERSION,
    TriState,
    decide_detail_presence,
    decide_final_presence,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailSelection,
    load_applicability_detail_report,
)
from standards_atlas.application.semantic_qualification.applicability_end_to_end import (
    load_applicability_end_to_end_artifacts,
)
from standards_atlas.domain.model import ApplicabilityTarget

PRIMARY_PROMPT = "detail-structure-aware-v4"
RESCUE_PROMPT = "detail-structure-aware-v3"
CONFIRMATION_PROMPT = "detail-structure-aware-v1"
PRIMARY_TASK_VERSION = "2.0.0"
RESCUE_TASK_VERSION = "2.0.0"
CONFIRMATION_TASK_VERSION = "1.0.0"


class ApplicabilityPolicyRoleSource(BaseModel):
    """Immutable provenance for one detail role used by replay."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["primary", "rescue", "confirmation"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    selected_clause_count: int = Field(ge=0)


class ApplicabilityPolicyReplayCase(BaseModel):
    """One consensus clause and its deterministic policy projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str | None = None
    gate_present: bool
    detail_selected: bool
    primary_present: TriState = None
    rescue_present: TriState = None
    confirmation_present: TriState = None
    detail_present: TriState = None
    final_present: TriState = None

    @model_validator(mode="after")
    def validate_projection(self) -> ApplicabilityPolicyReplayCase:
        if self.detail_selected != self.gate_present:
            raise ValueError(
                "Slice 9 detail selection must exactly match the Presence-positive gate"
            )
        expected_detail = None
        if self.detail_selected:
            expected_detail = decide_detail_presence(
                primary=self.primary_present,
                rescue=self.rescue_present,
                confirmation=self.confirmation_present,
            )
        if self.detail_present != expected_detail:
            raise ValueError("detail_present does not match the configured decision policy")
        expected_final = decide_final_presence(
            gate_present=self.gate_present,
            detail_present=self.detail_present,
        )
        if self.final_present != expected_final:
            raise ValueError("final_present does not match the Presence gate and detail policy")
        return self


class ApplicabilityPolicyReplayReport(BaseModel):
    """Complete offline replay over the archived final Presence consensus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    policy_id: Literal[POLICY_ID] = POLICY_ID
    policy_version: Literal[POLICY_VERSION] = POLICY_VERSION
    expression: Literal["D4 OR (D3 AND D1)"] = "D4 OR (D3 AND D1)"
    generated_at: datetime
    source_run: str = Field(min_length=1)
    source_run_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_matrix_id: str = Field(min_length=1)
    source_corpus_id: str = Field(min_length=1)
    source_selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consensus_clause_count: int = Field(ge=0)
    selected_clause_count: int = Field(ge=0)
    final_positive_count: int = Field(ge=0)
    final_negative_count: int = Field(ge=0)
    final_unknown_count: int = Field(ge=0)
    roles: tuple[ApplicabilityPolicyRoleSource, ...]
    cases: tuple[ApplicabilityPolicyReplayCase, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> ApplicabilityPolicyReplayReport:
        if self.consensus_clause_count != len(self.cases):
            raise ValueError("consensus_clause_count must match replay cases")
        if self.selected_clause_count != sum(case.detail_selected for case in self.cases):
            raise ValueError("selected_clause_count must match replay cases")
        positives = sum(case.final_present is True for case in self.cases)
        negatives = sum(case.final_present is False for case in self.cases)
        unknown = sum(case.final_present is None for case in self.cases)
        if (positives, negatives, unknown) != (
            self.final_positive_count,
            self.final_negative_count,
            self.final_unknown_count,
        ):
            raise ValueError("final decision counts do not match replay cases")
        if positives + negatives + unknown != len(self.cases):
            raise ValueError("final decision counts do not balance")
        if tuple(role.role for role in self.roles) != ("primary", "rescue", "confirmation"):
            raise ValueError("policy replay roles must be primary, rescue, confirmation")
        return self

    @classmethod
    def load(cls, path: Path) -> ApplicabilityPolicyReplayReport:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def replay_applicability_policy(
    *,
    run_archive: Path,
    primary_report_path: Path,
    rescue_report_path: Path,
    confirmation_report_path: Path,
) -> ApplicabilityPolicyReplayReport:
    """Replay the qualified policy from persisted artifacts without inference."""

    consensus, selection, _baseline_detail = load_applicability_end_to_end_artifacts(run_archive)
    primary = load_applicability_detail_report(primary_report_path)
    rescue = load_applicability_detail_report(rescue_report_path)
    confirmation = load_applicability_detail_report(confirmation_report_path)

    _validate_role_report(
        primary,
        selection=selection,
        role="primary",
        task_version=PRIMARY_TASK_VERSION,
        prompt_version=PRIMARY_PROMPT,
    )
    _validate_role_report(
        rescue,
        selection=selection,
        role="rescue",
        task_version=RESCUE_TASK_VERSION,
        prompt_version=RESCUE_PROMPT,
    )
    _validate_role_report(
        confirmation,
        selection=selection,
        role="confirmation",
        task_version=CONFIRMATION_TASK_VERSION,
        prompt_version=CONFIRMATION_PROMPT,
    )
    model_ids = {primary.model_id, rescue.model_id, confirmation.model_id}
    model_refs = {primary.model_ref, rescue.model_ref, confirmation.model_ref}
    if len(model_ids) != 1 or len(model_refs) != 1:
        raise ValueError("Slice 9 policy roles must use the same detail model")

    selected_coordinates = {(item.document_key, item.clause_id) for item in selection.clauses}
    expected_coordinates = {
        (item.document_key, item.clause_id)
        for item in consensus.clauses
        if item.applicability_present
    }
    if selected_coordinates != expected_coordinates:
        raise ValueError("detail selection does not match the final Presence-positive consensus")

    primary_by_coordinate = _role_results(primary, selection=selection, role="primary")
    rescue_by_coordinate = _role_results(rescue, selection=selection, role="rescue")
    confirmation_by_coordinate = _role_results(
        confirmation,
        selection=selection,
        role="confirmation",
    )

    cases: list[ApplicabilityPolicyReplayCase] = []
    for consensus_clause in consensus.clauses:
        coordinate = (consensus_clause.document_key, consensus_clause.clause_id)
        selected = coordinate in selected_coordinates
        primary_present = None
        rescue_present = None
        confirmation_present = None
        detail_present = None
        if selected:
            primary_present = normalize_detail_presence(primary_by_coordinate[coordinate])
            rescue_present = normalize_detail_presence(rescue_by_coordinate[coordinate])
            confirmation_present = normalize_detail_presence(confirmation_by_coordinate[coordinate])
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
            ApplicabilityPolicyReplayCase(
                document_key=consensus_clause.document_key,
                clause_id=consensus_clause.clause_id,
                reference=consensus_clause.reference,
                gate_present=consensus_clause.applicability_present,
                detail_selected=selected,
                primary_present=primary_present,
                rescue_present=rescue_present,
                confirmation_present=confirmation_present,
                detail_present=detail_present,
                final_present=final_present,
            )
        )

    roles = (
        _role_source("primary", primary_report_path, primary),
        _role_source("rescue", rescue_report_path, rescue),
        _role_source("confirmation", confirmation_report_path, confirmation),
    )
    return ApplicabilityPolicyReplayReport(
        generated_at=datetime.now(UTC),
        source_run=run_archive.name,
        source_run_sha256=_file_sha256(run_archive),
        source_matrix_id=consensus.matrix_id,
        source_corpus_id=consensus.corpus_id,
        source_selection_sha256=selection.fingerprint,
        consensus_clause_count=len(consensus.clauses),
        selected_clause_count=selection.selected_clause_count,
        final_positive_count=sum(case.final_present is True for case in cases),
        final_negative_count=sum(case.final_present is False for case in cases),
        final_unknown_count=sum(case.final_present is None for case in cases),
        roles=roles,
        cases=tuple(cases),
    )


def normalize_detail_presence(result: ApplicabilityDetailClauseResult) -> TriState:
    """Normalize persisted task-v1/task-v2 detail results into Presence tri-state."""

    if result.outcome is ApplicabilityDetailOutcome.FAILED:
        return None
    generator = result.generator
    if generator is None:
        raise ValueError("non-failed detail result is missing generator provenance")
    if generator.task_version == CONFIRMATION_TASK_VERSION:
        if result.contains_clause_or_requirement_applicability is not None:
            raise ValueError(
                "task-v1 detail result unexpectedly carries the task-v2 Presence field"
            )
        return result.applicability_target is ApplicabilityTarget.CLAUSE_OR_REQUIREMENT
    if generator.task_version == PRIMARY_TASK_VERSION:
        if result.contains_clause_or_requirement_applicability is None:
            raise ValueError("task-v2 detail result is missing clause applicability Presence")
        return result.contains_clause_or_requirement_applicability
    raise ValueError(f"unsupported applicability detail task version: {generator.task_version}")


def _validate_role_report(
    report: ApplicabilityDetailEnrichmentReport,
    *,
    selection: ApplicabilityDetailSelection,
    role: str,
    task_version: str,
    prompt_version: str,
) -> None:
    if report.task_version != task_version:
        raise ValueError(f"{role} detail report task version must be {task_version}")
    if report.prompt_version != prompt_version:
        raise ValueError(f"{role} detail report prompt version must be {prompt_version}")
    if report.selection_sha256 != selection.fingerprint:
        raise ValueError(f"{role} detail report belongs to a different detail selection")
    if report.selected_clause_count != selection.selected_clause_count:
        raise ValueError(f"{role} detail report selection count differs from selection")
    if report.processed_clause_count != report.selected_clause_count:
        raise ValueError(f"{role} detail report is incomplete")


def _role_results(
    report: ApplicabilityDetailEnrichmentReport,
    *,
    selection: ApplicabilityDetailSelection,
    role: str,
) -> dict[tuple[str, str], ApplicabilityDetailClauseResult]:
    results = {(item.document_key, item.clause_id): item for item in report.clauses}
    if len(results) != len(report.clauses):
        raise ValueError(f"{role} detail result coordinates must be unique")
    selected = {(item.document_key, item.clause_id): item for item in selection.clauses}
    if set(results) != set(selected):
        raise ValueError(f"{role} detail report does not cover the exact detail selection")
    for coordinate, result in results.items():
        expected = selected[coordinate]
        if result.content_hash != expected.content_hash:
            raise ValueError(f"{role} detail result content hash differs from the selection")
    return results


def _role_source(
    role: Literal["primary", "rescue", "confirmation"],
    path: Path,
    report: ApplicabilityDetailEnrichmentReport,
) -> ApplicabilityPolicyRoleSource:
    return ApplicabilityPolicyRoleSource(
        role=role,
        path=str(path),
        sha256=_file_sha256(path),
        task_version=report.task_version,
        prompt_version=report.prompt_version,
        model_id=report.model_id,
        model_ref=report.model_ref,
        selected_clause_count=report.selected_clause_count,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
