"""Filesystem repository for AP03 experiment plans, ledgers and private raw attempts."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from standards_atlas.adapters.filesystem.knowledge_proposal_repository import (
    FileSystemDocumentKnowledgeProposalRepository,
)
from standards_atlas.application.assertion_qualification.experiment import (
    AssertionExperimentManifest,
    AssertionExperimentState,
    manifest_sha256,
)
from standards_atlas.domain.model import DocumentKnowledgeProposal


class FileSystemAssertionExperimentRepository:
    def __init__(
        self, project_root: Path = Path("."), workspace: Path = Path(".atlas/data")
    ) -> None:
        self._public = project_root / "local" / "evaluation" / "assertions" / "ap03"
        self._private = workspace / "assertion-experiments"
        self._proposal_repository = FileSystemDocumentKnowledgeProposalRepository(workspace)

    def save_manifest(self, manifest: AssertionExperimentManifest) -> str:
        root = self._root(manifest.experiment_id)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "experiment-plan.json"
        payload = manifest.model_dump(mode="json")
        _write_json(path, payload)
        return manifest_sha256(manifest)

    def load_manifest(self, experiment_id: str) -> AssertionExperimentManifest:
        return AssertionExperimentManifest.model_validate(
            _read_json(self._root(experiment_id) / "experiment-plan.json")
        )

    def save_state(self, state: AssertionExperimentState) -> None:
        _write_json(
            self._root(state.experiment_id) / "experiment-state.json",
            state.model_dump(mode="json"),
        )

    def load_state(self, experiment_id: str) -> AssertionExperimentState | None:
        path = self._root(experiment_id) / "experiment-state.json"
        if not path.is_file():
            return None
        return AssertionExperimentState.model_validate(_read_json(path))

    def save_private_attempt(self, attempt_id: str, payload: Mapping[str, object]) -> str:
        if not attempt_id.startswith("attempt-") or "/" in attempt_id or "\\" in attempt_id:
            raise ValueError("invalid attempt id")
        path = self._private / "attempts" / f"{attempt_id}.json"
        merged: dict[str, object] = {}
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                raise ValueError("private attempt artifact must contain a JSON object")
            merged.update(existing)
        merged.update(dict(payload))
        data = (json.dumps(merged, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        _atomic_private_write(path, data)
        return str(path)

    def save_proposal(self, proposal: DocumentKnowledgeProposal) -> None:
        self._proposal_repository.save(proposal)

    def load_proposal(
        self, proposal_run_id: str, document_key: str
    ) -> DocumentKnowledgeProposal | None:
        return self._proposal_repository.load(proposal_run_id, document_key)

    def _root(self, experiment_id: str) -> Path:
        if (
            not experiment_id.strip()
            or "/" in experiment_id
            or "\\" in experiment_id
            or experiment_id in {".", ".."}
        ):
            raise ValueError("experiment id must be a safe path component")
        return self._public / experiment_id


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise ValueError(f"refusing to replace a symlink: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
