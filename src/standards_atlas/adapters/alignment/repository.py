"""Private persistence for alignment results."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from standards_atlas.application.model.alignment import AlignmentResult


class AlignmentArtifactState(StrEnum):
    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    INCOMPLETE = "incomplete"


class AlignmentArtifactRepository:
    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "alignments"

    def document_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "alignment.json")

    def save(self, document_key: str, result: AlignmentResult) -> Path:
        path = self.document_path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return path

    def load(self, document_key: str) -> AlignmentResult:
        path = self.document_path(document_key)
        return AlignmentResult.model_validate_json(path.read_text(encoding="utf-8"))

    def state(
        self,
        document_key: str,
        *,
        normalized_hash: str,
        candidate_hash: str,
        structure_hash: str,
        alignment_version: str,
    ) -> AlignmentArtifactState:
        path = self.document_path(document_key)
        if not path.exists():
            return AlignmentArtifactState.MISSING
        try:
            result = self.load(document_key)
        except (OSError, ValueError):
            return AlignmentArtifactState.INCOMPLETE
        metadata = result.metadata
        if (
            metadata.normalized_document_hash == normalized_hash
            and metadata.candidate_document_hash == candidate_hash
            and metadata.expected_structure_hash == structure_hash
            and metadata.alignment_version == alignment_version
        ):
            return AlignmentArtifactState.CURRENT
        return AlignmentArtifactState.STALE

    def _private_path(self, document_key: str, filename: str) -> Path:
        key = document_key.strip()
        if not key or key in {".", ".."} or Path(key).is_absolute() or "/" in key or "\\" in key:
            raise ValueError("Document key must not contain path components")
        path = (self._root / key / filename).resolve()
        if not path.is_relative_to(self._workspace):
            raise ValueError("Alignment artefacts must remain below the private workspace")
        return path
