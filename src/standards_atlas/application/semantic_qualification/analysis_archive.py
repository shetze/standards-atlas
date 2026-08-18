"""Immutable analysis artifacts for qualification-matrix runs."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from standards_atlas import __version__
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.shared.hashing import sha256_file

ANALYSIS_ARCHIVE_SCHEMA_VERSION = "1.1"
QUALIFICATION_RUN_METADATA_SCHEMA_VERSION = "1.0"
QUALIFICATION_RUN_INDEX_SCHEMA_VERSION = "1.0"
_QUALIFICATION_RUN_RE = re.compile(r"^qualification-run-(\d+)\.zip$")


def write_cascade_provenance(
    *,
    output_directory: Path,
    matrix_id: str,
    manifest_path: Path,
    run_mode: str,
    stages: list[dict[str, Any]],
) -> Path:
    """Persist clause-level stage entry/exit reasons and resolution deltas."""
    path = output_directory / matrix_id / "cascade-provenance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ANALYSIS_ARCHIVE_SCHEMA_VERSION,
        "matrix_id": matrix_id,
        "standards_atlas_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "run_mode": run_mode,
        "stages": stages,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_analysis_metrics(
    *,
    report: ConsensusReport,
    cascade_stages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build stable aggregate metrics used for qualification-result analysis."""
    review_reasons = Counter(
        reason for clause in report.clauses for reason in clause.review_reasons
    )
    structural_observed = sum(
        clause.applicability_structural_conflict_observed for clause in report.clauses
    )
    structural_unresolved = sum(
        clause.applicability_structural_conflict_unresolved for clause in report.clauses
    )
    return {
        "schema_version": ANALYSIS_ARCHIVE_SCHEMA_VERSION,
        "matrix_id": report.matrix_id,
        "corpus_id": report.corpus_id,
        "standards_atlas_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "clause_count": report.clause_count,
        "review_count": report.review_count,
        "categories": report.categories,
        "dimension_categories": report.dimension_categories,
        "overall_statuses": report.overall_statuses,
        "participation_distribution": report.participation_distribution,
        "resolution_sources": report.resolution_sources,
        "review_reasons": dict(sorted(review_reasons.items())),
        "structural_conflicts": {
            "observed": structural_observed,
            "unresolved": structural_unresolved,
            "resolved_during_cascade": max(0, structural_observed - structural_unresolved),
        },
        "cascade": {
            "stage_count": len(cascade_stages),
            "stages": [
                {
                    "stage_id": stage["stage_id"],
                    "entered_clause_count": stage["entered_clause_count"],
                    "unresolved_clause_count": stage["unresolved_clause_count"],
                    "entry_reason_counts": stage["entry_reason_counts"],
                    "exit_reason_counts": stage["exit_reason_counts"],
                    "resolution_counts_before": stage["resolution_counts_before"],
                    "resolution_counts_after": stage["resolution_counts_after"],
                    "newly_resolved_counts": stage["newly_resolved_counts"],
                }
                for stage in cascade_stages
            ],
        },
    }


def write_analysis_metrics(
    *, output_directory: Path, matrix_id: str, metrics: dict[str, Any]
) -> Path:
    path = output_directory / matrix_id / "qualification-analysis-metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def create_analysis_archive(
    *,
    output_directory: Path,
    matrix_id: str,
    manifest_path: Path,
    core_paths: Iterable[Path],
    cascade_directory: Path | None = None,
    analysis_metrics: dict[str, Any] | None = None,
    matrix_passed: bool | None = None,
) -> Path:
    """Create an immutable, sequentially numbered qualification-run ZIP."""
    archive_dir = output_directory.parent
    archive_dir.mkdir(parents=True, exist_ok=True)
    sequence_number = _next_sequence_number(archive_dir)
    archive_id = f"qualification-run-{sequence_number:03d}"
    archive_path = archive_dir / f"{archive_id}.zip"
    if archive_path.exists():
        raise FileExistsError(f"qualification run archive already exists: {archive_path}")

    generated_at = datetime.now(UTC).isoformat()
    manifest_payload = _load_manifest_payload(manifest_path)
    metadata = _build_run_metadata(
        archive_id=archive_id,
        sequence_number=sequence_number,
        generated_at=generated_at,
        manifest_path=manifest_path,
        manifest_payload=manifest_payload,
        analysis_metrics=analysis_metrics,
        matrix_passed=matrix_passed,
    )
    metadata_bytes = _json_bytes(metadata)

    members: list[tuple[Path, str]] = []
    for path in core_paths:
        if path.exists() and path.is_file():
            members.append((path, _member_name(path, output_directory, manifest_path)))
    if manifest_path.exists():
        members.append((manifest_path, "configuration/qualification-manifest.yaml"))
    if cascade_directory is not None and cascade_directory.is_dir():
        for path in sorted(cascade_directory.rglob("*.json")):
            if path.is_file():
                members.append((path, f"cascade/{path.relative_to(cascade_directory)}"))

    deduplicated: dict[str, Path] = {}
    for path, member in members:
        deduplicated.setdefault(member, path)

    file_entries = [
        {
            "path": member,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for member, path in sorted(deduplicated.items())
    ]
    file_entries.append(
        {
            "path": "qualification-run-metadata.json",
            "sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "size_bytes": len(metadata_bytes),
        }
    )
    archive_manifest = {
        "schema_version": ANALYSIS_ARCHIVE_SCHEMA_VERSION,
        "archive_id": archive_id,
        "sequence_number": sequence_number,
        "standards_atlas_version": __version__,
        "matrix_id": matrix_id,
        "generated_at": generated_at,
        "files": sorted(file_entries, key=lambda item: item["path"]),
    }

    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, path in sorted(deduplicated.items()):
            archive.write(path, member)
        archive.writestr("qualification-run-metadata.json", metadata_bytes)
        archive.writestr("archive-manifest.json", _json_bytes(archive_manifest))

    _update_run_index(
        archive_dir=archive_dir,
        archive_path=archive_path,
        metadata=metadata,
    )
    return archive_path


def _next_sequence_number(archive_dir: Path) -> int:
    sequences = []
    for path in archive_dir.glob("qualification-run-*.zip"):
        match = _QUALIFICATION_RUN_RE.match(path.name)
        if match is not None:
            sequences.append(int(match.group(1)))
    return max(sequences, default=0) + 1


def _load_manifest_payload(manifest_path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"qualification manifest must contain a mapping: {manifest_path}")
    return payload


def _build_run_metadata(
    *,
    archive_id: str,
    sequence_number: int,
    generated_at: str,
    manifest_path: Path,
    manifest_payload: dict[str, Any],
    analysis_metrics: dict[str, Any] | None,
    matrix_passed: bool | None,
) -> dict[str, Any]:
    prompts = [
        {
            "id": item.get("id"),
            "prompt_version": item.get("prompt_version"),
        }
        for item in manifest_payload.get("prompts", [])
        if isinstance(item, dict)
    ]
    models = [
        {
            "id": item.get("id"),
            "provider": item.get("provider"),
            "model_ref": item.get("model_ref"),
        }
        for item in manifest_payload.get("models", [])
        if isinstance(item, dict)
    ]
    result = None
    if analysis_metrics is not None:
        result = {
            "passed": matrix_passed,
            "clause_count": analysis_metrics.get("clause_count"),
            "review_count": analysis_metrics.get("review_count"),
            "categories": analysis_metrics.get("categories"),
            "dimension_categories": analysis_metrics.get("dimension_categories"),
            "overall_statuses": analysis_metrics.get("overall_statuses"),
        }
    return {
        "schema_version": QUALIFICATION_RUN_METADATA_SCHEMA_VERSION,
        "analysis_archive_schema_version": ANALYSIS_ARCHIVE_SCHEMA_VERSION,
        "archive_id": archive_id,
        "sequence_number": sequence_number,
        "created_at": generated_at,
        "standards_atlas": {"version": __version__},
        "qualification_matrix": {
            "id": manifest_payload.get("matrix_id"),
            "manifest_type": manifest_payload.get("manifest_type"),
            "schema_version": manifest_payload.get("schema_version"),
            "task_version": manifest_payload.get("task_version"),
            "dataset_version": manifest_payload.get("dataset_version"),
        },
        "corpus": {
            "id": manifest_payload.get("corpus_id"),
            "task_version": manifest_payload.get("task_version"),
            "dataset_version": manifest_payload.get("dataset_version"),
        },
        "prompts": prompts,
        "models": models,
        "inputs": {
            "qualification_manifest": {
                "path": str(manifest_path),
                "sha256": sha256_file(manifest_path),
            }
        },
        "result": result,
    }


def _update_run_index(
    *,
    archive_dir: Path,
    archive_path: Path,
    metadata: dict[str, Any],
) -> Path:
    index_path = archive_dir / "qualification-run-index.json"
    archives: list[dict[str, Any]] = []
    if index_path.exists():
        current = json.loads(index_path.read_text(encoding="utf-8"))
        current_archives = current.get("archives", []) if isinstance(current, dict) else []
        if isinstance(current_archives, list):
            archives.extend(item for item in current_archives if isinstance(item, dict))

    sequence_number = int(metadata["sequence_number"])
    archives = [
        item for item in archives if int(item.get("sequence_number", -1)) != sequence_number
    ]
    result = metadata.get("result") or {}
    matrix = metadata.get("qualification_matrix") or {}
    corpus = metadata.get("corpus") or {}
    archives.append(
        {
            "sequence_number": sequence_number,
            "archive_id": metadata["archive_id"],
            "file": archive_path.name,
            "sha256": sha256_file(archive_path),
            "created_at": metadata["created_at"],
            "standards_atlas_version": metadata["standards_atlas"]["version"],
            "matrix_id": matrix.get("id"),
            "corpus_id": corpus.get("id"),
            "clause_count": result.get("clause_count"),
            "review_count": result.get("review_count"),
            "passed": result.get("passed"),
        }
    )
    archives.sort(key=lambda item: int(item["sequence_number"]))
    payload = {
        "schema_version": QUALIFICATION_RUN_INDEX_SCHEMA_VERSION,
        "latest": sequence_number,
        "archives": archives,
    }
    temp_path = index_path.with_suffix(".json.tmp")
    temp_path.write_bytes(_json_bytes(payload))
    temp_path.replace(index_path)
    return index_path


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _member_name(path: Path, output_directory: Path, manifest_path: Path) -> str:
    if path == manifest_path:
        return "configuration/qualification-manifest.yaml"
    try:
        return str(path.relative_to(output_directory))
    except ValueError:
        return f"reports/{path.name}"
