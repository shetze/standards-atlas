"""File-system persistence for semantic knowledge extraction artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from standards_atlas.application.schema import require_supported_schema
from standards_atlas.domain.model import DocumentSemanticExtraction

CURRENT_SEMANTIC_EXTRACTION_SCHEMA_VERSION = 1


class FileSystemSemanticExtractionRepository:
    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._root = workspace / "semantic-extractions"
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, extraction: DocumentSemanticExtraction) -> None:
        payload = {
            "schema_version": CURRENT_SEMANTIC_EXTRACTION_SCHEMA_VERSION,
            "extraction": extraction.model_dump(mode="json"),
        }
        self._path(extraction.source_document_key).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load(self, document_key: str) -> DocumentSemanticExtraction | None:
        path = self._path(document_key)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        require_supported_schema("semantic-extraction", payload.get("schema_version"))
        data = payload.get("extraction")
        if not isinstance(data, dict):
            raise ValueError("semantic extraction payload is missing extraction")
        return DocumentSemanticExtraction.model_validate(data)

    def _path(self, document_key: str) -> Path:
        safe = (
            document_key.strip()
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
            .replace(" ", "_")
        )
        return self._root / f"{safe}.json"
