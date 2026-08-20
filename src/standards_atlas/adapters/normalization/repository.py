"""Private workspace persistence for normalized extracted documents."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from standards_atlas.adapters.normalization.serialization import canonical_json, canonical_sha256
from standards_atlas.application.model.normalized_document import (
    NormalizationOptions,
    NormalizationRunMetadata,
    NormalizedExtractedDocument,
)


class NormalizationState(StrEnum):
    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    INCOMPLETE = "incomplete"


class NormalizationArtifactRepository:
    """Store deterministic payloads and separate run metadata below the workspace."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "normalized"

    def document_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "document.json")

    def method_technique_index_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "methods-and-techniques.json")

    def run_path(self, document_key: str) -> Path:
        return self._private_path(document_key, "run.json")

    def save(self, document_key: str, document: NormalizedExtractedDocument) -> Path:
        path = self.document_path(document_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, canonical_json(document))
        _atomic_write(
            self.method_technique_index_path(document_key),
            canonical_json(
                {
                    "schema_version": 1,
                    "document_key": document_key,
                    "candidates": [
                        candidate.model_dump(mode="json")
                        for candidate in document.method_technique_candidates
                    ],
                }
            ),
        )
        run = NormalizationRunMetadata(
            created_at=datetime.now(UTC),
            document_content_hash=canonical_sha256(document),
        )
        _atomic_write(self.run_path(document_key), canonical_json(run))
        return path

    def load(self, document_key: str) -> NormalizedExtractedDocument:
        return NormalizedExtractedDocument.model_validate_json(
            self.document_path(document_key).read_text(encoding="utf-8")
        )

    def load_run(self, document_key: str) -> NormalizationRunMetadata:
        return NormalizationRunMetadata.model_validate_json(
            self.run_path(document_key).read_text(encoding="utf-8")
        )

    def state(
        self,
        document_key: str,
        *,
        source_extraction_hash: str,
        options: NormalizationOptions,
        normalizer_version: str,
    ) -> NormalizationState:
        path = self.document_path(document_key)
        run_path = self.run_path(document_key)
        if not path.exists():
            return NormalizationState.MISSING
        if not path.is_file() or not run_path.is_file():
            return NormalizationState.INCOMPLETE
        try:
            document = self.load(document_key)
            run = self.load_run(document_key)
        except (OSError, ValueError, json.JSONDecodeError):
            return NormalizationState.INCOMPLETE
        if run.document_content_hash != canonical_sha256(document):
            return NormalizationState.INCOMPLETE
        metadata = document.metadata
        if (
            metadata.source_extraction_hash != source_extraction_hash
            or metadata.options != options
            or metadata.normalizer_version != normalizer_version
        ):
            return NormalizationState.STALE
        return NormalizationState.CURRENT

    def _private_path(self, document_key: str, filename: str) -> Path:
        stripped = document_key.strip()
        if not stripped or stripped in {".", ".."}:
            raise ValueError("Document key must not be empty or a relative path segment")
        if Path(stripped).is_absolute() or "/" in stripped or "\\" in stripped:
            raise ValueError("Document key must not contain path components")
        candidate = (self._root / stripped / filename).resolve()
        if not candidate.is_relative_to(self._workspace):
            raise ValueError("Normalized artefacts must be stored below the private workspace")
        return candidate


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)
