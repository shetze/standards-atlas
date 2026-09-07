"""Prompt-by-model matrix summaries for applicability-detail experiments."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
    ApplicabilityModelMetrics,
)
from standards_atlas.application.semantic_qualification.applicability_detail_comparison import (
    ApplicabilityDetailComparisonReport,
    compare_applicability_detail_contracts,
)


class ApplicabilityDetailModelMatrixRow(BaseModel):
    """One prompt/model candidate evaluated against the shared archived baseline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_directory: str = Field(min_length=1)
    task_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_ref: str = Field(min_length=1)
    metrics: ApplicabilityModelMetrics
    improvement_count: int = Field(ge=0)
    regression_count: int = Field(ge=0)
    stable_wrong_count: int = Field(ge=0)
    candidate_target_pattern_counts: dict[str, int] = Field(default_factory=dict)
    decision_transition_counts: dict[str, int] = Field(default_factory=dict)
    correctness_transition_counts: dict[str, int] = Field(default_factory=dict)


class ApplicabilityDetailModelMatrixReport(BaseModel):
    """Comparable prompt/model results over one immutable Presence-positive selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
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
    baseline_metrics: ApplicabilityModelMetrics
    rows: tuple[ApplicabilityDetailModelMatrixRow, ...]
    comparisons: tuple[ApplicabilityDetailComparisonReport, ...]

    @model_validator(mode="after")
    def validate_rows(self) -> ApplicabilityDetailModelMatrixReport:
        identities = [(item.model_id, item.prompt_version, item.task_version) for item in self.rows]
        if len(identities) != len(set(identities)):
            raise ValueError("model matrix contains duplicate model/prompt/task candidates")
        if len(self.rows) != len(self.comparisons):
            raise ValueError("model matrix rows and detailed comparisons must align")
        return self


def build_applicability_detail_model_matrix(
    golden: ApplicabilityGoldenCorpus,
    *,
    baseline_archive: Path,
    candidate_directories: tuple[Path, ...],
) -> ApplicabilityDetailModelMatrixReport:
    """Evaluate several candidate directories against one immutable archived baseline."""
    if not candidate_directories:
        raise ValueError("at least one candidate detail directory is required")

    comparisons = tuple(
        compare_applicability_detail_contracts(
            golden,
            baseline_archive=baseline_archive,
            candidate_directory=directory,
        )
        for directory in candidate_directories
    )
    _validate_shared_baseline(comparisons)
    first = comparisons[0]

    rows = tuple(
        ApplicabilityDetailModelMatrixRow(
            candidate_directory=str(directory),
            task_version=comparison.candidate_task_version,
            prompt_version=comparison.candidate_prompt_version,
            model_id=comparison.candidate_model_id,
            model_ref=comparison.candidate_model_ref,
            metrics=comparison.end_to_end_metrics.candidate,
            improvement_count=comparison.improvement_count,
            regression_count=comparison.regression_count,
            stable_wrong_count=comparison.stable_wrong_count,
            candidate_target_pattern_counts=comparison.candidate_target_pattern_counts,
            decision_transition_counts=comparison.decision_transition_counts,
            correctness_transition_counts=comparison.correctness_transition_counts,
        )
        for directory, comparison in zip(candidate_directories, comparisons, strict=True)
    )

    return ApplicabilityDetailModelMatrixReport(
        golden_corpus_id=first.golden_corpus_id,
        golden_corpus_version=first.golden_corpus_version,
        source_matrix_id=first.source_matrix_id,
        source_corpus_id=first.source_corpus_id,
        baseline_archive=first.baseline_archive,
        baseline_archive_sha256=first.baseline_archive_sha256,
        selection_sha256=first.selection_sha256,
        selected_clause_count=first.selected_clause_count,
        golden_candidate_count=first.golden_candidate_count,
        baseline_task_version=first.baseline_task_version,
        baseline_prompt_version=first.baseline_prompt_version,
        baseline_model_id=first.baseline_model_id,
        baseline_model_ref=first.baseline_model_ref,
        baseline_metrics=first.end_to_end_metrics.baseline,
        rows=rows,
        comparisons=comparisons,
    )


def _validate_shared_baseline(
    comparisons: tuple[ApplicabilityDetailComparisonReport, ...],
) -> None:
    first = comparisons[0]
    shared = (
        first.golden_corpus_id,
        first.golden_corpus_version,
        first.source_matrix_id,
        first.source_corpus_id,
        first.baseline_archive_sha256,
        first.selection_sha256,
        first.selected_clause_count,
        first.golden_candidate_count,
        first.baseline_task_version,
        first.baseline_prompt_version,
        first.baseline_model_id,
        first.baseline_model_ref,
    )
    for comparison in comparisons[1:]:
        current = (
            comparison.golden_corpus_id,
            comparison.golden_corpus_version,
            comparison.source_matrix_id,
            comparison.source_corpus_id,
            comparison.baseline_archive_sha256,
            comparison.selection_sha256,
            comparison.selected_clause_count,
            comparison.golden_candidate_count,
            comparison.baseline_task_version,
            comparison.baseline_prompt_version,
            comparison.baseline_model_id,
            comparison.baseline_model_ref,
        )
        if current != shared:
            raise ValueError("candidate comparisons do not share one immutable baseline")
