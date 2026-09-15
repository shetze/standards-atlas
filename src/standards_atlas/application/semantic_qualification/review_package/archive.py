"""Deterministic, bounded review snapshots with offline source/history verification.

Archives contain frozen review evidence, not the potentially huge original qualification
runs. No extraction, model invocation, human decision or publication is performed here.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar, Literal

from pydantic import Field

from standards_atlas.application.schema import require_supported_schema

from .candidates import safe_read
from .model import Digest, NonBlank, ReviewModel, ReviewPackage, ReviewState, WorkbenchEvidence
from .service import load_review
from .sources import fingerprint
from .storage import _json_bytes, _sync_directory, output_is_separate, review_lock
from .validation import review_report, seal, verify_package, verify_state
from .workbench import verify_workbench_evidence, workbench_from_files, workbench_summary

MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 20_000
MANIFEST = "archive-manifest.json"


class ArchiveMember(ReviewModel):
    sha256: Digest
    size: int = Field(ge=0, strict=True)


class ReviewArchiveManifest(ReviewModel):
    SCHEMA_FAMILY: ClassVar[str] = "review-archive"

    schema_version: Literal[1] = 1
    kind: Literal["review-archive"] = "review-archive"
    package_root: NonBlank
    package_sha256: Digest
    state_sha256: Digest
    audit_sha256: Digest
    input_bindings: dict[str, str]
    files: dict[str, ArchiveMember] = Field(min_length=2)
    archive_sha256: Digest


@dataclass(frozen=True)
class ReviewArchiveSnapshot:
    manifest: ReviewArchiveManifest
    package: ReviewPackage
    state: ReviewState
    workbench: WorkbenchEvidence

    def summary(self) -> dict:
        return {
            "archive_sha256": self.manifest.archive_sha256,
            "package_sha256": self.package.package_sha256,
            "state_sha256": self.state.state_sha256,
            "member_count": len(self.manifest.files),
            "uncompressed_bytes": sum(v.size for v in self.manifest.files.values()),
            "workbench": workbench_summary(self.workbench),
            "report": review_report(self.package, self.state),
            "frozen_evidence_verified": True,
            "live_sources_verified": False,
            "human_decisions_added": 0,
        }


def _safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or any(part in {".", ".."} for part in name.split("/"))
        or path.as_posix() != name
        or "\\" in name
        or ":" in name
        or "\x00" in name
    ):
        raise ValueError("unsafe review archive member name")


def _package_name(name: str) -> bool:
    if name in {
        "review-package.json",
        "review-state.json",
        "README.md",
        "review-queue.json",
        "preparation-lineage.json",
        "preparation-selection.json",
        "preparation-index.json",
        "preparation-parent-state.json",
        "preparation-parent-workbench.json",
        "preparation-parent-package.json",
        "workbench/state.json",
    }:
        return True
    return bool(
        re.fullmatch(
            r"(?:history/[0-9a-f]{64}\.json|workbench/history/[0-9a-f]{64}\.json|"
            r"preparation/indexes/[0-9a-f]{64}/index\.json|"
            r"preparation/selections/[0-9a-f]{64}/selection\.json)",
            name,
        )
    )


def _bounded_read(path: Path) -> bytes:
    if not path.is_file() or path.stat().st_size > MAX_MEMBER_BYTES:
        raise ValueError(f"review snapshot member is not a bounded regular file: {path}")
    raw = safe_read(path)
    if len(raw) > MAX_MEMBER_BYTES:
        raise ValueError("review snapshot member grew beyond size limit")
    return raw


def snapshot_files(root: Path) -> dict[str, bytes]:
    """Caller holds .review.lock; every other lock, symlink or unknown file fails closed."""
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("unsafe review snapshot root")
    result = {}
    total = 0
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError("symlink in review snapshot")
        if name == ".review.lock":
            continue  # This is the caller's lock, deliberately not a transported stale lock.
        if path.is_dir():
            continue
        if not _package_name(name):
            raise ValueError(f"unexpected/active-writer file in review snapshot: {name}")
        raw = _bounded_read(path)
        result[name] = raw
        total += len(raw)
        if total > MAX_ARCHIVE_BYTES or len(result) > MAX_MEMBERS:
            raise ValueError("review snapshot exceeds archive limits")
    return result


def _verify_review_files(files: dict[str, bytes], package, state) -> WorkbenchEvidence:
    verify_package(package)
    verify_state(package, state)
    for name, raw in files.items():
        if not _package_name(name):
            raise ValueError(f"unexpected review package file: {name}")
        if name.startswith("history/"):
            previous = ReviewState.model_validate_json(raw)
            verify_state(package, previous)
            if (
                name != f"history/{previous.state_sha256}.json"
                or previous.revision >= state.revision
                or previous.proposals != state.proposals[: len(previous.proposals)]
                or previous.decisions != state.decisions[: len(previous.decisions)]
            ):
                raise ValueError("review history is not a bound prefix of the current decisions")
    if "preparation-parent-package.json" in files:
        parent = ReviewPackage.model_validate_json(files["preparation-parent-package.json"])
        previous = ReviewState.model_validate_json(files["preparation-parent-state.json"])
        verify_package(parent)
        verify_state(parent, previous)
        lineage = json.loads(files["preparation-lineage.json"])
        if (
            parent.population != package.population
            or parent.rules != package.rules
            or lineage["parent_package_sha256"] != parent.package_sha256
            or lineage["parent_state_sha256"] != previous.state_sha256
            or previous.proposals != state.proposals[: len(previous.proposals)]
            or previous.decisions != state.decisions[: len(previous.decisions)]
            or not set(parent.known_development_ids) <= set(package.known_development_ids)
            or {c.example_id for c in parent.cases if c.split == "holdout"}
            != {c.example_id for c in package.cases if c.split == "holdout"}
        ):
            raise ValueError("materialized review lost parent sources, membership or human history")
        if "preparation-parent-workbench.json" in files:
            audit = WorkbenchEvidence.model_validate_json(
                files["preparation-parent-workbench.json"]
            )
            verify_workbench_evidence(audit, parent, previous)
            current = workbench_from_files(files, package, state)
            if current.state.exposures[: len(audit.state.exposures)] != audit.state.exposures:
                raise ValueError("materialized review lost parent Holdout exposure history")
    if "review-queue.json" in files:
        queue = json.loads(files["review-queue.json"])
        order = [row["example_id"] for row in queue["rows"]]
        if order != [c.example_id for c in package.cases]:
            raise ValueError("archived review queue differs from the frozen selected order")
    return workbench_from_files(files, package, state)


def build_archive_bytes(root: Path, package, state) -> tuple[bytes, ReviewArchiveSnapshot]:
    """Build under the caller's review lock. Source-only corpus and rules are already frozen."""
    local = snapshot_files(root)
    if (
        ReviewPackage.model_validate_json(local["review-package.json"]) != package
        or ReviewState.model_validate_json(local["review-state.json"]) != state
    ):
        raise ValueError("review snapshot changed while being captured")
    workbench = _verify_review_files(local, package, state)
    files = {"package/" + name: raw for name, raw in local.items()}
    inputs = {}
    for origin, digest in sorted(package.input_files.items()):
        path = Path(origin)
        if path.is_relative_to(root.resolve()):
            name = "package/" + path.relative_to(root.resolve()).as_posix()
            if name not in files:
                raise ValueError("bound local review input missing from snapshot")
            raw = files[name]
        else:
            raw = _bounded_read(path)
            name = "inputs/" + digest
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"review input changed before archival: {origin}")
        files[name] = raw
        inputs[origin] = name
    if sum(map(len, files.values())) > MAX_ARCHIVE_BYTES or len(files) > MAX_MEMBERS:
        raise ValueError("review snapshot and bound inputs exceed archive limits")
    manifest = seal(
        ReviewArchiveManifest,
        {
            "package_root": str(root.resolve()),
            "package_sha256": package.package_sha256,
            "state_sha256": state.state_sha256,
            "audit_sha256": workbench.audit_sha256,
            "input_bindings": inputs,
            "files": {
                name: {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
                for name, raw in sorted(files.items())
            },
        },
        "archive_sha256",
    )
    raw = encode_archive({**files, MANIFEST: _json_bytes(manifest.model_dump(mode="json"))})
    checked = verify_archive_bytes(raw)
    return raw, checked


def encode_archive(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(files.items()):
            _safe_name(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return stream.getvalue()


def verify_archive_bytes(raw: bytes) -> ReviewArchiveSnapshot:
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("review archive exceeds compressed size limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES:
            raise ValueError("review archive exceeds inventory/expanded size limit")
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError("duplicate review archive member")
        for info in infos:
            _safe_name(info.filename)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (
                info.is_dir()
                or mode not in {0, stat.S_IFREG}
                or info.file_size > MAX_MEMBER_BYTES
                or info.flag_bits & 1
                or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            ):
                raise ValueError("unsafe or oversized review archive member")
        files = {i.filename: archive.read(i) for i in infos}
    if MANIFEST not in files:
        raise ValueError("review archive has no manifest")
    manifest = ReviewArchiveManifest.model_validate_json(files.pop(MANIFEST))
    require_supported_schema("review-archive", manifest.schema_version)
    if fingerprint(manifest, "archive_sha256") != manifest.archive_sha256:
        raise ValueError("review archive manifest fingerprint mismatch")
    if set(files) != set(manifest.files):
        raise ValueError("review archive inventory differs from manifest")
    for name, expected in manifest.files.items():
        value = files[name]
        if len(value) != expected.size or hashlib.sha256(value).hexdigest() != expected.sha256:
            raise ValueError(f"review archive member fingerprint mismatch: {name}")
    if any(
        not (n.startswith("package/") or re.fullmatch(r"inputs/[0-9a-f]{64}", n)) for n in files
    ):
        raise ValueError("unexpected review archive payload")
    local = {n.removeprefix("package/"): v for n, v in files.items() if n.startswith("package/")}
    try:
        package = ReviewPackage.model_validate_json(local["review-package.json"])
        state = ReviewState.model_validate_json(local["review-state.json"])
    except KeyError as exc:
        raise ValueError("review archive missing source package or review state") from exc
    workbench = _verify_review_files(local, package, state)
    if (package.package_sha256, state.state_sha256, workbench.audit_sha256) != (
        manifest.package_sha256,
        manifest.state_sha256,
        manifest.audit_sha256,
    ):
        raise ValueError("review archive source/state/Workbench binding mismatch")
    if set(manifest.input_bindings) != set(package.input_files):
        raise ValueError("review archive bound input inventory is incomplete")
    for origin, digest in package.input_files.items():
        name = manifest.input_bindings[origin]
        expected = manifest.files.get(name)
        if expected is None or expected.sha256 != digest:
            raise ValueError("review archive bound input fingerprint mismatch")
        path, source_root = Path(origin), Path(manifest.package_root)
        if path.is_relative_to(source_root):
            if name != "package/" + path.relative_to(source_root).as_posix():
                raise ValueError("archived local input has been substituted")
        elif name != "inputs/" + digest:
            raise ValueError("unexpected external review input binding")
    if {n for n in files if n.startswith("inputs/")} != {
        n for n in manifest.input_bindings.values() if n.startswith("inputs/")
    }:
        raise ValueError("unreferenced input in review archive")
    return ReviewArchiveSnapshot(manifest, package, state, workbench)


def verify_review_archive(path: Path) -> dict:
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("review archive exceeds size limit")
    return verify_archive_bytes(safe_read(path)).summary()


def archive_review_package(*, package: Path, output: Path) -> dict:
    output_is_separate(output.resolve(), (package,))
    if output.suffix != ".zip":
        raise ValueError("review archive output must be a .zip file")
    with review_lock(package / ".review.lock"):
        contract, state = load_review(package)
        raw, snapshot = build_archive_bytes(package, contract, state)
        if output.is_symlink() or any(p.is_symlink() for p in output.parents):
            raise ValueError("unsafe review archive output path")
        output.parent.mkdir(parents=True, exist_ok=True)
        with review_lock(output.parent / f".{output.name}.review-write.lock"):
            if output.exists():
                if output.read_bytes() != raw:
                    raise ValueError(
                        "review archive exists with different evidence; use a new path"
                    )
            else:
                fd, name = tempfile.mkstemp(prefix=f".{output.name}-", dir=output.parent)
                temporary = Path(name)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.rename(temporary, output)
                    _sync_directory(output.parent)
                finally:
                    temporary.unlink(missing_ok=True)
    return {**snapshot.summary(), "output": str(output)}
