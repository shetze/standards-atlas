"""File-system based repository for EngineeringDocument objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    Standard,
)

CURRENT_DOCUMENT_SCHEMA_VERSION = 2

_DOCUMENT_MODELS: dict[
    DocumentType,
    type[EngineeringDocument],
] = {
    DocumentType.STANDARD: Standard,
    DocumentType.SPECIFICATION: EngineeringDocument,
    DocumentType.REPORT: EngineeringDocument,
    DocumentType.SAFETY_CASE_ARTIFACT: EngineeringDocument,
    DocumentType.OTHER: EngineeringDocument,
}


class FileSystemEngineeringDocumentRepository:
    """Persist EngineeringDocument objects as versioned JSON files."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents_dir = workspace / "documents"
        self._documents_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: EngineeringDocument) -> None:
        """Persist a document using the current private schema version."""
        path = self._path_for_key(document.key)
        payload = {
            "schema_version": CURRENT_DOCUMENT_SCHEMA_VERSION,
            "document": document.model_dump(mode="json"),
        }

        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load(self, key: DocumentKey) -> EngineeringDocument:
        """Load both current and legacy unversioned document files."""
        path = self._path_for_key(key)

        if not path.exists():
            raise FileNotFoundError(
                f"No persisted document found for key: {key.value}"
            )

        payload = json.loads(path.read_text(encoding="utf-8"))
        data = _extract_document_data(payload)
        document_type = DocumentType(data["document_type"])
        model = _DOCUMENT_MODELS[document_type]

        return model.model_validate(data)

    def exists(self, key: DocumentKey) -> bool:
        """Return whether a document exists."""
        return self._path_for_key(key).exists()

    def _path_for_key(self, key: DocumentKey) -> Path:
        safe_key = _safe_filename(key.value)
        return self._documents_dir / f"{safe_key}.json"


def _extract_document_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Persisted engineering document must be a JSON object")

    if "schema_version" not in payload:
        return payload

    version = payload["schema_version"]
    if version != CURRENT_DOCUMENT_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported engineering document schema version: "
            f"{version}; expected {CURRENT_DOCUMENT_SCHEMA_VERSION}"
        )

    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError("Versioned engineering document payload is missing 'document'")

    return document


def _safe_filename(value: str) -> str:
    return (
        value.strip()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
