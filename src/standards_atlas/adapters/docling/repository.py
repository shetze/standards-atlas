"""Private workspace persistence for native Docling artefacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from standards_atlas.application.ports.workflow_artifacts import ExtractionState


class DoclingArtifactRepository:
    """Store native Docling documents and metadata below a private workspace."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "docling"

    @property
    def workspace(self) -> Path:
        """Return the normalized private workspace path."""
        return self._workspace

    def document_path(self, document_key: str) -> Path:
        """Return the canonical native JSON path for ``document_key``."""
        return self._private_path(document_key, "document.json")

    def metadata_path(self, document_key: str) -> Path:
        """Return the conversion metadata path for ``document_key``."""
        return self._private_path(document_key, "conversion.json")

    def save_metadata(self, document_key: str, metadata: dict[str, Any]) -> Path:
        """Atomically persist conversion metadata."""
        path = self.metadata_path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(path, metadata)
        return path

    def load_metadata(self, document_key: str) -> dict[str, Any]:
        """Load and validate persisted conversion metadata."""
        path = self.metadata_path(document_key)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Conversion metadata must contain an object: {path}")
        return payload

    def extraction_state(self, document_key: str, source: Path) -> ExtractionState:
        """Compare a persisted extraction with its current source PDF."""
        document = self.document_path(document_key)
        metadata = self.metadata_path(document_key)
        if not document.exists() and not metadata.exists():
            return ExtractionState.MISSING
        if not document.is_file() or not metadata.is_file():
            return ExtractionState.INCOMPLETE
        try:
            stored = self.load_metadata(document_key)
        except (OSError, ValueError, json.JSONDecodeError):
            return ExtractionState.INCOMPLETE
        expected_hash = stored.get("source_sha256")
        if not isinstance(expected_hash, str) or not source.is_file():
            return ExtractionState.INCOMPLETE
        return (
            ExtractionState.CURRENT
            if expected_hash == sha256_file(source)
            else ExtractionState.STALE
        )

    def is_current(self, document_key: str, source: Path) -> bool:
        """Return whether the native artefact matches ``source``."""
        return self.extraction_state(document_key, source) is ExtractionState.CURRENT

    def _private_path(self, document_key: str, filename: str) -> Path:
        candidate = (self._root / _safe_filename(document_key) / filename).resolve()
        if not candidate.is_relative_to(self._workspace):
            raise ValueError("Docling artefacts must be stored below the private workspace")
        return candidate


def sha256_file(path: Path) -> str:
    """Return a stable SHA-256 digest without loading the whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_filename(value: str) -> str:
    stripped = value.strip()
    if not stripped or stripped in {".", ".."}:
        raise ValueError("Document key must not be empty or a relative path segment")
    if Path(stripped).is_absolute() or "/" in stripped or "\\" in stripped:
        raise ValueError("Document key must not contain path components")
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", stripped).strip("._")
    if not normalized:
        raise ValueError("Document key does not contain a usable filename")
    return normalized
