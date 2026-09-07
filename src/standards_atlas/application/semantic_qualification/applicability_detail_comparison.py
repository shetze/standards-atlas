"""Offline A/B comparison for applicability-detail contract experiments."""

from __future__ import annotations

import hashlib
from collections import Counter
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
    ApplicabilityModelMetrics,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    APPLICABILITY_DETAIL_REPORT_FILENAME,
    APPLICABILITY_DETAIL_SELECTION_FILENAME,
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailEnrichmentReport,
    ApplicabilityDetailOutcome,
    ApplicabilityDetailSelection,
    load_applicability_detail_report,
    load_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_end_to_end import (
    ApplicabilityEndToEndRegressionReport,
    evaluate_applicability_end_to_end_from_artifacts,
    load_applicability_end_to_end_artifacts,
    validate_applicability_detail_provenance,
)
from standards_atlas.domain.model import ApplicabilityTarget, OtherApplicabilityTarget


class ApplicabilityComparisonState(StrEnum):
    """Golden-set correctness state for one resolved detail candidate."""

    CORRECT = "correct"
    WRONG = "wrong"
    UNRESOLVED = "unresolved"


class ApplicabilityDetailDecisionClass(StrEnum):
    """Contract-independent detail gate decision used for A/B transitions."""

    CLAUSE_OR_REQUIREMENT = "clause_or_requirement"
    NON_CLAUSE = "non_clause"
    FAILED = "failed"


class ApplicabilityCandidateTargetPattern(StrEnum):
    """Contract-neutral diagnostic projection of one candidate detail output."""

    CLAUSE_ONLY = "clause_only"
    MIXED_TARGET = "mixed_target"
    NON_CLAUSE_TARGET = "non_clause_target"
    NON_CLAUSE_UNSPECIFIED = "non_clause_unspecified"
    FAILED = "failed"


class ApplicabilityMetricDelta(BaseModel):
    """Baseline/candidate end-to-end metrics and signed candidate-minus-baseline deltas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: ApplicabilityModelMetrics
    candidate: ApplicabilityModelMetrics
    true_positive_delta: int
    false_positive_delta: int
    true_negative_delta: int
    false_negative_delta: int
    accuracy_delta: float
    precision_delta: float
    recall_delta: float
    specificity_delta: float
    balanced_accuracy_delta: float
    f1_delta: float


class ApplicabilityDetailComparisonCase(BaseModel):
    """One exact-selection clause compared across baseline and candidate detail contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)
    reference: str | None = None
    expected_present: bool | None = None
    baseline_outcome: ApplicabilityDetailOutcome
    candidate_outcome: ApplicabilityDetailOutcome
    baseline_applicability_target: ApplicabilityTarget | None = None
    candidate_contains_clause_or_requirement_applicability: bool | None = None
    candidate_other_applicability_targets: tuple[OtherApplicabilityTarget, ...] = ()
    baseline_final_present: bool | None = None
    candidate_final_present: bool | None = None
    baseline_state: ApplicabilityComparisonState | None = None
    candidate_state: ApplicabilityComparisonState | None = None
    correctness_transition: str | None = None
    decision_transition: str = Field(min_length=1)
    candidate_target_pattern: ApplicabilityCandidateTargetPattern

    @model_validator(mode="after")
    def validate_golden_state(self) -> ApplicabilityDetailComparisonCase:
        if self.expected_present is None:
            if self.baseline_state is not None or self.candidate_state is not None:
                raise ValueError("non-golden comparison cases must not contain correctness states")
            if self.correctness_transition is not None:
                raise ValueError("non-golden comparison cases have no correctness transition")
        else:
            if self.baseline_state is None or self.candidate_state is None:
                raise ValueError("golden comparison cases require baseline and candidate states")
            expected_transition = f"{self.baseline_state.value}_to_{self.candidate_state.value}"
            if self.correctness_transition != expected_transition:
                raise ValueError("golden correctness transition differs from case states")
        return self


class ApplicabilityDetailComparisonReport(BaseModel):
    """Reproducible detail A/B report over one immutable Presence-positive selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.1"
    golden_corpus_id: str = Field(min_length=1)
    golden_corpus_version: str = Field(min_length=1)
    source_matrix_id: str = Field(min_length=1)
    source_corpus_id: str = Field(min_length=1)
    baseline_archive: str = Field(min_length=1)
    baseline_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_clause_count: int = Field(ge=0)
    golden_candidate_count: int = Field(ge=0)
    baseline_task_version: str = Field(min_length=1)
    baseline_prompt_version: str = Field(min_length=1)
    baseline_model_id: str = Field(min_length=1)
    baseline_model_ref: str = Field(min_length=1)
    candidate_task_version: str = Field(min_length=1)
    candidate_prompt_version: str = Field(min_length=1)
    candidate_model_id: str = Field(min_length=1)
    candidate_model_ref: str = Field(min_length=1)
    decision_transition_counts: dict[str, int] = Field(default_factory=dict)
    correctness_transition_counts: dict[str, int] = Field(default_factory=dict)
    candidate_target_pattern_counts: dict[str, int] = Field(default_factory=dict)
    improvement_count: int = Field(ge=0)
    regression_count: int = Field(ge=0)
    stable_wrong_count: int = Field(ge=0)
    end_to_end_metrics: ApplicabilityMetricDelta
    baseline_end_to_end_unresolved_count: int = Field(ge=0)
    candidate_end_to_end_unresolved_count: int = Field(ge=0)
    cases: tuple[ApplicabilityDetailComparisonCase, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> ApplicabilityDetailComparisonReport:
        if self.selected_clause_count != len(self.cases):
            raise ValueError("selected_clause_count must match comparison cases")
        if self.golden_candidate_count != sum(
            item.expected_present is not None for item in self.cases
        ):
            raise ValueError("golden_candidate_count must match annotated comparison cases")
        if sum(self.decision_transition_counts.values()) != self.selected_clause_count:
            raise ValueError("detail decision transition counts must cover the exact selection")
        if sum(self.correctness_transition_counts.values()) != self.golden_candidate_count:
            raise ValueError("correctness transition counts must cover golden detail candidates")
        if sum(self.candidate_target_pattern_counts.values()) != self.selected_clause_count:
            raise ValueError("candidate target patterns must cover the exact selection")
        return self


def compare_applicability_detail_contracts(
    golden: ApplicabilityGoldenCorpus,
    *,
    baseline_archive: Path,
    candidate_directory: Path,
) -> ApplicabilityDetailComparisonReport:
    """Compare one isolated detail run with the archived baseline on the same selection."""

    baseline_consensus, baseline_selection, baseline_detail = (
        load_applicability_end_to_end_artifacts(baseline_archive)
    )
    candidate_selection_path = candidate_directory / APPLICABILITY_DETAIL_SELECTION_FILENAME
    candidate_report_path = candidate_directory / APPLICABILITY_DETAIL_REPORT_FILENAME
    if not candidate_selection_path.is_file():
        raise ValueError(f"candidate detail selection not found: {candidate_selection_path}")
    if not candidate_report_path.is_file():
        raise ValueError(f"candidate detail report not found: {candidate_report_path}")

    candidate_selection = load_applicability_detail_selection(candidate_selection_path)
    candidate_detail = load_applicability_detail_report(candidate_report_path)
    _validate_comparison_inputs(
        baseline_selection=baseline_selection,
        baseline_detail=baseline_detail,
        candidate_selection=candidate_selection,
        candidate_detail=candidate_detail,
    )
    validate_applicability_detail_provenance(
        consensus=baseline_consensus,
        selection=candidate_selection,
        detail=candidate_detail,
    )

    baseline_e2e = evaluate_applicability_end_to_end_from_artifacts(
        golden,
        consensus=baseline_consensus,
        selection=baseline_selection,
        detail=baseline_detail,
    )
    candidate_e2e = evaluate_applicability_end_to_end_from_artifacts(
        golden,
        consensus=baseline_consensus,
        selection=candidate_selection,
        detail=candidate_detail,
    )

    published_gold = {
        (case.document_key, case.clause_id): case.expected.present
        for case in golden.cases
        if case.status == "published" and case.expected is not None
    }
    baseline_by_coordinate = _detail_by_coordinate(baseline_detail, "baseline")
    candidate_by_coordinate = _detail_by_coordinate(candidate_detail, "candidate")

    decision_transitions: Counter[str] = Counter()
    correctness_transitions: Counter[str] = Counter()
    target_patterns: Counter[str] = Counter()
    cases: list[ApplicabilityDetailComparisonCase] = []

    for selected in baseline_selection.clauses:
        coordinate = (selected.document_key, selected.clause_id)
        baseline_result = baseline_by_coordinate[coordinate]
        candidate_result = candidate_by_coordinate[coordinate]
        expected_present = published_gold.get(coordinate)

        baseline_final = _detail_final_present(baseline_result)
        candidate_final = _detail_final_present(candidate_result)
        baseline_decision = _detail_decision_class(baseline_result)
        candidate_decision = _detail_decision_class(candidate_result)
        decision_transition = f"{baseline_decision.value}_to_{candidate_decision.value}"
        decision_transitions[decision_transition] += 1

        target_pattern = _candidate_target_pattern(candidate_result)
        target_patterns[target_pattern.value] += 1

        baseline_state = None
        candidate_state = None
        correctness_transition = None
        if expected_present is not None:
            baseline_state = _comparison_state(baseline_final, expected_present)
            candidate_state = _comparison_state(candidate_final, expected_present)
            correctness_transition = f"{baseline_state.value}_to_{candidate_state.value}"
            correctness_transitions[correctness_transition] += 1

        cases.append(
            ApplicabilityDetailComparisonCase(
                document_key=selected.document_key,
                clause_id=selected.clause_id,
                reference=selected.reference,
                expected_present=expected_present,
                baseline_outcome=baseline_result.outcome,
                candidate_outcome=candidate_result.outcome,
                baseline_applicability_target=baseline_result.applicability_target,
                candidate_contains_clause_or_requirement_applicability=(
                    candidate_result.contains_clause_or_requirement_applicability
                ),
                candidate_other_applicability_targets=(
                    candidate_result.other_applicability_targets
                ),
                baseline_final_present=baseline_final,
                candidate_final_present=candidate_final,
                baseline_state=baseline_state,
                candidate_state=candidate_state,
                correctness_transition=correctness_transition,
                decision_transition=decision_transition,
                candidate_target_pattern=target_pattern,
            )
        )

    improvement_count = (
        correctness_transitions["wrong_to_correct"]
        + correctness_transitions["unresolved_to_correct"]
    )
    regression_count = (
        correctness_transitions["correct_to_wrong"]
        + correctness_transitions["correct_to_unresolved"]
    )
    stable_wrong_count = correctness_transitions["wrong_to_wrong"]

    return ApplicabilityDetailComparisonReport(
        golden_corpus_id=golden.corpus_id,
        golden_corpus_version=golden.corpus_version,
        source_matrix_id=baseline_consensus.matrix_id,
        source_corpus_id=baseline_consensus.corpus_id,
        baseline_archive=baseline_archive.name,
        baseline_archive_sha256=_file_sha256(baseline_archive),
        selection_sha256=baseline_selection.fingerprint,
        selected_clause_count=baseline_selection.selected_clause_count,
        golden_candidate_count=sum(item.expected_present is not None for item in cases),
        baseline_task_version=baseline_detail.task_version,
        baseline_prompt_version=baseline_detail.prompt_version,
        baseline_model_id=baseline_detail.model_id,
        baseline_model_ref=baseline_detail.model_ref,
        candidate_task_version=candidate_detail.task_version,
        candidate_prompt_version=candidate_detail.prompt_version,
        candidate_model_id=candidate_detail.model_id,
        candidate_model_ref=candidate_detail.model_ref,
        decision_transition_counts=dict(sorted(decision_transitions.items())),
        correctness_transition_counts=dict(sorted(correctness_transitions.items())),
        candidate_target_pattern_counts=dict(sorted(target_patterns.items())),
        improvement_count=improvement_count,
        regression_count=regression_count,
        stable_wrong_count=stable_wrong_count,
        end_to_end_metrics=_metric_delta(baseline_e2e, candidate_e2e),
        baseline_end_to_end_unresolved_count=baseline_e2e.end_to_end_unresolved_count,
        candidate_end_to_end_unresolved_count=candidate_e2e.end_to_end_unresolved_count,
        cases=tuple(cases),
    )


def _validate_comparison_inputs(
    *,
    baseline_selection: ApplicabilityDetailSelection,
    baseline_detail: ApplicabilityDetailEnrichmentReport,
    candidate_selection: ApplicabilityDetailSelection,
    candidate_detail: ApplicabilityDetailEnrichmentReport,
) -> None:
    if candidate_selection.fingerprint != baseline_selection.fingerprint:
        raise ValueError(
            "candidate applicability detail selection differs from the archived baseline; "
            "reuse the exact persisted selection for a valid contract A/B comparison"
        )
    if candidate_detail.processed_clause_count != candidate_detail.selected_clause_count:
        raise ValueError("candidate applicability detail report is incomplete")
    if baseline_detail.processed_clause_count != baseline_detail.selected_clause_count:
        raise ValueError("baseline applicability detail report is incomplete")

    _validate_candidate_contract(candidate_detail)


def _validate_candidate_contract(report: ApplicabilityDetailEnrichmentReport) -> None:
    """Accept either the legacy single-target contract or the dual-decision contract."""
    for item in report.clauses:
        if item.outcome is ApplicabilityDetailOutcome.FAILED:
            continue
        if item.contains_clause_or_requirement_applicability is not None:
            continue
        if item.applicability_target is None:
            raise ValueError(
                "candidate detail result has neither a dual-decision boolean nor a "
                f"single applicability target: {item.document_key}/{item.clause_id}"
            )


def _detail_by_coordinate(
    report: ApplicabilityDetailEnrichmentReport,
    label: str,
) -> dict[tuple[str, str], ApplicabilityDetailClauseResult]:
    by_coordinate = {(item.document_key, item.clause_id): item for item in report.clauses}
    if len(by_coordinate) != len(report.clauses):
        raise ValueError(f"{label} applicability detail coordinates must be unique")
    return by_coordinate


def _detail_final_present(result: ApplicabilityDetailClauseResult) -> bool | None:
    if result.outcome is ApplicabilityDetailOutcome.FAILED:
        return None
    if result.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
        return False
    return True


def _detail_decision_class(
    result: ApplicabilityDetailClauseResult,
) -> ApplicabilityDetailDecisionClass:
    if result.outcome is ApplicabilityDetailOutcome.FAILED:
        return ApplicabilityDetailDecisionClass.FAILED
    if result.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED:
        return ApplicabilityDetailDecisionClass.NON_CLAUSE
    return ApplicabilityDetailDecisionClass.CLAUSE_OR_REQUIREMENT


def _candidate_target_pattern(
    result: ApplicabilityDetailClauseResult,
) -> ApplicabilityCandidateTargetPattern:
    if result.outcome is ApplicabilityDetailOutcome.FAILED:
        return ApplicabilityCandidateTargetPattern.FAILED
    contains_clause = result.contains_clause_or_requirement_applicability
    if contains_clause is None:
        if result.applicability_target is ApplicabilityTarget.CLAUSE_OR_REQUIREMENT:
            return ApplicabilityCandidateTargetPattern.CLAUSE_ONLY
        if result.applicability_target in {None, ApplicabilityTarget.NONE}:
            return ApplicabilityCandidateTargetPattern.NON_CLAUSE_UNSPECIFIED
        return ApplicabilityCandidateTargetPattern.NON_CLAUSE_TARGET
    if contains_clause:
        if result.other_applicability_targets:
            return ApplicabilityCandidateTargetPattern.MIXED_TARGET
        return ApplicabilityCandidateTargetPattern.CLAUSE_ONLY
    if result.other_applicability_targets:
        return ApplicabilityCandidateTargetPattern.NON_CLAUSE_TARGET
    return ApplicabilityCandidateTargetPattern.NON_CLAUSE_UNSPECIFIED


def _comparison_state(
    final_present: bool | None,
    expected_present: bool,
) -> ApplicabilityComparisonState:
    if final_present is None:
        return ApplicabilityComparisonState.UNRESOLVED
    if final_present == expected_present:
        return ApplicabilityComparisonState.CORRECT
    return ApplicabilityComparisonState.WRONG


def _metric_delta(
    baseline: ApplicabilityEndToEndRegressionReport,
    candidate: ApplicabilityEndToEndRegressionReport,
) -> ApplicabilityMetricDelta:
    before = baseline.end_to_end
    after = candidate.end_to_end
    return ApplicabilityMetricDelta(
        baseline=before,
        candidate=after,
        true_positive_delta=after.true_positive - before.true_positive,
        false_positive_delta=after.false_positive - before.false_positive,
        true_negative_delta=after.true_negative - before.true_negative,
        false_negative_delta=after.false_negative - before.false_negative,
        accuracy_delta=after.presence_accuracy - before.presence_accuracy,
        precision_delta=after.presence_precision - before.presence_precision,
        recall_delta=after.presence_recall - before.presence_recall,
        specificity_delta=after.presence_specificity - before.presence_specificity,
        balanced_accuracy_delta=(
            after.presence_balanced_accuracy - before.presence_balanced_accuracy
        ),
        f1_delta=after.presence_f1 - before.presence_f1,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
