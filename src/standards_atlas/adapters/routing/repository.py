"""Filesystem persistence for deterministic semantic routing artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from standards_atlas.application.routing.model import DocumentRoutingArtifact
from standards_atlas.application.schema import require_current_schema, require_supported_schema

_ROUTING_SCHEMA_VERSION = 1


class FileSystemSemanticRoutingArtifactRepository:
    """Store routing plans separately from EngineeringDocument semantic state."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._workspace = workspace.resolve()
        self._root = self._workspace / "routing"

    def artifact_path(
        self,
        document_key: str,
        contract_id: str,
        contract_version: str,
    ) -> Path:
        document = _safe_component(document_key, "document key")
        contract = _safe_component(contract_id, "routing contract id")
        version = _safe_component(contract_version, "routing contract version")
        path = (self._root / document / contract / version / "routing.json").resolve()
        if not path.is_relative_to(self._workspace):
            raise ValueError("routing artifacts must remain below the private workspace")
        return path

    def save(self, artifact: DocumentRoutingArtifact) -> None:
        path = self.artifact_path(
            artifact.document_key,
            artifact.contract_id,
            artifact.contract_version,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        require_current_schema("semantic-routing-artifact", _ROUTING_SCHEMA_VERSION)
        payload = {
            "schema_version": _ROUTING_SCHEMA_VERSION,
            "routing": artifact.model_dump(mode="json"),
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def load(
        self,
        document_key: str,
        contract_id: str,
        contract_version: str,
    ) -> DocumentRoutingArtifact:
        path = self.artifact_path(document_key, contract_id, contract_version)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("persisted semantic routing artifact must be a JSON object")
        require_supported_schema("semantic-routing-artifact", payload.get("schema_version"))
        routing = payload.get("routing")
        if not isinstance(routing, dict):
            raise ValueError("semantic routing artifact is missing 'routing'")
        artifact = DocumentRoutingArtifact.model_validate(routing)
        if (
            artifact.document_key != document_key
            or artifact.contract_id != contract_id
            or artifact.contract_version != contract_version
        ):
            raise ValueError("semantic routing artifact identity mismatch")
        return artifact


def _safe_component(value: str, label: str) -> str:
    candidate = value.strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or Path(candidate).is_absolute()
        or "/" in candidate
        or "\\" in candidate
    ):
        raise ValueError(f"{label} must not contain path components")
    return candidate
