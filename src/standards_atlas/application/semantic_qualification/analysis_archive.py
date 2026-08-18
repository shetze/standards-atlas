"""Versioned analysis artifacts for qualification-matrix runs."""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from standards_atlas import __version__
from standards_atlas.application.semantic_qualification.consensus import ConsensusReport
from standards_atlas.shared.hashing import sha256_file

ANALYSIS_ARCHIVE_SCHEMA_VERSION = "1.0"


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
) -> Path:
    """Create a versioned ZIP with reports, metrics, provenance, and hashes."""
    archive_dir = output_directory / matrix_id
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_name = (
        f"{matrix_id}-qualification-analysis-v{ANALYSIS_ARCHIVE_SCHEMA_VERSION}"
        f"-standards-atlas-{__version__}.zip"
    )
    archive_path = archive_dir / archive_name

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

    archive_manifest = {
        "schema_version": ANALYSIS_ARCHIVE_SCHEMA_VERSION,
        "standards_atlas_version": __version__,
        "matrix_id": matrix_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": [
            {
                "path": member,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for member, path in sorted(deduplicated.items())
        ],
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, path in sorted(deduplicated.items()):
            archive.write(path, member)
        archive.writestr(
            "archive-manifest.json",
            json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n",
        )
    return archive_path


def _member_name(path: Path, output_directory: Path, manifest_path: Path) -> str:
    if path == manifest_path:
        return "configuration/qualification-manifest.yaml"
    try:
        return str(path.relative_to(output_directory))
    except ValueError:
        return f"reports/{path.name}"
