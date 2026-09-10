"""Verify a frozen context baseline before continuing with qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_context_baseline(
    *,
    project_root: Path,
    workspace: Path,
    document_keys: tuple[str, ...],
    manifest_paths: tuple[Path, ...],
    selection: str,
    receipt: Path,
    corpus_count: int | None = None,
    limit: int | None = None,
    strict_context: bool = False,
) -> dict[str, object]:
    """Read only: refuse drift rather than restore files or silently rerun context.

    Source code may have changed to fix the failed downstream stage. The original
    code remains archived; documents, reports, context configuration, selected
    AtlasData and manifests must still match the frozen context exactly.
    """
    root = project_root.resolve()
    workspace = root / workspace
    payload = json.loads((root / receipt).read_text(encoding="utf-8"))
    archive_path = root / payload["archive"]
    if _digest(archive_path) != payload["archive_sha256"]:
        raise ValueError("context baseline archive checksum mismatch")
    try:
        with ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate context baseline archive members")
            inventory = json.loads(archive.read("manifest.json"))["files"]
            members = {item["path"]: item for item in inventory}
            if len(members) != len(inventory) or set(names) != {*members, "manifest.json"}:
                raise ValueError("incomplete context baseline inventory")
            for name, record in members.items():
                with archive.open(name) as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                if (
                    checksum != record["sha256"]
                    or archive.getinfo(name).file_size != record["size"]
                ):
                    raise ValueError(f"corrupt context baseline member: {name}")
            summary = json.loads(archive.read("baseline.json"))
            receipt_summary = {
                key: value
                for key, value in payload.items()
                if key not in {"archive", "archive_sha256"}
            }
            if summary != receipt_summary:
                raise ValueError("context baseline receipt does not match archived summary")
    except BadZipFile as exc:
        raise ValueError(f"invalid context baseline ZIP: {archive_path}") from exc
    if (
        summary["schema_version"] != 1
        or summary["phase"] != "context"
        or summary["selection"] != selection
    ):
        raise ValueError("context baseline belongs to another phase or selection")
    archived_keys = [doc["document_key"] for doc in summary["documents"]]
    if (
        len(archived_keys) != len(document_keys)
        or set(archived_keys) != set(document_keys)
        or len(document_keys) != len(set(document_keys))
        or not document_keys
    ):
        raise ValueError("context baseline document selection mismatch")
    coverage = summary["coverage"]
    if coverage["corpus_count"] != corpus_count or coverage["limit"] != limit:
        raise ValueError("context baseline sampling settings mismatch")
    if strict_context and summary["summary"]["failed"]:
        raise ValueError("strict context policy rejects failures in the saved baseline")

    def unchanged(name: str, current: Path, *, required: bool = True) -> None:
        archived = members.get(name)
        if archived is None and not current.exists() and not required:
            return
        if archived is None or not current.is_file() or _digest(current) != archived["sha256"]:
            raise ValueError(
                f"context baseline input changed or missing: {current}; "
                "resume refused without modifying the saved baseline"
            )

    for index, manifest in enumerate(manifest_paths):
        unchanged(f"inputs/manifests/{index}-{manifest.name}", root / manifest)
    archived_manifests = {name for name in members if name.startswith("inputs/manifests/")}
    if len(archived_manifests) != len(manifest_paths) or not manifest_paths:
        raise ValueError("context baseline manifest selection mismatch")
    bindings = atlasdata_bindings(
        YamlStandardCatalogReader().read(root / manifest_paths[0]),
        root=root,
    )
    for key in document_keys:
        unchanged(f"documents/{key}.json", workspace / "documents" / f"{key}.json")
        report_dir = workspace / "evaluation/context-routing"
        ledger = report_dir / f"{key}-run.json"
        for suffix in ("run", "failures", "unresolved-targets", "routing-corrections"):
            name = f"{key}-{suffix}.json"
            unchanged(f"reports/context/{name}", report_dir / name, required=suffix == "run")
        config = json.loads(ledger.read_text(encoding="utf-8"))["config"]
        unchanged(f"inputs/context-config/{key}.yaml", root / config)
        binding = bindings[key]
        unchanged(f"inputs/atlasdata/{binding.family_key}/{binding.source.name}", binding.source)
    return payload
