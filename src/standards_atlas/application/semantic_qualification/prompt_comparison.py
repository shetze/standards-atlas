"""Pairwise prompt-value analysis for semantic qualification runs."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationLifecycleStatus,
    ClauseAnnotationResolver,
    CorpusManifestRepository,
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.qualification import (
    _load_predictions,
    _structure_selection,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
    QualificationMatrixManifest,
)

PromptDeltaOutcome = Literal[
    "unchanged",
    "changed",
    "improved",
    "degraded",
    "resolved_only_by_context",
    "lost_by_context",
]


class PromptDeltaCase(BaseModel):
    """One same-model, same-clause comparison between two prompt variants."""

    model_config = ConfigDict(frozen=True)

    clause_key: str
    outcome: PromptDeltaOutcome
    evidence_source: str | None = None
    baseline_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_score: float | None = Field(default=None, ge=0.0, le=1.0)


class PromptPairComparison(BaseModel):
    """Aggregate value of one candidate prompt relative to another prompt."""

    model_config = ConfigDict(frozen=True)

    baseline_prompt_id: str
    candidate_prompt_id: str
    model_id: str
    reasoning_mode_id: str
    repetition: int
    comparable_clauses: int = Field(ge=0)
    outcome_counts: dict[str, int]
    mean_baseline_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_candidate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    cases: tuple[PromptDeltaCase, ...] = ()


class PromptComparisonReport(BaseModel):
    """Pairwise prompt-value report built without triggering additional inference."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    matrix_id: str
    corpus_id: str
    comparisons: tuple[PromptPairComparison, ...]
    diagnostics: tuple[str, ...] = ()


def build_prompt_comparison_report(
    *,
    manifest: QualificationMatrixManifest,
    local_corpus_root: Path,
    published_corpus_root: Path,
) -> PromptComparisonReport:
    """Compare prompt runs sharing model, reasoning mode, repetition, and clauses."""
    expected = _expected_selections(
        corpus_id=manifest.corpus_id,
        local_corpus_root=local_corpus_root,
        published_corpus_root=published_corpus_root,
    )
    observation_groups: dict[tuple[str, str, int], dict[str, MatrixObservation]] = {}
    diagnostics: list[str] = []
    for observation in manifest.observations:
        if observation.run_directory is None or not observation.run_directory.is_dir():
            continue
        key = (observation.model_id, observation.reasoning_mode_id, observation.repetition)
        observation_groups.setdefault(key, {})[observation.prompt_id] = observation

    prompt_order = [prompt.id for prompt in manifest.prompts]
    comparisons: list[PromptPairComparison] = []
    for (model_id, reasoning_mode_id, repetition), observations in sorted(
        observation_groups.items()
    ):
        available = [prompt_id for prompt_id in prompt_order if prompt_id in observations]
        for baseline_prompt_id, candidate_prompt_id in combinations(available, 2):
            baseline_run = observations[baseline_prompt_id].run_directory
            candidate_run = observations[candidate_prompt_id].run_directory
            assert baseline_run is not None and candidate_run is not None
            baseline = _load_predictions(baseline_run)
            candidate = _load_predictions(candidate_run)
            keys = sorted(set(baseline).union(candidate))
            cases = tuple(
                _compare_case(
                    key,
                    baseline.get(key),
                    candidate.get(key),
                    expected.get(key),
                )
                for key in keys
            )
            counts = Counter(case.outcome for case in cases)
            baseline_scores = [
                case.baseline_score for case in cases if case.baseline_score is not None
            ]
            candidate_scores = [
                case.candidate_score for case in cases if case.candidate_score is not None
            ]
            comparisons.append(
                PromptPairComparison(
                    baseline_prompt_id=baseline_prompt_id,
                    candidate_prompt_id=candidate_prompt_id,
                    model_id=model_id,
                    reasoning_mode_id=reasoning_mode_id,
                    repetition=repetition,
                    comparable_clauses=len(cases),
                    outcome_counts=dict(sorted(counts.items())),
                    mean_baseline_score=(
                        sum(baseline_scores) / len(baseline_scores) if baseline_scores else None
                    ),
                    mean_candidate_score=(
                        sum(candidate_scores) / len(candidate_scores) if candidate_scores else None
                    ),
                    cases=cases,
                )
            )

    if not comparisons:
        diagnostics.append(
            "no pairwise prompt runs share the same model, reasoning mode, and repetition; "
            "run benchmark/full-matrix prompts to measure prompt deltas"
        )
    return PromptComparisonReport(
        matrix_id=manifest.matrix_id,
        corpus_id=manifest.corpus_id,
        comparisons=tuple(comparisons),
        diagnostics=tuple(diagnostics),
    )


def persist_prompt_comparison_report(
    report: PromptComparisonReport, output_directory: Path
) -> tuple[Path, Path]:
    """Persist machine-readable and compact human-readable prompt comparison reports."""
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "prompt-comparison.json"
    markdown_path = output_directory / "prompt-comparison.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _expected_selections(
    *, corpus_id: str, local_corpus_root: Path, published_corpus_root: Path
) -> dict[str, tuple[StatementFunctionSelection, str]]:
    manifest = CorpusManifestRepository(local_corpus_root).load(corpus_id)
    resolver = ClauseAnnotationResolver(
        local_root=local_corpus_root,
        published_root=published_corpus_root,
    )
    result: dict[str, tuple[StatementFunctionSelection, str]] = {}
    for member in manifest.clauses:
        key = member.clause.key
        try:
            resolved = resolver.resolve(corpus_id, member.clause)
        except (OSError, RuntimeError, ValueError):
            resolved = None
        if resolved is not None:
            annotation = resolved.annotation
            if (
                annotation.lifecycle_status
                in {AnnotationLifecycleStatus.REVIEWED, AnnotationLifecycleStatus.PUBLISHED}
                and annotation.annotation is not None
            ):
                result[key] = (annotation.annotation, resolved.source.value)
                continue
            result[key] = (annotation.proposal, resolved.source.value)
            continue
        structure = _structure_selection(member.strata)
        if structure is not None:
            result[key] = (structure, "structure")
    return result


def _compare_case(
    key: str,
    baseline: StatementFunctionSelection | None,
    candidate: StatementFunctionSelection | None,
    expected_entry: tuple[StatementFunctionSelection, str] | None,
) -> PromptDeltaCase:
    if baseline is None and candidate is not None:
        return PromptDeltaCase(
            clause_key=key,
            outcome="resolved_only_by_context",
            evidence_source=expected_entry[1] if expected_entry else None,
            baseline_score=0.0 if expected_entry else None,
            candidate_score=(
                _selection_score(candidate, expected_entry[0]) if expected_entry else None
            ),
        )
    if baseline is not None and candidate is None:
        return PromptDeltaCase(
            clause_key=key,
            outcome="lost_by_context",
            evidence_source=expected_entry[1] if expected_entry else None,
            baseline_score=(
                _selection_score(baseline, expected_entry[0]) if expected_entry else None
            ),
            candidate_score=0.0 if expected_entry else None,
        )
    assert baseline is not None and candidate is not None
    if _semantic_signature(baseline) == _semantic_signature(candidate):
        score = _selection_score(baseline, expected_entry[0]) if expected_entry else None
        return PromptDeltaCase(
            clause_key=key,
            outcome="unchanged",
            evidence_source=expected_entry[1] if expected_entry else None,
            baseline_score=score,
            candidate_score=score,
        )
    if expected_entry is None:
        return PromptDeltaCase(clause_key=key, outcome="changed")
    expected, source = expected_entry
    baseline_score = _selection_score(baseline, expected)
    candidate_score = _selection_score(candidate, expected)
    if candidate_score > baseline_score:
        outcome: PromptDeltaOutcome = "improved"
    elif candidate_score < baseline_score:
        outcome = "degraded"
    else:
        outcome = "changed"
    return PromptDeltaCase(
        clause_key=key,
        outcome=outcome,
        evidence_source=source,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
    )


def _semantic_signature(selection: StatementFunctionSelection) -> tuple[object, ...]:
    return (
        tuple(sorted(item.value for item in selection.statement_functions)),
        selection.primary_function.value if selection.primary_function else None,
        tuple(sorted(item.value for item in selection.knowledge_kinds)),
        selection.primary_knowledge_kind.value if selection.primary_knowledge_kind else None,
        selection.applicability_present,
        tuple(sorted(item.value for item in selection.applicability_functions)),
        selection.primary_applicability_function.value
        if selection.primary_applicability_function
        else None,
        selection.role_semantics_present,
        tuple(sorted(item.value for item in selection.role_relation_types)),
    )


def _selection_score(
    predicted: StatementFunctionSelection, expected: StatementFunctionSelection
) -> float:
    """Return a simple four-dimension exact agreement score for prompt deltas."""
    dimensions = (
        (
            tuple(sorted(item.value for item in predicted.statement_functions)),
            predicted.primary_function.value if predicted.primary_function else None,
        )
        == (
            tuple(sorted(item.value for item in expected.statement_functions)),
            expected.primary_function.value if expected.primary_function else None,
        ),
        (
            tuple(sorted(item.value for item in predicted.knowledge_kinds)),
            predicted.primary_knowledge_kind.value if predicted.primary_knowledge_kind else None,
        )
        == (
            tuple(sorted(item.value for item in expected.knowledge_kinds)),
            expected.primary_knowledge_kind.value if expected.primary_knowledge_kind else None,
        ),
        (
            predicted.applicability_present,
            tuple(sorted(item.value for item in predicted.applicability_functions)),
            predicted.primary_applicability_function.value
            if predicted.primary_applicability_function
            else None,
        )
        == (
            expected.applicability_present,
            tuple(sorted(item.value for item in expected.applicability_functions)),
            expected.primary_applicability_function.value
            if expected.primary_applicability_function
            else None,
        ),
        (
            predicted.role_semantics_present,
            tuple(sorted(item.value for item in predicted.role_relation_types)),
        )
        == (
            expected.role_semantics_present,
            tuple(sorted(item.value for item in expected.role_relation_types)),
        ),
    )
    return sum(dimensions) / len(dimensions)


def _render_markdown(report: PromptComparisonReport) -> str:
    lines = [
        f"# Prompt comparison — {report.matrix_id}",
        "",
        "Pairwise comparisons use existing runs only; this report never triggers inference.",
        "`improved` and `degraded` are emitted only when corpus evidence is available.",
        "",
    ]
    if report.diagnostics:
        lines += ["## Diagnostics", "", *[f"- {item}" for item in report.diagnostics], ""]
    if not report.comparisons:
        return "\n".join(lines).rstrip() + "\n"
    lines += [
        "| Prompt pair | Model | Rep | Clauses | Unchanged | Changed | Improved | "
        "Degraded | Resolved only | Lost | Δ score |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.comparisons:
        counts = item.outcome_counts
        delta = (
            item.mean_candidate_score - item.mean_baseline_score
            if item.mean_candidate_score is not None and item.mean_baseline_score is not None
            else None
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{item.baseline_prompt_id} → {item.candidate_prompt_id}",
                    item.model_id,
                    str(item.repetition),
                    str(item.comparable_clauses),
                    str(counts.get("unchanged", 0)),
                    str(counts.get("changed", 0)),
                    str(counts.get("improved", 0)),
                    str(counts.get("degraded", 0)),
                    str(counts.get("resolved_only_by_context", 0)),
                    str(counts.get("lost_by_context", 0)),
                    f"{delta:+.3f}" if delta is not None else "—",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
