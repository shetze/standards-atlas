"""Freeze private context diagnostics and published development state without overwrites."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from standards_atlas import __version__
from standards_atlas.adapters.atlasdata.knowledge_evidence import atomic_write
from standards_atlas.adapters.catalog import YamlStandardCatalogReader
from standards_atlas.adapters.evaluation.archive_receipt import resolve_archive_receipt
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.workflow.report import WorkflowRunReporter

_COUNTERS = (
    "candidates",
    "succeeded",
    "reused",
    "protected",
    "failed",
    "not_candidate",
    "failed_with_retained_value",
    "unresolved_scope_targets",
    "unresolved_reference_targets",
    "routing_corrections",
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _private_fingerprints(payload: object) -> set[str]:
    result = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"private_value", "private_provenance"} and isinstance(value, str):
                digest = value.removeprefix("sha256:")
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError(f"invalid private evidence fingerprint: {value!r}")
                result.add(digest)
            else:
                result.update(_private_fingerprints(value))
    elif isinstance(payload, list):
        for value in payload:
            result.update(_private_fingerprints(value))
    return result


def archive_enrichment_baseline(
    *,
    project_root: Path,
    workspace: Path,
    document_keys: tuple[str, ...],
    manifest_paths: tuple[Path, ...],
    selection: str,
    phase: str,
    reports_root: Path,
    output: Path,
    corpus_count: int | None = None,
    limit: int | None = None,
    strict_context: bool = False,
) -> dict[str, object]:
    """Write a new immutable ZIP and an atomically replaced discovery receipt.

    Only explicit selected document records are included. Archive bytes never
    replace an earlier run. Missing diagnostics/publication outputs are technical
    failures, not an excuse to label a partial collection complete. Context
    quality failures, by contrast, are data and do not block this operation.
    """
    if phase not in {"context", "published"}:
        raise ValueError("baseline phase must be context or published")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", selection):
        raise ValueError("unsafe baseline selection")
    if not document_keys or len(document_keys) != len(set(document_keys)):
        raise ValueError("baseline requires a nonempty, unique document selection")
    if not manifest_paths:
        raise ValueError("baseline requires a standards manifest")
    root = project_root.resolve()
    workspace = (root / workspace).resolve()
    reports_root = root / reports_root
    output = root / output
    bindings = atlasdata_bindings(
        YamlStandardCatalogReader().read(root / manifest_paths[0]), root=root
    )
    if set(document_keys) - bindings.keys():
        raise ValueError("baseline selection includes documents without AtlasData bindings")
    if output.resolve().is_relative_to(workspace / "documents") or any(
        output.resolve().is_relative_to(binding.source.parent / "enrichments")
        for binding in bindings.values()
    ):
        raise ValueError("baseline receipts are private, not canonical/public document files")
    files: dict[str, Path] = {}

    def add(name: str, path: Path, *, required: bool = True) -> None:
        if not path.is_file():
            if required:
                raise ValueError(f"missing baseline input: {path}")
            return
        if name in files and files[name] != path:
            raise ValueError(f"duplicate baseline member: {name}")
        files[name] = path

    documents = []
    evidence = set()
    for key in document_keys:
        canonical = workspace / "documents" / f"{key}.json"
        add(f"documents/{key}.json", canonical)
        report_dir = workspace / "evaluation/context-routing"
        ledger = report_dir / f"{key}-run.json"
        add(f"reports/context/{ledger.name}", ledger)
        report = json.loads(ledger.read_text(encoding="utf-8"))
        if report.get("schema_version") != 1 or report.get("document_key") != key:
            raise ValueError(f"invalid context run ledger: {ledger}")
        summary = report["summary"]
        for counter in _COUNTERS:
            if type(summary.get(counter)) is not int or summary[counter] < 0:
                raise ValueError(f"invalid context counter {counter}: {ledger}")
        documents.append(
            {
                "document_key": key,
                "last_context_invocation": report["completed_at"],
                "status": report["status"],
                "outcomes_complete": report["outcomes_complete"],
                "summary": summary,
            }
        )
        for suffix in ("failures", "unresolved-targets", "routing-corrections"):
            path = report_dir / f"{key}-{suffix}.json"
            # Successful later invocations remove failure/target reports. A missing
            # required report during archival would erase evidence: fail visibly.
            required = (
                suffix == "failures"
                and summary["failed"] > 0
                or suffix == "unresolved-targets"
                and (
                    summary["unresolved_scope_targets"] + summary["unresolved_reference_targets"]
                    > 0
                )
            )
            add(f"reports/context/{path.name}", path, required=bool(required))
        binding = bindings[key]
        add(f"inputs/atlasdata/{binding.family_key}/{binding.source.name}", binding.source)
        if phase == "published":
            companion = binding.enrichments_path
            add(f"public/enrichments/{key}.yaml", companion)
            evidence.update(_private_fingerprints(yaml.safe_load(companion.read_text("utf-8"))))

    for fingerprint in sorted(evidence):
        path = workspace / "knowledge-evidence" / f"{fingerprint}.json"
        add(f"knowledge-evidence/{path.name}", path)
        if _digest(path) != fingerprint:
            raise ValueError(f"corrupt private evidence: {path}")
    for index, manifest in enumerate(manifest_paths):
        add(f"inputs/manifests/{index}-{manifest.name}", root / manifest)
    # Exact source/resources and explicit configuration files, not environment
    # values, MCP credentials, model weights or unrelated private workspace data.
    for path in sorted((root / "src/standards_atlas").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            add(f"code/{path.relative_to(root).as_posix()}", path)
    for name in (
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "cfg/context-enrichment.yaml",
        "cfg/llm.yaml",
    ):
        add(f"code/{name}", root / name, required=False)
    # Include nondefault context profiles explicitly recorded by document commands.
    for key in document_keys:
        report = json.loads((workspace / f"evaluation/context-routing/{key}-run.json").read_text())
        path = root / report["config"]
        add(f"inputs/context-config/{key}.yaml", path)
        if _digest(path) != report["config_sha256"]:
            raise ValueError(f"context configuration changed since last invocation for {key}")
    if phase == "published":
        for name in (
            "archive.json",
            "adopt.json",
            "export.json",
            "reimport.json",
            "cbox.json",
            "context-baseline.json",
        ):
            add(f"reports/workflow/{name}", reports_root / name)
        qualification = resolve_archive_receipt(reports_root / "archive.json")
        add("qualification/run.zip", qualification)

    if any(output.resolve() == path.resolve() for path in files.values()):
        raise ValueError("baseline receipt must not overwrite an archived input")
    totals = {key: sum(doc["summary"][key] for doc in documents) for key in _COUNTERS}
    timestamp = datetime.now(UTC)
    run_id = f"{phase}-{timestamp:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}"
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "phase": phase,
        "selection": selection,
        "created_at": timestamp.isoformat(),
        "status": "completed_with_context_failures" if totals["failed"] else "completed",
        "semantically_verified": False,
        "standards_atlas_version": __version__,
        "python_version": platform.python_version(),
        "git": WorkflowRunReporter._git_identity(root),
        "context_failure_policy": "strict" if strict_context else "report_and_continue",
        "counting_basis": "last recorded per-document context invocation; see timestamps",
        "coverage": {
            "context": "all context candidates of selected documents",
            "semantic": (
                "sampled" if corpus_count is not None or limit is not None else "all_eligible"
            ),
            "corpus_count": corpus_count,
            "limit": limit,
        },
        "summary": {"documents": len(documents), **totals},
        "documents": documents,
    }
    folder = workspace / "evaluation/baselines/enrichments" / selection
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{run_id}.zip"
    fd, temporary = tempfile.mkstemp(prefix=".baseline-", dir=folder)
    os.close(fd)
    try:
        inventory = []
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for name, path in sorted(files.items()):
                # Hash the exact bytes that are written, not a second potentially
                # changed read of a mutable diagnostics/document file.
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as dest:
                    while chunk := source.read(1024 * 1024):
                        dest.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                inventory.append({"path": name, "size": size, "sha256": digest.hexdigest()})
            archive.writestr("baseline.json", _json_bytes(summary))
            archive.writestr("README.md", _markdown(summary))
            archive.writestr(
                "manifest.json",
                _json_bytes(
                    {
                        "schema_version": 1,
                        "files": [
                            *inventory,
                            {
                                "path": "baseline.json",
                                "size": len(_json_bytes(summary)),
                                "sha256": hashlib.sha256(_json_bytes(summary)).hexdigest(),
                            },
                            {
                                "path": "README.md",
                                "size": len(_markdown(summary).encode()),
                                "sha256": hashlib.sha256(_markdown(summary).encode()).hexdigest(),
                            },
                        ],
                    }
                ),
            )
        # Exclusive publication: even a colliding run ID cannot replace a baseline.
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    receipt = {**summary, "archive": str(target), "archive_sha256": _digest(target)}
    atomic_write(output, _json_bytes(receipt), private=True)
    return receipt


def _markdown(payload: dict) -> str:
    totals = payload["summary"]
    lines = [
        "# Enrichment development baseline",
        "",
        f"Phase: {payload['phase']}. Status: {payload['status']}.",
        "",
        "Not a semantic approval or a claim of complete target resolution.",
        "Counts describe the last document invocations, including reused checkpoints.",
        "Failed attempts with retained older values are NOT current successes.",
        "",
        f"Documents: {totals['documents']}; candidates: {totals['candidates']}; "
        f"failed: {totals['failed']}; "
        f"retained older values: {totals['failed_with_retained_value']}.",
        "",
        "| Document | Success | Reused | Protected | Failed | Unresolved scopes / refs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for doc in payload["documents"]:
        s = doc["summary"]
        lines.append(
            f"| {doc['document_key']} | {s['succeeded']} | {s['reused']} | {s['protected']} | "
            f"{s['failed']} | {s['unresolved_scope_targets']} / "
            f"{s['unresolved_reference_targets']} |"
        )
    lines.extend(
        [
            "",
            "The archive is private and can contain licensed source text and rejected answers.",
            "It excludes source PDFs, Docling inputs, model weights, environment secrets and caches.",
            "Use manifest.json to verify every payload before comparison or manual restore.",
            "",
        ]
    )
    return "\n".join(lines)
