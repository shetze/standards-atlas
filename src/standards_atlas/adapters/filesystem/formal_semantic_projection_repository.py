"""File-system persistence for derived formal semantic projections."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.domain.model import FormalSemanticProjection

CURRENT_FORMAL_SEMANTIC_PROJECTION_SCHEMA_VERSION = 1


class FileSystemFormalSemanticProjectionRepository:
    """Persist rebuildable formal semantic projections as versioned JSON."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._root = workspace / "formal-semantic-projections"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, projection: FormalSemanticProjection) -> None:
        payload = {
            "schema_version": CURRENT_FORMAL_SEMANTIC_PROJECTION_SCHEMA_VERSION,
            "projection": projection.model_dump(mode="json"),
        }
        self._path(projection.source_document_key).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load(self, document_key: str) -> FormalSemanticProjection | None:
        path = self._path(document_key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "schema_version" not in payload:
            raise ValueError("formal semantic projection payload is missing schema_version")
        require_supported_schema("formal-semantic-projection", payload["schema_version"])
        data = payload.get("projection")
        if not isinstance(data, dict):
            raise ValueError("formal semantic projection payload is missing projection")
        return FormalSemanticProjection.model_validate(data)

    def _path(self, document_key: str) -> Path:
        safe = (
            document_key.strip()
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
            .replace(" ", "_")
        )
        return self._root / f"{safe}.json"
