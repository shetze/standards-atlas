"""File-system based repository for EngineeringDocument objects."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    require_current_payload,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument, Standard

# Keep writer envelopes and reader compatibility on one canonical version policy.
CURRENT_DOCUMENT_SCHEMA_VERSION = SCHEMA_POLICIES["engineering-document"].current

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

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._documents_dir = workspace / "documents"
        self._documents_dir.mkdir(parents=True, exist_ok=True)

    def save(self, document: EngineeringDocument) -> None:
        """Persist a document using the current private schema version."""
        require_current_schema("engineering-document", CURRENT_DOCUMENT_SCHEMA_VERSION)
        if type(CURRENT_DOCUMENT_SCHEMA_VERSION) is not int:
            raise ValueError("engineering document schema version must be an integer")
        path = self._path_for_key(document.key)
        payload = {
            "schema_version": CURRENT_DOCUMENT_SCHEMA_VERSION,
            "document": document.model_dump(mode="json"),
        }
        require_current_payload("engineering-document", payload)

        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def backup(self, key: DocumentKey) -> Path:
        """Keep exact pre-repair bytes outside the repository's *.json inventory."""
        source = self._path_for_key(key)
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        target = source.with_name(f"{source.name}.before-routing-repair-{digest[:16]}.bak")
        try:
            with target.open("xb") as stream:
                stream.write(payload)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError(f"existing backup has different content: {target}") from None
        return target

    def load(self, key: DocumentKey) -> EngineeringDocument:
        """Load a document using the current schema baseline."""
        path = self._path_for_key(key)

        if not path.exists():
            raise FileNotFoundError(f"No persisted document found for key: {key.value}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        data = _extract_document_data(payload)
        document_type = DocumentType(data["document_type"])
        model = _DOCUMENT_MODELS[document_type]

        return model.model_validate(data)

    def exists(self, key: DocumentKey) -> bool:
        """Return whether a document exists."""
        return self._path_for_key(key).exists()

    def delete(self, key: DocumentKey) -> None:
        """Remove one persisted document when it exists."""
        self._path_for_key(key).unlink(missing_ok=True)

    def list(self) -> tuple[EngineeringDocument, ...]:
        """Return all persisted documents in stable key order."""
        documents = []
        for path in sorted(self._documents_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            documents.append(_document_from_payload(payload))
        return tuple(sorted(documents, key=lambda document: document.key.value))

    def list_readable(self) -> tuple[EngineeringDocument, ...]:
        """Return a strict inventory; obsolete sources must not silently disappear.

        This entry point is also used by cross-reference consumers. During
        refactoring it has the same current-only contract as ``list``/``load``.
        """
        return self.list()

    def _path_for_key(self, key: DocumentKey) -> Path:
        safe_key = _safe_filename(key.value)
        return self._documents_dir / f"{safe_key}.json"


def _document_from_payload(payload: Any) -> EngineeringDocument:
    data = _extract_document_data(payload)
    document_type = DocumentType(data["document_type"])
    model = _DOCUMENT_MODELS[document_type]
    return model.model_validate(data)


def _extract_document_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Persisted engineering document must be a JSON object")

    if "schema_version" not in payload:
        raise ValueError("Persisted engineering document is missing 'schema_version'")
    if type(payload["schema_version"]) is not int:
        raise ValueError("engineering document schema version must be an integer")
    require_supported_schema("engineering-document", payload["schema_version"])

    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError("Versioned engineering document payload is missing 'document'")
    return document


def _safe_filename(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
