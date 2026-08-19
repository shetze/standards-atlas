"""Head-to-head challenger qualification derived from a production matrix manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import yaml

from standards_atlas.application.semantic_qualification.qualification_matrix import (
    ChallengerQualificationConfig,
    MatrixExecutionConfig,
    QualificationMatrixManifest,
)


def load_hard_case_selection(
    *, source_manifest: QualificationMatrixManifest, run_archive: Path, sample: str
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Load a reproducible challenger sample from an archived qualification run."""
    if sample != "applicability-conflicts":
        raise ValueError(f"unsupported challenger sample: {sample}")
    with ZipFile(run_archive) as archive:
        metadata = json.loads(archive.read("qualification-run-metadata.json"))
        corpus = metadata.get("corpus", {})
        if corpus.get("id") != source_manifest.corpus_id:
            raise ValueError(
                "hard-case archive corpus does not match challenger manifest: "
                f"{corpus.get('id')!r} != {source_manifest.corpus_id!r}"
            )
        if corpus.get("dataset_version") != source_manifest.dataset_version:
            raise ValueError(
                "hard-case archive dataset version does not match challenger manifest: "
                f"{corpus.get('dataset_version')!r} != {source_manifest.dataset_version!r}"
            )
        matrix_id = metadata.get("qualification_matrix", {}).get("id")
        consensus_name = next(
            (
                name
                for name in archive.namelist()
                if name.endswith(f"consensus/{matrix_id}/consensus-report.json")
            ),
            None,
        )
        if consensus_name is None:
            raise ValueError("qualification archive has no final consensus report")
        report = json.loads(archive.read(consensus_name))

    clause_ids = tuple(
        clause["clause_id"]
        for clause in report.get("clauses", [])
        if _has_applicability_disagreement(clause.get("votes", []))
    )
    if not clause_ids:
        raise ValueError("hard-case archive contains no applicability conflicts")
    selection = {
        "schema_version": "1.0",
        "sample": sample,
        "source_archive": run_archive.name,
        "source_archive_sha256": _sha256(run_archive),
        "source_matrix_id": matrix_id,
        "corpus_id": source_manifest.corpus_id,
        "dataset_version": source_manifest.dataset_version,
        "clause_count": len(clause_ids),
        "clause_ids": list(clause_ids),
    }
    return clause_ids, selection


def write_hard_case_selection(*, selection: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _has_applicability_disagreement(votes: list[dict[str, Any]]) -> bool:
    presence = {bool(vote.get("applicability_present")) for vote in votes}
    present_subtypes = {
        vote.get("applicability_function")
        for vote in votes
        if vote.get("applicability_present") and vote.get("applicability_function")
    }
    return len(presence) > 1 or len(present_subtypes) > 1


def build_challenger_manifest(
    manifest: QualificationMatrixManifest,
) -> QualificationMatrixManifest:
    """Derive an isolated full-matrix run without mutating the production cascade."""
    config = manifest.challenger_qualification
    if not config.enabled:
        raise ValueError("challenger qualification is not enabled in the manifest")
    candidate_pool = {model.id: model for model in (*manifest.models, *config.models)}
    ordered_model_ids: list[str] = []
    for group in config.groups:
        # Run challengers before incumbents so an incompatible new model fails fast
        # instead of wasting a full incumbent pass first.
        for model_id in (*group.challengers, *group.incumbents):
            if model_id not in ordered_model_ids:
                ordered_model_ids.append(model_id)
    models = tuple(candidate_pool[model_id] for model_id in ordered_model_ids)
    consensus = manifest.consensus.model_copy(
        update={
            "adjudication": manifest.consensus.adjudication.model_copy(
                update={"enabled": False, "model_id": None}
            )
        }
    )
    return manifest.model_copy(
        update={
            "matrix_id": f"{manifest.matrix_id}-challengers",
            "repetitions": config.repetitions,
            "models": models,
            "observations": (),
            "review_imports": (),
            "execution": MatrixExecutionConfig(mode="full_matrix"),
            "consensus": consensus,
            "challenger_qualification": ChallengerQualificationConfig(),
        }
    )


def write_challenger_manifest(*, manifest: QualificationMatrixManifest, path: Path) -> Path:
    """Write the derived manifest used by the generic qualification engine."""
    derived = build_challenger_manifest(manifest)
    derived = derived.model_copy(
        update={
            "consensus": derived.consensus.model_copy(
                update={"output_directory": Path("consensus")}
            )
        }
    )
    payload = derived.model_dump(mode="json", exclude_none=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def write_challenger_comparison(
    *, source_manifest: QualificationMatrixManifest, run_directory: Path
) -> tuple[Path, Path]:
    """Compare challenger model-fitness signals with incumbents after a matrix run."""
    metrics_path = run_directory / "qualification-analysis-metrics.json"
    matrix_path = run_directory / "qualification-matrix.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    fitness = {
        item["model_id"]: item
        for item in metrics.get("diagnostics", {}).get("applicability_model_fitness", [])
    }
    performance: dict[str, dict[str, Any]] = {}
    for candidate in matrix.get("candidates", []):
        if not candidate.get("qualification_eligible", False):
            continue
        current = performance.setdefault(
            candidate["model_id"],
            {
                "prediction_success_rates": [],
                "durations": [],
            },
        )
        current["prediction_success_rates"].append(candidate["mean_prediction_success_rate"])
        duration = candidate.get("mean_duration_seconds")
        if duration is not None:
            current["durations"].append(duration)

    groups = []
    for group in source_manifest.challenger_qualification.groups:
        entries = []
        for role, model_ids in (("incumbent", group.incumbents), ("challenger", group.challengers)):
            for model_id in model_ids:
                perf = performance.get(model_id, {})
                rates = perf.get("prediction_success_rates", [])
                durations = perf.get("durations", [])
                entries.append(
                    {
                        "role": role,
                        "model_id": model_id,
                        "applicability_fitness": fitness.get(model_id),
                        "mean_prediction_success_rate": sum(rates) / len(rates) if rates else None,
                        "mean_duration_seconds": sum(durations) / len(durations)
                        if durations
                        else None,
                    }
                )
        groups.append({"id": group.id, "models": entries})

    payload = {
        "schema_version": "1.0",
        "matrix_id": source_manifest.matrix_id,
        "challenger_matrix_id": f"{source_manifest.matrix_id}-challengers",
        "groups": groups,
    }
    json_path = run_directory / "challenger-comparison.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = run_directory / "challenger-comparison.md"
    md_path.write_text(_render_comparison(payload), encoding="utf-8")
    return json_path, md_path


def _render_comparison(payload: dict[str, Any]) -> str:
    lines = [
        f"# Challenger qualification: {payload['matrix_id']}",
        "",
        "The comparison is observational. It does not modify the production cascade, "
        "model weights, or qualification thresholds.",
    ]
    for group in payload["groups"]:
        lines.extend(
            [
                "",
                f"## {group['id']}",
                "",
                "| Role | Model | Conflict none | Presence agreement | Subtype agreement | "
                "Prediction success | Mean duration |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in group["models"]:
            fitness = item.get("applicability_fitness") or {}
            lines.append(
                f"| {item['role']} | `{item['model_id']}` | "
                f"{_rate(fitness.get('conflict_none_rate'))} | "
                f"{_rate(fitness.get('presence_reference_agreement_rate'))} | "
                f"{_rate(fitness.get('subtype_reference_agreement_rate'))} | "
                f"{_rate(item.get('mean_prediction_success_rate'))} | "
                f"{_seconds(item.get('mean_duration_seconds'))} |"
            )
    return "\n".join(lines) + "\n"


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}s"
