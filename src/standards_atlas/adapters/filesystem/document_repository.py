"""File-system based repository for EngineeringDocument objects."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.domain.model import (
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    Standard,
)

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
    """Persist EngineeringDocument objects as JSON files."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents_dir = workspace / "documents"
        self._documents_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: EngineeringDocument) -> None:
        """Persist a document as JSON."""
        path = self._path_for_key(document.key)

        path.write_text(
            json.dumps(
                document.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def load(self, key: DocumentKey) -> EngineeringDocument:
        path = self._path_for_key(key)

        if not path.exists():
            raise FileNotFoundError(
                f"No persisted document found for key: {key.value}"
            )

        data = json.loads(path.read_text(encoding="utf-8"))
        document_type = DocumentType(data["document_type"])

        model = _DOCUMENT_MODELS[document_type]

        return model.model_validate(data)

    def exists(self, key: DocumentKey) -> bool:
        """Return whether a document exists."""
        return self._path_for_key(key).exists()

    def _path_for_key(self, key: DocumentKey) -> Path:
        safe_key = _safe_filename(key.value)
        return self._documents_dir / f"{safe_key}.json"


def _safe_filename(value: str) -> str:
    return (
        value.strip()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
