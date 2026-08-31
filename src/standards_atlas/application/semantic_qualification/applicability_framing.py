"""Applicability-specific CBox framing ablation reports."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.annotations import (
    StatementFunctionSelection,
)
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCorpus,
)
from standards_atlas.application.semantic_qualification.qualification import (
    _load_predictions,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)


class ApplicabilityFrameMetrics(BaseModel):
    """Applicability behavior for one model/prompt/frame observation."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    prompt_version: str | None = None
    cbox_frame: str
    model_id: str
    reasoning_mode_id: str
    repetition: int
    evaluated_clauses: int = Field(ge=0)
    applicability_present_count: int = Field(ge=0)
    applicability_present_rate: float = Field(ge=0.0, le=1.0)
    polarity_counts: dict[str, int]
    golden_cases: int = Field(default=0, ge=0)
    false_positives: int | None = Field(default=None, ge=0)
    false_negatives: int | None = Field(default=None, ge=0)
    presence_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    presence_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    presence_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    polarity_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)


class ApplicabilityFrameDelta(BaseModel):
    """Same-model applicability delta between two prompt/frame observations."""

    model_config = ConfigDict(frozen=True)

    baseline_prompt_id: str
    baseline_cbox_frame: str
    candidate_prompt_id: str
    candidate_cbox_frame: str
    model_id: str
    reasoning_mode_id: str
    repetition: int
    comparable_clauses: int = Field(ge=0)
    presence_disagreement_count: int = Field(ge=0)
    presence_disagreement_rate: float = Field(ge=0.0, le=1.0)
    polarity_disagreement_count: int = Field(ge=0)
    polarity_disagreement_rate: float = Field(ge=0.0, le=1.0)
    changed_to_present: int = Field(ge=0)
    changed_to_absent: int = Field(ge=0)
    golden_outcome: Literal["improved", "degraded", "unchanged", "unscored"] = "unscored"
    baseline_golden_errors: int | None = Field(default=None, ge=0)
    candidate_golden_errors: int | None = Field(default=None, ge=0)


class ApplicabilityFramingReport(BaseModel):
    """CBox framing ablation focused exclusively on applicability semantics."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    matrix_id: str
    corpus_id: str
    golden_corpus_id: str | None = None
    observations: tuple[ApplicabilityFrameMetrics, ...]
    comparisons: tuple[ApplicabilityFrameDelta, ...]
    diagnostics: tuple[str, ...] = ()


def build_applicability_framing_report(
    *,
    manifest: QualificationMatrixManifest,
    golden_path: Path | None = None,
) -> ApplicabilityFramingReport:
    """Build a no-inference applicability framing ablation from existing observations."""
    prompt_by_id = {prompt.id: prompt for prompt in manifest.prompts}
    golden = _load_optional_golden(golden_path)
    expected = _golden_expected(golden)
    diagnostics: list[str] = []
    if golden_path is not None and golden is None:
        diagnostics.append(f"applicability golden corpus not available: {golden_path}")

    rows: list[ApplicabilityFrameMetrics] = []
    predictions_by_key: dict[tuple[str, str, int, str], dict[str, StatementFunctionSelection]] = {}
    for observation in manifest.observations:
        if observation.run_directory is None or not observation.run_directory.is_dir():
            continue
        prompt = prompt_by_id.get(observation.prompt_id)
        if prompt is None:
            continue
        predictions = _load_predictions(observation.run_directory)
        key = (
            observation.model_id,
            observation.reasoning_mode_id,
            observation.repetition,
            observation.prompt_id,
        )
        predictions_by_key[key] = predictions
        rows.append(
            _metrics(
                prompt_id=observation.prompt_id,
                prompt_version=prompt.prompt_version,
                cbox_frame=prompt.cbox_frame,
                model_id=observation.model_id,
                reasoning_mode_id=observation.reasoning_mode_id,
                repetition=observation.repetition,
                predictions=predictions,
                expected=expected,
            )
        )

    comparisons: list[ApplicabilityFrameDelta] = []
    groups: dict[tuple[str, str, int], list[ApplicabilityFrameMetrics]] = {}
    for row in rows:
        groups.setdefault((row.model_id, row.reasoning_mode_id, row.repetition), []).append(row)
    for group_key, group_rows in sorted(groups.items()):
        baseline = _select_baseline(group_rows)
        if baseline is None:
            continue
        baseline_predictions = predictions_by_key[(*group_key, baseline.prompt_id)]
        for candidate in sorted(group_rows, key=lambda item: item.prompt_id):
            if candidate.prompt_id == baseline.prompt_id:
                continue
            candidate_predictions = predictions_by_key[(*group_key, candidate.prompt_id)]
            comparisons.append(
                _compare(
                    baseline,
                    candidate,
                    baseline_predictions,
                    candidate_predictions,
                )
            )

    if not rows:
        diagnostics.append("no completed prompt observations available for framing analysis")
    if rows and not comparisons:
        diagnostics.append("no same-model full-context baseline is available for frame deltas")
    if golden is None:
        diagnostics.append(
            "no published applicability golden corpus loaded; framing deltas are descriptive only"
        )
    return ApplicabilityFramingReport(
        matrix_id=manifest.matrix_id,
        corpus_id=manifest.corpus_id,
        golden_corpus_id=golden.corpus_id if golden is not None else None,
        observations=tuple(
            sorted(
                rows,
                key=lambda row: (
                    row.model_id,
                    row.reasoning_mode_id,
                    row.repetition,
                    row.prompt_id,
                ),
            )
        ),
        comparisons=tuple(comparisons),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def persist_applicability_framing_report(
    report: ApplicabilityFramingReport, output_directory: Path
) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "applicability-framing.json"
    markdown_path = output_directory / "applicability-framing.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _load_optional_golden(path: Path | None) -> ApplicabilityGoldenCorpus | None:
    if path is None or not path.is_file():
        return None
    return ApplicabilityGoldenCorpus.load(path)


def _golden_expected(
    golden: ApplicabilityGoldenCorpus | None,
) -> dict[tuple[str, str], tuple[bool, str | None]]:
    if golden is None:
        return {}
    result: dict[tuple[str, str], tuple[bool, str | None]] = {}
    for case in golden.cases:
        if case.status != "published" or case.expected is None:
            continue
        result[(case.document_key, case.clause_id)] = (
            case.expected.present,
            case.expected.polarity.value if case.expected.polarity is not None else None,
        )
    return result


def _metrics(
    *,
    prompt_id: str,
    prompt_version: str | None,
    cbox_frame: str,
    model_id: str,
    reasoning_mode_id: str,
    repetition: int,
    predictions: dict[str, StatementFunctionSelection],
    expected: dict[tuple[str, str], tuple[bool, str | None]],
) -> ApplicabilityFrameMetrics:
    present = sum(selection.applicability_present for selection in predictions.values())
    polarity_counts = Counter(
        _polarity(selection) or "none"
        for selection in predictions.values()
        if selection.applicability_present
    )
    tp = fp = fn = polarity_total = polarity_correct = 0
    golden_cases = 0
    for key, selection in predictions.items():
        gold = _expected_for_prediction_key(expected, key)
        if gold is None:
            continue
        golden_cases += 1
        expected_present, expected_polarity = gold
        if selection.applicability_present and expected_present:
            tp += 1
        elif selection.applicability_present and not expected_present:
            fp += 1
        elif not selection.applicability_present and expected_present:
            fn += 1
        if expected_present and expected_polarity is not None:
            polarity_total += 1
            polarity_correct += _polarity(selection) == expected_polarity
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ApplicabilityFrameMetrics(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        cbox_frame=cbox_frame,
        model_id=model_id,
        reasoning_mode_id=reasoning_mode_id,
        repetition=repetition,
        evaluated_clauses=len(predictions),
        applicability_present_count=present,
        applicability_present_rate=present / len(predictions) if predictions else 0.0,
        polarity_counts=dict(sorted(polarity_counts.items())),
        golden_cases=golden_cases,
        false_positives=fp if golden_cases else None,
        false_negatives=fn if golden_cases else None,
        presence_precision=precision if golden_cases else None,
        presence_recall=recall if golden_cases else None,
        presence_f1=f1 if golden_cases else None,
        polarity_accuracy=(polarity_correct / polarity_total if polarity_total else None),
    )


def _expected_for_prediction_key(
    expected: dict[tuple[str, str], tuple[bool, str | None]], key: str
) -> tuple[bool, str | None] | None:
    for (document_key, clause_id), value in expected.items():
        if key.endswith(f":{document_key}:{clause_id}"):
            return value
    return None


def _select_baseline(rows: list[ApplicabilityFrameMetrics]) -> ApplicabilityFrameMetrics | None:
    full = [row for row in rows if row.cbox_frame == "full-context-v1"]
    clean_full = [row for row in full if row.prompt_id == "applicability-clean-full"]
    return (clean_full or full or [None])[0]


def _compare(
    baseline: ApplicabilityFrameMetrics,
    candidate: ApplicabilityFrameMetrics,
    baseline_predictions: dict[str, StatementFunctionSelection],
    candidate_predictions: dict[str, StatementFunctionSelection],
) -> ApplicabilityFrameDelta:
    keys = sorted(set(baseline_predictions).intersection(candidate_predictions))
    presence_disagreement = polarity_disagreement = to_present = to_absent = 0
    for key in keys:
        left = baseline_predictions[key]
        right = candidate_predictions[key]
        if left.applicability_present != right.applicability_present:
            presence_disagreement += 1
            if right.applicability_present:
                to_present += 1
            else:
                to_absent += 1
        if (
            left.applicability_present
            and right.applicability_present
            and _polarity(left) != _polarity(right)
        ):
            polarity_disagreement += 1
    baseline_errors = _golden_errors(baseline)
    candidate_errors = _golden_errors(candidate)
    outcome: Literal["improved", "degraded", "unchanged", "unscored"] = "unscored"
    if baseline_errors is not None and candidate_errors is not None:
        if candidate_errors < baseline_errors:
            outcome = "improved"
        elif candidate_errors > baseline_errors:
            outcome = "degraded"
        else:
            outcome = "unchanged"
    return ApplicabilityFrameDelta(
        baseline_prompt_id=baseline.prompt_id,
        baseline_cbox_frame=baseline.cbox_frame,
        candidate_prompt_id=candidate.prompt_id,
        candidate_cbox_frame=candidate.cbox_frame,
        model_id=baseline.model_id,
        reasoning_mode_id=baseline.reasoning_mode_id,
        repetition=baseline.repetition,
        comparable_clauses=len(keys),
        presence_disagreement_count=presence_disagreement,
        presence_disagreement_rate=presence_disagreement / len(keys) if keys else 0.0,
        polarity_disagreement_count=polarity_disagreement,
        polarity_disagreement_rate=polarity_disagreement / len(keys) if keys else 0.0,
        changed_to_present=to_present,
        changed_to_absent=to_absent,
        golden_outcome=outcome,
        baseline_golden_errors=baseline_errors,
        candidate_golden_errors=candidate_errors,
    )


def _golden_errors(metrics: ApplicabilityFrameMetrics) -> int | None:
    if metrics.false_positives is None or metrics.false_negatives is None:
        return None
    return metrics.false_positives + metrics.false_negatives


def _polarity(selection: StatementFunctionSelection) -> str | None:
    value = None
    if selection.primary_applicability_function is not None:
        value = selection.primary_applicability_function.value
    elif selection.applicability_functions:
        value = selection.applicability_functions[0].value
    if value == "inclusion":
        return "included"
    if value == "exclusion":
        return "excluded"
    return None


def _render_markdown(report: ApplicabilityFramingReport) -> str:
    lines = [
        f"# Applicability framing — {report.matrix_id}",
        "",
        "This report compares existing inference results only; it never triggers inference.",
        "Golden outcomes are emitted only when a published applicability corpus is available.",
        "",
    ]
    if report.diagnostics:
        lines += ["## Diagnostics", "", *[f"- {item}" for item in report.diagnostics], ""]
    if report.observations:
        lines += [
            "## Frame observations",
            "",
            "| Prompt / frame | Model | Clauses | Present | Rate | FP | FN | "
            "Precision | Recall | F1 | Polarity acc. |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for item in report.observations:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{item.prompt_id} / {item.cbox_frame}",
                        item.model_id,
                        str(item.evaluated_clauses),
                        str(item.applicability_present_count),
                        f"{item.applicability_present_rate:.3f}",
                        _fmt(item.false_positives),
                        _fmt(item.false_negatives),
                        _fmt_float(item.presence_precision),
                        _fmt_float(item.presence_recall),
                        _fmt_float(item.presence_f1),
                        _fmt_float(item.polarity_accuracy),
                    ]
                )
                + " |"
            )
    if report.comparisons:
        lines += [
            "",
            "## Full-context deltas",
            "",
            "| Baseline → candidate | Model | Clauses | Presence Δ | To present | "
            "To absent | Polarity Δ | Golden | Errors |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
        for item in report.comparisons:
            errors = (
                f"{item.baseline_golden_errors} → {item.candidate_golden_errors}"
                if item.baseline_golden_errors is not None
                else "—"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"{item.baseline_prompt_id}/{item.baseline_cbox_frame} → "
                        f"{item.candidate_prompt_id}/{item.candidate_cbox_frame}",
                        item.model_id,
                        str(item.comparable_clauses),
                        f"{item.presence_disagreement_count} "
                        f"({item.presence_disagreement_rate:.3f})",
                        str(item.changed_to_present),
                        str(item.changed_to_absent),
                        (
                            f"{item.polarity_disagreement_count} "
                            f"({item.polarity_disagreement_rate:.3f})"
                        ),
                        item.golden_outcome,
                        errors,
                    ]
                )
                + " |"
            )
    return "\n".join(lines).rstrip() + "\n"


def _fmt(value: int | None) -> str:
    return str(value) if value is not None else "—"


def _fmt_float(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "—"
