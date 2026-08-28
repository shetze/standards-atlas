"""Filesystem persistence for rebuildable composed publication views."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.model import ComposedDocumentView

CURRENT_COMPOSED_DOCUMENT_VIEW_SCHEMA_VERSION = 2


class FileSystemComposedDocumentViewRepository:
    """Persist publication-only family compositions below ``.atlas/work``."""

    def __init__(self, workspace: Path = Path(".atlas/work")) -> None:
        self._root = workspace / "composed-documents"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, view: ComposedDocumentView) -> Path:
        path = self._path(view.family_key)
        payload = {
            "schema_version": CURRENT_COMPOSED_DOCUMENT_VIEW_SCHEMA_VERSION,
            "view": view.model_dump(mode="json"),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def load(self, family_key: str) -> ComposedDocumentView:
        path = self._path(family_key)
        if not path.exists():
            raise FileNotFoundError(f"No composed document view found for key: {family_key}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get(
            "schema_version"
        ) != CURRENT_COMPOSED_DOCUMENT_VIEW_SCHEMA_VERSION or not isinstance(
            payload.get("view"), dict
        ):
            raise ValueError(f"Unsupported composed document view payload: {path}")
        return ComposedDocumentView.model_validate(payload["view"])

    def exists(self, family_key: str) -> bool:
        return self._path(family_key).exists()

    def _path(self, family_key: str) -> Path:
        return self._root / f"{_safe_filename(family_key)}.json"


def _safe_filename(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
