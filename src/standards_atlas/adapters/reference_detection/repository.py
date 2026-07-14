"""Private persistence for clause-reference candidate documents."""

from __future__ import annotations

import os
from pathlib import Path

from standards_atlas.application.model.reference_candidates import ReferenceCandidateDocument


class ReferenceCandidateRepository:
    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "reference-candidates"

    def document_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "document.json")

    def save(self, document_key: str, document: ReferenceCandidateDocument) -> Path:
        path = self.document_path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return path

    def load(self, document_key: str) -> ReferenceCandidateDocument:
        payload = self.document_path(document_key).read_text(encoding="utf-8")
        return ReferenceCandidateDocument.model_validate_json(payload)

    def _private_path(self, document_key: str, filename: str) -> Path:
        key = document_key.strip()
        if not key or key in {".", ".."} or Path(key).is_absolute() or "/" in key or "\\" in key:
            raise ValueError("Document key must not contain path components")
        path = (self._root / key / filename).resolve()
        if not path.is_relative_to(self._workspace):
            raise ValueError(
                "Reference candidate artefacts must remain below the private workspace"
            )
        return path
