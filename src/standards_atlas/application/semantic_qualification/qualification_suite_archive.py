"""Immutable suite-level archives for routed multi-task qualification runs."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from standards_atlas import __version__
from standards_atlas.shared.hashing import sha256_file

SUITE_ARCHIVE_SCHEMA_VERSION = "1.0"
SUITE_RUN_METADATA_SCHEMA_VERSION = "1.0"
SUITE_RUN_INDEX_SCHEMA_VERSION = "1.0"
_SUITE_RUN_RE = re.compile(r"^qualification-suite-run-(\d+)\.zip$")


def next_qualification_suite_run_id(archive_directory: Path) -> str:
    """Return the next human-readable immutable suite run identifier."""

    sequences: list[int] = []
    if archive_directory.exists():
        for path in archive_directory.glob("qualification-suite-run-*.zip"):
            match = _SUITE_RUN_RE.match(path.name)
            if match is not None:
                sequences.append(int(match.group(1)))
    return f"qualification-suite-run-{max(sequences, default=0) + 1:03d}"


def create_qualification_suite_archive(
    *,
    archive_directory: Path,
    suite_run_id: str,
    suite_manifest_path: Path,
    routing_manifest_path: Path,
    qualification_archives: Iterable[Path],
) -> Path:
    """Archive one routed qualification suite and references to its five task runs."""

    archive_directory.mkdir(parents=True, exist_ok=True)
    archive_path = archive_directory / f"{suite_run_id}.zip"
    if archive_path.exists():
        raise FileExistsError(f"qualification suite archive already exists: {archive_path}")

    suite_payload = yaml.safe_load(suite_manifest_path.read_text(encoding="utf-8")) or {}
    routing_payload = yaml.safe_load(routing_manifest_path.read_text(encoding="utf-8")) or {}
    expected_count = len(tuple(suite_payload.get("qualification_manifests", ())))

    run_entries: list[dict[str, Any]] = []
    aggregate_by_task: dict[str, Any] = {}
    for path in qualification_archives:
        with zipfile.ZipFile(path) as run_zip:
            metadata = json.loads(run_zip.read("qualification-run-metadata.json"))
        if metadata.get("suite_run_id") != suite_run_id:
            raise ValueError(
                f"qualification archive {path.name} belongs to suite "
                f"{metadata.get('suite_run_id')!r}, expected {suite_run_id!r}"
            )
        routing = metadata.get("routing") or {}
        task = routing.get("task") or (metadata.get("qualification_matrix") or {}).get("task")
        entry = {
            "archive_id": metadata["archive_id"],
            "file": path.name,
            "sha256": sha256_file(path),
            "matrix_id": (metadata.get("qualification_matrix") or {}).get("id"),
            "task": task,
            "routing": routing,
        }
        run_entries.append(entry)
        if task:
            aggregate_by_task[str(task)] = routing.get("aggregate")

    run_entries.sort(key=lambda item: str(item.get("task") or ""))
    if expected_count and len(run_entries) != expected_count:
        raise ValueError(
            f"qualification suite {suite_run_id} requires {expected_count} task runs, "
            f"found {len(run_entries)}"
        )

    generated_at = datetime.now(UTC).isoformat()
    metadata = {
        "schema_version": SUITE_RUN_METADATA_SCHEMA_VERSION,
        "suite_run_id": suite_run_id,
        "created_at": generated_at,
        "standards_atlas": {"version": __version__},
        "suite": {
            "id": suite_payload.get("suite_id"),
            "version": suite_payload.get("version"),
            "manifest_sha256": sha256_file(suite_manifest_path),
        },
        "routing_contract": {
            "id": (routing_payload.get("contract") or {}).get("id"),
            "version": (routing_payload.get("contract") or {}).get("version"),
            "manifest_sha256": sha256_file(routing_manifest_path),
        },
        "qualification_runs": run_entries,
        "routing_aggregates": aggregate_by_task,
    }
    metadata_bytes = _json_bytes(metadata)

    members = {
        "configuration/qualification-suite-manifest.yaml": suite_manifest_path,
        "configuration/routing-manifest.yaml": routing_manifest_path,
    }
    files = [
        {"path": member, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for member, path in sorted(members.items())
    ]
    files.append(
        {
            "path": "qualification-suite-run-metadata.json",
            "sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "size_bytes": len(metadata_bytes),
        }
    )
    archive_manifest = {
        "schema_version": SUITE_ARCHIVE_SCHEMA_VERSION,
        "suite_run_id": suite_run_id,
        "standards_atlas_version": __version__,
        "generated_at": generated_at,
        "files": sorted(files, key=lambda item: item["path"]),
        "qualification_runs": [
            {"archive_id": item["archive_id"], "file": item["file"], "sha256": item["sha256"]}
            for item in run_entries
        ],
    }

    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, path in sorted(members.items()):
            archive.write(path, member)
        archive.writestr("qualification-suite-run-metadata.json", metadata_bytes)
        archive.writestr("archive-manifest.json", _json_bytes(archive_manifest))

    _update_suite_index(archive_directory, archive_path, metadata)
    return archive_path


def qualification_archives_for_suite(
    archive_directory: Path, suite_run_id: str
) -> tuple[Path, ...]:
    """Resolve qualification run archives correlated with one suite run."""

    index_path = archive_directory / "qualification-run-index.json"
    if not index_path.is_file():
        return ()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    archives = payload.get("archives", []) if isinstance(payload, dict) else []
    return tuple(
        archive_directory / str(item["file"])
        for item in archives
        if isinstance(item, dict) and item.get("suite_run_id") == suite_run_id
    )


def _update_suite_index(archive_dir: Path, archive_path: Path, metadata: dict[str, Any]) -> None:
    path = archive_dir / "qualification-suite-run-index.json"
    archives: list[dict[str, Any]] = []
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(current, dict) and isinstance(current.get("archives"), list):
            archives.extend(item for item in current["archives"] if isinstance(item, dict))
    sequence = int(str(metadata["suite_run_id"]).rsplit("-", 1)[1])
    archives = [item for item in archives if int(item.get("sequence_number", -1)) != sequence]
    archives.append(
        {
            "sequence_number": sequence,
            "suite_run_id": metadata["suite_run_id"],
            "file": archive_path.name,
            "sha256": sha256_file(archive_path),
            "created_at": metadata["created_at"],
            "suite_id": metadata["suite"]["id"],
            "suite_version": metadata["suite"]["version"],
            "qualification_run_count": len(metadata["qualification_runs"]),
        }
    )
    archives.sort(key=lambda item: int(item["sequence_number"]))
    payload = {
        "schema_version": SUITE_RUN_INDEX_SCHEMA_VERSION,
        "latest": sequence,
        "archives": archives,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_bytes(_json_bytes(payload))
    temporary.replace(path)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
