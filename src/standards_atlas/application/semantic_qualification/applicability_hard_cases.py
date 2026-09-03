"""Clause-level applicability presence disagreement analysis for qualification runs."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.annotations import (
    ClauseEvaluationAnnotation,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)

PREDICTION_SNAPSHOT_FILENAME = "applicability-predictions.json"


class ApplicabilityPrediction(BaseModel):
    """One presence-only applicability prediction for an archived clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_key: str
    document_key: str
    clause_id: str
    present: bool
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ApplicabilityPredictionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str
    cbox_frame: str
    model_id: str
    reasoning_mode_id: str
    repetition: int = Field(ge=1)
    predictions: tuple[ApplicabilityPrediction, ...]


class ApplicabilityPredictionSnapshot(BaseModel):
    """Current presence-only prediction snapshot written to qualification archives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    matrix_id: str
    observations: tuple[ApplicabilityPredictionObservation, ...]


class _LegacyApplicabilityPrediction(BaseModel):
    """Polarity-era snapshot item accepted only for retrospective projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_key: str
    document_key: str
    clause_id: str
    present: bool
    polarity: Literal["included", "excluded"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class _LegacyApplicabilityPredictionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str
    cbox_frame: str
    model_id: str
    reasoning_mode_id: str
    repetition: int = Field(ge=1)
    predictions: tuple[_LegacyApplicabilityPrediction, ...]


class _LegacyApplicabilityPredictionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    matrix_id: str
    observations: tuple[_LegacyApplicabilityPredictionObservation, ...]


class PresenceHardCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_key: str
    clause_id: str
    reference: str
    text: str
    category: Literal[
        "balanced_presence_disagreement",
        "minority_presence_disagreement",
        "unanimous_present",
        "unanimous_absent",
        "insufficient_presence_votes",
        "framing_sensitive_presence",
    ]
    participating_models: int = Field(ge=0)
    present_count: int = Field(ge=0)
    absent_count: int = Field(ge=0)
    presence_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    majority_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    disagreement_score: float = Field(ge=0.0, le=1.0)
    present_models: tuple[str, ...] = ()
    absent_models: tuple[str, ...] = ()
    consensus_present: bool | None = None
    framing_sensitive_models: tuple[str, ...] = ()


class ApplicabilityModelPresenceProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    evaluated_clauses: int = Field(ge=0)
    present_count: int = Field(ge=0)
    presence_rate: float = Field(ge=0.0, le=1.0)
    ensemble_disagreement_count: int = Field(ge=0)
    minority_present_count: int = Field(ge=0)
    minority_absent_count: int = Field(ge=0)
    balanced_hard_case_count: int = Field(ge=0)
    framing_sensitive_count: int = Field(ge=0)


class PresenceHardCaseReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    source_archive: str
    matrix_id: str
    baseline_prompt_id: str
    baseline_cbox_frame: str
    analyzed_clauses: int = Field(ge=0)
    category_counts: dict[str, int]
    cases: tuple[PresenceHardCase, ...]
    model_profiles: tuple[ApplicabilityModelPresenceProfile, ...]
    diagnostics: tuple[str, ...] = ()


class PresenceHardCaseArtifacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    json_path: Path
    markdown_path: Path
    review_path: Path
    selected_count: int = Field(ge=0)


def load_applicability_prediction_snapshot(payload: bytes | str) -> ApplicabilityPredictionSnapshot:
    """Load current snapshots and project polarity-era schema 1.0 to presence only."""

    raw = json.loads(payload)
    schema_version = str(raw.get("schema_version") or "")
    if schema_version == "2.0":
        return ApplicabilityPredictionSnapshot.model_validate(raw)
    if schema_version != "1.0":
        raise ValueError(
            "unsupported applicability prediction snapshot schema "
            f"{schema_version!r}; readable versions are '1.0' and '2.0'"
        )

    legacy = _LegacyApplicabilityPredictionSnapshot.model_validate(raw)
    return ApplicabilityPredictionSnapshot(
        matrix_id=legacy.matrix_id,
        observations=tuple(
            ApplicabilityPredictionObservation(
                prompt_id=observation.prompt_id,
                cbox_frame=observation.cbox_frame,
                model_id=observation.model_id,
                reasoning_mode_id=observation.reasoning_mode_id,
                repetition=observation.repetition,
                predictions=tuple(
                    ApplicabilityPrediction(
                        clause_key=prediction.clause_key,
                        document_key=prediction.document_key,
                        clause_id=prediction.clause_id,
                        present=prediction.present,
                        confidence=prediction.confidence,
                    )
                    for prediction in observation.predictions
                ),
            )
            for observation in legacy.observations
        ),
    )


def persist_applicability_prediction_snapshot(
    manifest: QualificationMatrixManifest,
    output_directory: Path,
) -> Path:
    """Persist compact clause-level presence predictions needed by run analysis."""

    prompt_frames = {prompt.id: prompt.cbox_frame for prompt in manifest.prompts}
    observations: list[ApplicabilityPredictionObservation] = []
    for observation in manifest.observations:
        if observation.run_directory is None:
            continue
        predictions: list[ApplicabilityPrediction] = []
        paths = tuple(observation.run_directory.rglob("evaluation.yaml")) + tuple(
            observation.run_directory.rglob("evaluation.json")
        )
        for path in sorted(paths):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            annotation = ClauseEvaluationAnnotation.model_validate(payload["annotation_candidate"])
            selection = annotation.proposal
            predictions.append(
                ApplicabilityPrediction(
                    clause_key=annotation.clause.key,
                    document_key=annotation.clause.document_key,
                    clause_id=annotation.clause.clause_id,
                    present=selection.applicability_present,
                    confidence=selection.confidence,
                )
            )
        if not predictions:
            continue
        observations.append(
            ApplicabilityPredictionObservation(
                prompt_id=observation.prompt_id,
                cbox_frame=prompt_frames[observation.prompt_id],
                model_id=observation.model_id,
                reasoning_mode_id=observation.reasoning_mode_id,
                repetition=observation.repetition,
                predictions=tuple(predictions),
            )
        )
    snapshot = ApplicabilityPredictionSnapshot(
        matrix_id=manifest.matrix_id,
        observations=tuple(observations),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / PREDICTION_SNAPSHOT_FILENAME
    path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def project_applicability_hard_cases(run_archive: Path) -> PresenceHardCaseReport:
    """Project the shared clause-level hard-case view from an immutable run archive."""

    with ZipFile(run_archive) as archive:
        manifest = yaml.safe_load(archive.read("configuration/qualification-manifest.yaml")) or {}
        snapshot_name = _find_member(archive, PREDICTION_SNAPSHOT_FILENAME)
        if snapshot_name is None:
            raise ValueError(
                "qualification run does not contain clause-level applicability predictions; "
                "rerun qualification with the current archive schema"
            )
        snapshot = load_applicability_prediction_snapshot(archive.read(snapshot_name))
        dataset = json.loads(archive.read("inputs/corpus/dataset.json"))

    details = _dataset_details(dataset)
    eligible = _presence_eligible_model_ids(manifest)
    baseline_prompt, baseline_frame = _baseline(snapshot)
    baseline = _collapsed_predictions(
        snapshot,
        prompt_id=baseline_prompt,
        cbox_frame=baseline_frame,
        eligible=eligible,
    )
    comparison = _comparison_predictions(
        snapshot,
        baseline_prompt_id=baseline_prompt,
        baseline_cbox_frame=baseline_frame,
        eligible=eligible,
    )
    cases = _build_cases(baseline, comparison, details)
    profiles = _model_profiles(baseline, comparison, cases)
    return PresenceHardCaseReport(
        source_archive=run_archive.name,
        matrix_id=snapshot.matrix_id,
        baseline_prompt_id=baseline_prompt,
        baseline_cbox_frame=baseline_frame,
        analyzed_clauses=len({key for predictions in baseline.values() for key in predictions}),
        category_counts=dict(sorted(Counter(case.category for case in cases).items())),
        cases=tuple(cases),
        model_profiles=tuple(profiles),
    )


def analyze_applicability_hard_cases(
    run_archive: Path,
    output_directory: Path,
    *,
    limit: int = 30,
) -> tuple[PresenceHardCaseReport, PresenceHardCaseArtifacts]:
    """Analyze model presence disagreement from an immutable qualification archive."""

    report = project_applicability_hard_cases(run_archive)
    cases = list(report.cases)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "presence-disagreement-analysis.json"
    markdown_path = output_directory / "presence-disagreement-analysis.md"
    review_path = output_directory / "applicability-golden-review.csv"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    selected = tuple(case for case in cases if _review_candidate(case))[:limit]
    _write_review_csv(review_path, selected)
    return report, PresenceHardCaseArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        review_path=review_path,
        selected_count=len(selected),
    )


def _presence_eligible_model_ids(manifest: dict[str, Any]) -> set[str] | None:
    models = tuple(manifest.get("models", []))
    if not models:
        return None
    return {
        str(model.get("id"))
        for model in models
        if bool((model.get("dimension_eligibility") or {}).get("applicability_presence", True))
    }


def _baseline(snapshot: ApplicabilityPredictionSnapshot) -> tuple[str, str]:
    observations = list(snapshot.observations)
    clean = [
        item
        for item in observations
        if item.cbox_frame == "full-context-v1" and item.prompt_id == "applicability-clean-full"
    ]
    full = [item for item in observations if item.cbox_frame == "full-context-v1"]
    selected = clean or full or observations
    if not selected:
        raise ValueError("applicability prediction snapshot contains no observations")
    return selected[0].prompt_id, selected[0].cbox_frame


def _comparison_predictions(
    snapshot: ApplicabilityPredictionSnapshot,
    *,
    baseline_prompt_id: str,
    baseline_cbox_frame: str,
    eligible: set[str] | None,
) -> dict[str, dict[str, ApplicabilityPrediction]]:
    arms = sorted(
        {
            (item.prompt_id, item.cbox_frame)
            for item in snapshot.observations
            if (item.prompt_id, item.cbox_frame) != (baseline_prompt_id, baseline_cbox_frame)
        },
        key=lambda item: (item[1] == "full-context-v1", item[0], item[1]),
    )
    if not arms:
        return {}
    prompt_id, cbox_frame = arms[0]
    return _collapsed_predictions(
        snapshot,
        prompt_id=prompt_id,
        cbox_frame=cbox_frame,
        eligible=eligible,
    )


def _collapsed_predictions(
    snapshot: ApplicabilityPredictionSnapshot,
    *,
    prompt_id: str,
    cbox_frame: str,
    eligible: set[str] | None,
) -> dict[str, dict[str, ApplicabilityPrediction]]:
    grouped: dict[tuple[str, str], list[ApplicabilityPrediction]] = defaultdict(list)
    for observation in snapshot.observations:
        if observation.prompt_id != prompt_id or observation.cbox_frame != cbox_frame:
            continue
        if eligible is not None and observation.model_id not in eligible:
            continue
        for prediction in observation.predictions:
            grouped[(observation.model_id, prediction.clause_key)].append(prediction)
    result: dict[str, dict[str, ApplicabilityPrediction]] = defaultdict(dict)
    for (model_id, clause_key), predictions in grouped.items():
        collapsed = _collapse_repetitions(predictions)
        if collapsed is not None:
            result[model_id][clause_key] = collapsed
    return dict(result)


def _collapse_repetitions(
    predictions: list[ApplicabilityPrediction],
) -> ApplicabilityPrediction | None:
    present = sum(item.present for item in predictions)
    absent = len(predictions) - present
    if present == absent:
        return None
    selected_present = present > absent
    chosen = next(item for item in predictions if item.present == selected_present)
    confidences = [item.confidence for item in predictions if item.confidence is not None]
    return chosen.model_copy(
        update={
            "present": selected_present,
            "confidence": sum(confidences) / len(confidences) if confidences else None,
        }
    )


def _build_cases(
    baseline: dict[str, dict[str, ApplicabilityPrediction]],
    comparison: dict[str, dict[str, ApplicabilityPrediction]],
    details: dict[tuple[str, str], tuple[str, str]],
) -> list[PresenceHardCase]:
    clause_keys = sorted({key for predictions in baseline.values() for key in predictions})
    cases: list[PresenceHardCase] = []
    for clause_key in clause_keys:
        votes = {
            model: values[clause_key] for model, values in baseline.items() if clause_key in values
        }
        if not votes:
            continue
        present_models = tuple(sorted(model for model, vote in votes.items() if vote.present))
        absent_models = tuple(sorted(model for model, vote in votes.items() if not vote.present))
        count = len(votes)
        present_count = len(present_models)
        absent_count = len(absent_models)
        presence_rate = present_count / count if count else None
        margin = abs(present_count - absent_count) / count if count else None
        disagreement_score = 1.0 - margin if margin is not None else 0.0
        framing = tuple(
            sorted(
                model
                for model, vote in votes.items()
                if clause_key in comparison.get(model, {})
                and comparison[model][clause_key].present != vote.present
            )
        )
        category = _category(count, present_count, absent_count, framing)
        first = next(iter(votes.values()))
        reference, text = details.get((first.document_key, first.clause_id), (first.clause_id, ""))
        consensus = None if present_count == absent_count else present_count > absent_count
        cases.append(
            PresenceHardCase(
                document_key=first.document_key,
                clause_id=first.clause_id,
                reference=reference,
                text=text,
                category=category,
                participating_models=count,
                present_count=present_count,
                absent_count=absent_count,
                presence_rate=presence_rate,
                majority_margin=margin,
                disagreement_score=disagreement_score,
                present_models=present_models,
                absent_models=absent_models,
                consensus_present=consensus,
                framing_sensitive_models=framing,
            )
        )
    cases.sort(key=_case_rank)
    return cases


def _category(
    count: int,
    present: int,
    absent: int,
    framing: tuple[str, ...],
) -> str:
    if count < 3:
        return "insufficient_presence_votes"
    if present and absent:
        margin = abs(present - absent) / count
        return (
            "balanced_presence_disagreement" if margin <= 0.20 else "minority_presence_disagreement"
        )
    if framing:
        return "framing_sensitive_presence"
    return "unanimous_present" if present else "unanimous_absent"


def _case_rank(case: PresenceHardCase) -> tuple[Any, ...]:
    priority = {
        "balanced_presence_disagreement": 0,
        "minority_presence_disagreement": 1,
        "framing_sensitive_presence": 2,
        "insufficient_presence_votes": 3,
        "unanimous_present": 4,
        "unanimous_absent": 5,
    }
    return (
        priority[case.category],
        -case.disagreement_score,
        -case.participating_models,
        -len(case.framing_sensitive_models),
        case.document_key,
        case.reference,
        case.clause_id,
    )


def _model_profiles(
    baseline: dict[str, dict[str, ApplicabilityPrediction]],
    comparison: dict[str, dict[str, ApplicabilityPrediction]],
    cases: list[PresenceHardCase],
) -> list[ApplicabilityModelPresenceProfile]:
    case_map = {(case.document_key, case.clause_id): case for case in cases}
    profiles: list[ApplicabilityModelPresenceProfile] = []
    for model_id, predictions in sorted(baseline.items()):
        present = sum(item.present for item in predictions.values())
        disagreements = minority_present = minority_absent = balanced = framing = 0
        for clause_key, prediction in predictions.items():
            case = case_map.get((prediction.document_key, prediction.clause_id))
            if case is None:
                continue
            if case.consensus_present is not None and prediction.present != case.consensus_present:
                disagreements += 1
                if prediction.present:
                    minority_present += 1
                else:
                    minority_absent += 1
            if case.category == "balanced_presence_disagreement":
                balanced += 1
            if clause_key in comparison.get(model_id, {}):
                framing += comparison[model_id][clause_key].present != prediction.present
        total = len(predictions)
        profiles.append(
            ApplicabilityModelPresenceProfile(
                model_id=model_id,
                evaluated_clauses=total,
                present_count=present,
                presence_rate=present / total if total else 0.0,
                ensemble_disagreement_count=disagreements,
                minority_present_count=minority_present,
                minority_absent_count=minority_absent,
                balanced_hard_case_count=balanced,
                framing_sensitive_count=framing,
            )
        )
    return profiles


def _dataset_details(dataset: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str]]:
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for example in dataset.get("examples", []):
        context = (example.get("input") or {}).get("context") or {}
        content = (example.get("input") or {}).get("content") or {}
        document_key = str(context.get("document_key") or "")
        clause_id = str(context.get("clause_id") or example.get("id") or "")
        reference = str(context.get("reference") or clause_id)
        qualified = f"{document_key}:{reference}" if document_key else reference
        result[(document_key, clause_id)] = (qualified, str(content.get("text") or ""))
    return result


def _find_member(archive: ZipFile, filename: str) -> str | None:
    matches = [
        name for name in archive.namelist() if name.endswith(f"/{filename}") or name == filename
    ]
    return sorted(matches, key=len)[0] if matches else None


def _review_candidate(case: PresenceHardCase) -> bool:
    return case.category in {
        "balanced_presence_disagreement",
        "minority_presence_disagreement",
        "framing_sensitive_presence",
    }


def _write_review_csv(path: Path, cases: tuple[PresenceHardCase, ...]) -> None:
    fields = (
        "document_key",
        "reference",
        "category",
        "vote_summary",
        "present_models",
        "absent_models",
        "framing_sensitive_models",
        "text",
        "review_status",
        "present",
        "review_note",
        "clause_id",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "document_key": case.document_key,
                    "reference": case.reference,
                    "category": case.category,
                    "vote_summary": f"{case.present_count} present / {case.absent_count} absent",
                    "present_models": ";".join(case.present_models),
                    "absent_models": ";".join(case.absent_models),
                    "framing_sensitive_models": ";".join(case.framing_sensitive_models),
                    "text": case.text,
                    "review_status": "pending",
                    "present": "",
                    "review_note": "",
                    "clause_id": case.clause_id,
                }
            )


def _render_markdown(report: PresenceHardCaseReport) -> str:
    lines = [
        f"# Applicability presence hard cases — {report.matrix_id}",
        "",
        f"Baseline: `{report.baseline_prompt_id}` / `{report.baseline_cbox_frame}`",
        f"Analyzed clauses: **{report.analyzed_clauses}**",
        "",
        "## Categories",
        "",
        "| Category | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in report.category_counts.items())
    lines.extend(
        [
            "",
            "## Model presence profiles",
            "",
            (
                "| Model | Present | Rate | Ensemble disagreements | Minority present | "
                "Minority absent | Framing sensitive |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.model_profiles:
        lines.append(
            f"| {item.model_id} | {item.present_count}/{item.evaluated_clauses} | "
            f"{item.presence_rate:.3f} | {item.ensemble_disagreement_count} | "
            f"{item.minority_present_count} | {item.minority_absent_count} | "
            f"{item.framing_sensitive_count} |"
        )
    lines.extend(["", "## Ranked hard cases", ""])
    for index, case in enumerate((item for item in report.cases if _review_candidate(item)), 1):
        lines.extend(
            [
                f"### {index}. {case.reference}",
                "",
                f"- Category: `{case.category}`",
                f"- Presence: **{case.present_count} present / {case.absent_count} absent**",
                f"- Disagreement score: `{case.disagreement_score:.3f}`",
                f"- Present models: {', '.join(case.present_models) or '—'}",
                f"- Absent models: {', '.join(case.absent_models) or '—'}",
                f"- Framing-sensitive models: {', '.join(case.framing_sensitive_models) or '—'}",
                "",
                case.text or "_Clause text unavailable._",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
